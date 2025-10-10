from typing import Tuple, List, Dict, Callable, Optional
from sqlalchemy import MetaData, text
from sqlalchemy.orm import Session
import asyncio
import logging

from app.services.data_processor.excel_parser import iter_rows
from app.services.data_processor.schema_generator import build_table
from app.services.vector_store.vector_operations import upsert_texts
# NOTE: Avoid importing websocket_manager at module load to keep workers lightweight.
# We'll import inside functions right before sending to prevent pickling issues.
from app.services.data_processor.data_cleaner import clean_row
from app.services.data_processor.data_validator import validate_row
from app.core.config import settings


def process_in_batches(db: Session, file_bytes: bytes, filename: str, dataset_name: str, file_id: int = None, batch_size: int | None = None, cancel_check: Optional[Callable[[], bool]] = None) -> Tuple[int, str]:
	# SQLAlchemy 2.x: MetaData no longer accepts 'bind'. Use engine explicitly on create_all
	metadata = MetaData()
	engine = db.get_bind()
	total = 0
	table_name = f"ds_{dataset_name}"
	table = None
	batch_count = 0
	
	# Determine optimal batch size based on file size and row count
	file_size_mb = len(file_bytes) / (1024 * 1024)
	
	if batch_size is None or batch_size <= 0:
		# Use adaptive batch sizing for massive files
		if file_size_mb > settings.MASSIVE_FILE_THRESHOLD_MB:
			batch_size = settings.STREAMING_BATCH_SIZE  # 100K for massive files
		else:
			batch_size = max(1000, int(settings.INGEST_BATCH_SIZE))
	
	# For massive files, allow much larger batch sizes
	if file_size_mb > settings.MASSIVE_FILE_THRESHOLD_MB:
		# Allow up to 100K rows per batch for massive files
		batch_size = min(batch_size, settings.STREAMING_BATCH_SIZE)
	else:
		# Standard cap for smaller files
		if batch_size > 10000:
			batch_size = 10000

	# Resumable: find how many rows already inserted
	# Note: counts data rows, not including header
	already = 0
	try:
		res = db.execute(text(f"SELECT COUNT(*) FROM {table_name}"))
		already = int(res.scalar() or 0)
	except Exception:
		already = 0

	log = logging.getLogger("file_processor")

	def _safe_insert(rows: List[Dict]) -> List[str]:
		"""Insert rows, splitting recursively on failure to avoid param limits.
		Returns inserted row ids only when embeddings are enabled; otherwise returns
		placeholders (empty list) to avoid RETURNING overhead on large batches.
		"""
		if not rows:
			return []
		try:
			if settings.DEFER_EMBEDDINGS:
				# Faster path: no RETURNING to reduce server-side overhead
				db.execute(table.insert(), rows)
				inserted = []
			else:
				result = db.execute(table.insert().returning(table.c.id), rows)
				inserted = [str(row_id[0]) for row_id in result.fetchall()]
			db.commit()
			return inserted
		except Exception:
			db.rollback()
			try:
				log.warning("Bulk insert failed for %s rows, splitting...", len(rows))
			except Exception:
				pass
			if len(rows) == 1:
				# Drop the problematic row
				return []
			mid = len(rows) // 2
			left_ids = _safe_insert(rows[:mid])
			right_ids = _safe_insert(rows[mid:])
			return left_ids + right_ids

	for batch in iter_rows(file_bytes, filename, chunk_size=batch_size, skip_rows=already):
		# Cooperative cancellation: allow caller to abort cleanly
		if cancel_check and cancel_check():
			try:
				log.info("Cancellation requested, stopping ingestion early")
			except Exception:
				pass
			break
		# Clean and validate batch
		cleaned: List[Dict] = [clean_row(r) for r in batch]
		valid: List[Dict] = [r for r in cleaned if validate_row(r)]
		invalid_count = len(cleaned) - len(valid)
		if invalid_count and file_id:
			# Websocket disabled to avoid pickling issues
			pass
		batch = valid
		
		if table is None:
			table = build_table(metadata, table_name, batch[:10])
			# Bind explicitly in SQLAlchemy 2.x
			metadata.create_all(bind=engine)
			# Send schema creation message (websocket disabled)
			if file_id:
				pass
		
		if not batch:
			continue
		
		batch_count += 1
		try:
			log.info("Ingest batch %s: attempting %s rows", batch_count, len(batch))
		except Exception:
			pass
		
		# Insert and capture primary keys for embedding linkage
		inserted_ids = _safe_insert(batch)
		# When embeddings are deferred, we didn't fetch ids; count rows by batch length
		if settings.DEFER_EMBEDDINGS:
			total += len(batch)
		else:
			total += len(inserted_ids)
		try:
			log.info("Ingest batch %s: inserted %s rows, running total %s", batch_count, len(inserted_ids), total)
		except Exception:
			pass

		# Send batch progress (reduced frequency for better performance)
		if file_id and batch_count % 5 == 0:  # Only send every 5 batches
			try:
				# Lazy import to avoid pickling/init issues
				from app.core.websocket_manager import websocket_manager
				message = {
					"type": "batch_progress",
					"file_id": file_id,
					"processed_rows": int(total),
					"current_batch": int(batch_count),
					"processing_stage": "processing_data"
				}
				# Best-effort non-blocking send
				loop = None
				try:
					loop = asyncio.get_running_loop()
				except RuntimeError:
					loop = None
				if loop and loop.is_running():
					loop.create_task(websocket_manager.send_progress(str(file_id), message))
				else:
					asyncio.run(websocket_manager.send_progress(str(file_id), message))
			except Exception:
				# Never fail ingestion due to progress update issues
				pass

		# Build texts for embeddings from string-like columns
		string_cols: List[str] = []
		for col in table.columns:
			if col.name == "id":
				continue
			# Consider String/Text columns only
			if getattr(col.type, "length", None) is not None or col.type.__class__.__name__ in ("String", "Text"):
				string_cols.append(col.name)
		# Fallback: if no typed info, use all keys that are str in first row
		if not string_cols and batch:
			sample = batch[0]
			string_cols = [k for k, v in sample.items() if isinstance(v, str)]

		documents: List[str] = []
		metadatas: List[Dict] = []
		for row in batch:
			parts = []
			for key in string_cols:
				val = row.get(key)
				if isinstance(val, str) and val.strip():
					parts.append(f"{key}: {val}")
			documents.append(" | ".join(parts) if parts else "")
			metadatas.append({"dataset": dataset_name})
		if any(documents) and not settings.DEFER_EMBEDDINGS:
			# chroma client computes embeddings if not provided, but we pass texts to keep it consistent
			collection = f"ds_{dataset_name}"
			# Upsert with inserted row ids mapped to documents; never block ingestion
			try:
				upsert_texts(collection, ids=inserted_ids, texts=documents, metadatas=metadatas)
			except Exception as e:
				try:
					log.warning("Embedding upsert failed for batch %s: %s", batch_count, e)
				except Exception:
					pass
			
			# Send embedding progress (reduced frequency for better performance)
			if file_id and batch_count % 10 == 0:  # Only send every 10 batches
				try:
					from app.core.websocket_manager import websocket_manager
					msg = {
						"type": "embedding_progress",
						"file_id": file_id,
						"current_batch": int(batch_count),
						"processing_stage": "embedding_upsert"
					}
					loop = None
					try:
						loop = asyncio.get_running_loop()
					except RuntimeError:
						loop = None
					if loop and loop.is_running():
						loop.create_task(websocket_manager.send_progress(str(file_id), msg))
					else:
						asyncio.run(websocket_manager.send_progress(str(file_id), msg))
				except Exception:
					pass

	if table is None:
		table = build_table(metadata, table_name, [])
		metadata.create_all(bind=engine)
	return total, table_name