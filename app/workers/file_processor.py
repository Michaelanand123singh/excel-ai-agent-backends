from sqlalchemy.orm import Session
import asyncio
import logging

from app.core.database import SessionLocal
from app.core.config import settings
from app.models.database.file import File as FileModel
from app.services.supabase_client import get_supabase
from app.services.data_processor.batch_processor import process_in_batches
from app.services.data_processor.massive_file_processor import process_massive_file_in_batches
from app.services.database.index_manager import create_search_indexes
from app.services.database.ultra_fast_index_manager import create_ultra_fast_indexes, optimize_table_for_bulk_search
from app.services.cache.ultra_fast_cache_manager import ultra_fast_cache
from app.core.websocket_manager import websocket_manager
from app.services.search_engine.data_sync import DataSyncService
from app.services.search_engine.google_cloud_search_client import GoogleCloudSearchClient

logger = logging.getLogger("file_processor")


def get_common_part_numbers(session: Session, table_name: str, limit: int = 100) -> list[str]:
	"""Get common part numbers from a table for cache warming"""
	try:
		from sqlalchemy import text
		result = session.execute(text(f"""
			SELECT "part_number", COUNT(*) as frequency
			FROM {table_name}
			WHERE "part_number" IS NOT NULL 
			AND "part_number" != ''
			GROUP BY "part_number"
			ORDER BY frequency DESC
			LIMIT {limit}
		""")).fetchall()
		return [row[0] for row in result]
	except Exception as e:
		logger.warning(f"Failed to get common part numbers for {table_name}: {e}")
		return []


def run(file_id: int, content: bytes | None = None, filename: str | None = None, file_path: str | None = None) -> None:
	session: Session = SessionLocal()
	try:
		obj = session.get(FileModel, file_id)
		if not obj:
			return
		# mark as processing
		obj.status = "processing"
		session.add(obj)
		session.commit()
		
		# Notify start (best-effort websocket)
		logger.info(f"Processing started for file {file_id}: {obj.filename}")
		try:
			message = {"type": "processing_started", "file_id": file_id}
			websocket_manager.send_progress_sync(str(file_id), message)
		except Exception as e:
			logger.warning(f"Failed to send processing started notification: {e}")
		
		data = content
		name = filename or obj.filename
		if data is None and file_path:
			# Read from file path for large files
			try:
				with open(file_path, "rb") as f:
					data = f.read()
			except Exception as e:
				logger.error(f"Failed to read file {file_path}: {e}")
				obj.status = "failed"
				session.add(obj)
				session.commit()
				return
		elif data is None:
			bucket = settings.SUPABASE_STORAGE_BUCKET
			if not bucket:
				logger.error(f"No storage bucket configured for file {file_id}")
				return
			client = get_supabase()
			path = obj.storage_path or f"files/{obj.id}/{obj.filename}"
			data = client.storage.from_(bucket).download(path)
		
		# Notify download complete
		logger.info(f"Download complete for file {file_id}: {len(data)} bytes")
		try:
			message = {"type": "download_complete", "file_id": file_id, "size_bytes": len(data), "processing_stage": "downloaded"}
			websocket_manager.send_progress_sync(str(file_id), message)
		except Exception as e:
			logger.warning(f"Failed to send download complete notification: {e}")

		# Define a lightweight cancellation checker: treat non-processing status as cancellation
		def is_cancelled() -> bool:
			try:
				fresh = session.get(FileModel, file_id)
				return (fresh is None) or (fresh.status not in ("processing", "uploaded"))
			except Exception:
				return False

		# Notify data processing start
		try:
			message = {"type": "data_processing_started", "file_id": file_id, "processing_stage": "parsing_data"}
			websocket_manager.send_progress_sync(str(file_id), message)
		except Exception as e:
			logger.warning(f"Failed to send data processing started notification: {e}")

		# Choose processor based on file size for optimal performance
		file_size_mb = len(data) / (1024 * 1024)
		
		if file_size_mb > settings.MASSIVE_FILE_THRESHOLD_MB:
			logger.info(f"🚀 Using massive file processor for {file_size_mb:.1f}MB file")
			logger.info(f"📊 File size: {len(data):,} bytes, Threshold: {settings.MASSIVE_FILE_THRESHOLD_MB}MB")
			total, table_name = process_massive_file_in_batches(
				session,
				data,
				name,
				dataset_name=str(obj.id),
				file_id=file_id,
				cancel_check=is_cancelled,
			)
			logger.info(f"✅ Massive file processing completed: {total:,} rows processed")
		else:
			logger.info(f"📦 Using standard batch processor for {file_size_mb:.1f}MB file")
			total, table_name = process_in_batches(
				session,
				data,
				name,
				dataset_name=str(obj.id),
				file_id=file_id,
				cancel_check=is_cancelled,
			)
		obj.rows_count = total
		# If cancelled mid-way, mark as cancelled instead of processed
		try:
			fresh = session.get(FileModel, file_id)
			if fresh and fresh.status not in ("processing", "uploaded"):
				obj.status = "cancelled"
			else:
				obj.status = "processed"
		except Exception:
			obj.status = "processed"
		session.add(obj)
		session.commit()
		
		# Create search indexes for faster queries (temporarily disabled for timeout issues)
		try:
			# create_search_indexes(session, table_name)
			logger.info(f"Skipped search indexes for table {table_name} (timeout issues)")
		except Exception as e:
			logger.warning(f"Failed to create indexes for table {table_name}: {e}")
		
		# Create ultra-fast indexes for bulk search optimization (temporarily disabled)
		try:
			# create_ultra_fast_indexes(session, table_name)
			# optimize_table_for_bulk_search(session, table_name)
			logger.info(f"Skipped ultra-fast indexes for table {table_name} (timeout issues)")
		except Exception as e:
			logger.warning(f"Failed to create ultra-fast indexes for table {table_name}: {e}")
		
		# Warm up cache with common part numbers for better performance
		try:
			common_parts = get_common_part_numbers(session, table_name)
			ultra_fast_cache.warm_up_cache(table_name, common_parts)
			logger.info(f"Warmed up cache for table {table_name} with {len(common_parts)} common parts")
		except Exception as e:
			logger.warning(f"Failed to warm up cache for table {table_name}: {e}")
		
		# Index data to Google Cloud Search for ultra-fast search
		gcs_synced = False
		try:
			gcs_client = GoogleCloudSearchClient()
			if gcs_client.is_available():
				# Create index if it doesn't exist
				gcs_client.create_index(table_name, file_id)
				
				# Get data from database to index
				from sqlalchemy import text
				data_result = session.execute(text(f"""
					SELECT 
						"part_number",
						"Item_Description",
						"Potential Buyer 1",
						"Potential Buyer 1 Contact Details",
						"Potential Buyer 1 email id",
						"Quantity",
						"Unit_Price",
						"UQC",
						"Potential Buyer 2",
						"Potential Buyer 2 Contact Details",
						"Potential Buyer 2 email id"
					FROM {table_name}
					LIMIT 100000
				""")).fetchall()
				
				data = [dict(row._mapping) for row in data_result]
				if data:
					gcs_synced = gcs_client.index_data(data, file_id)
					logger.info(f"✅ Google Cloud Search indexing {'completed' if gcs_synced else 'failed'} for file {file_id}")
				else:
					logger.warning(f"No data found to index for file {file_id}")
			else:
				logger.warning(f"Google Cloud Search not available for file {file_id}")
		except Exception as gcs_err:
			logger.warning(f"Google Cloud Search indexing failed for file {file_id}: {gcs_err}")
		
		# Notify PostgreSQL storage complete
		try:
			message = {"type": "postgresql_storage_complete", "file_id": file_id, "total_rows": int(total), "processing_stage": "postgresql_ready"}
			websocket_manager.send_progress_sync(str(file_id), message)
		except Exception as e:
			logger.warning(f"Failed to send PostgreSQL storage complete notification: {e}")

		# Notify processing complete
		logger.info(f"Processing complete for file {file_id}: {total} rows processed")
		try:
			# Trigger Elasticsearch sync so bulk ES search is ready automatically
			sync_service = DataSyncService()
			es_synced = False
			try:
				# Notify Elasticsearch sync started
				try:
					msg = {"type": "elasticsearch_sync_started", "file_id": file_id, "processing_stage": "elasticsearch_syncing"}
					websocket_manager.send_progress_sync(str(file_id), msg)
				except Exception as e:
					logger.warning(f"Failed to send Elasticsearch sync started notification: {e}")

				es_synced = sync_service.sync_file_to_elasticsearch(file_id)
				
				# Update file record with ES sync status
				obj.elasticsearch_synced = es_synced
				if not es_synced:
					obj.elasticsearch_sync_error = "Sync failed - check logs for details"
				else:
					obj.elasticsearch_sync_error = None
				session.add(obj)
				session.commit()
				logger.info(f"✅ Updated file {file_id} ES sync status: {es_synced}")
				
				# Send WebSocket notification for status update
				try:
					msg = {
						"type": "elasticsearch_sync_complete",
						"file_id": file_id,
						"elasticsearch_synced": es_synced,
						"elasticsearch_sync_error": obj.elasticsearch_sync_error
					}
					websocket_manager.send_progress_sync(str(file_id), msg)
				except Exception as e:
					logger.warning(f"Failed to send Elasticsearch sync complete notification: {e}")
				
			except Exception as sync_err:
				logger.warning(f"Elasticsearch sync failed for file {file_id}: {sync_err}")
				# Update file record with ES sync error
				obj.elasticsearch_synced = False
				obj.elasticsearch_sync_error = str(sync_err)
				session.add(obj)
				session.commit()
				logger.info(f"❌ Updated file {file_id} ES sync status: failed")
				
				# Send WebSocket notification for status update
				try:
					msg = {
						"type": "elasticsearch_sync_complete",
						"file_id": file_id,
						"elasticsearch_synced": False,
						"elasticsearch_sync_error": str(sync_err)
					}
					websocket_manager.send_progress_sync(str(file_id), msg)
				except Exception as e:
					logger.warning(f"Failed to send Elasticsearch sync error notification: {e}")
			
			message = {
				"type": "processing_complete", 
				"file_id": file_id, 
				"total_rows": int(total),
				"ultra_fast_optimized": True,
				"bulk_search_ready": True,
				"google_cloud_search_synced": bool(gcs_synced),
				"elasticsearch_synced": bool(es_synced)
			}
			websocket_manager.send_progress_sync(str(file_id), message)
		except Exception as e:
			logger.warning(f"Failed to send processing complete notification: {e}")
		
	except Exception as e:
		session.rollback()
		# update status on failure so UI doesn't stay stuck
		try:
			obj = session.get(FileModel, file_id)
			if obj:
				obj.status = "failed"
				session.add(obj)
				session.commit()
		except Exception:
			pass
		logger.error(f"File processing failed for file {file_id}: {e}")
	finally:
		session.close()


