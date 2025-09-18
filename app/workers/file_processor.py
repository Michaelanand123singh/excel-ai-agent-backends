from sqlalchemy.orm import Session
import asyncio
import logging

from app.core.database import SessionLocal
from app.core.config import settings
from app.models.database.file import File as FileModel
from app.services.supabase_client import get_supabase
from app.services.data_processor.batch_processor import process_in_batches
from app.services.database.index_manager import create_search_indexes
from app.core.websocket_manager import websocket_manager

logger = logging.getLogger("file_processor")


def run(file_id: int, content: bytes | None = None, filename: str | None = None) -> None:
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
			loop = None
			try:
				loop = asyncio.get_running_loop()
			except RuntimeError:
				loop = None
			message = {"type": "processing_started", "file_id": file_id}
			if loop and loop.is_running():
				loop.create_task(websocket_manager.send_progress(str(file_id), message))
			else:
				asyncio.run(websocket_manager.send_progress(str(file_id), message))
		except Exception:
			pass
		
		data = content
		name = filename or obj.filename
		if data is None:
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
			loop = None
			try:
				loop = asyncio.get_running_loop()
			except RuntimeError:
				loop = None
			message = {"type": "download_complete", "file_id": file_id, "size_bytes": len(data)}
			if loop and loop.is_running():
				loop.create_task(websocket_manager.send_progress(str(file_id), message))
			else:
				asyncio.run(websocket_manager.send_progress(str(file_id), message))
		except Exception:
			pass
		
		total, table_name = process_in_batches(session, data, name, dataset_name=str(obj.id), file_id=file_id)
		obj.rows_count = total
		obj.status = "processed"
		session.add(obj)
		session.commit()
		
		# Create search indexes for faster queries
		try:
			create_search_indexes(session, table_name)
			logger.info(f"Created search indexes for table {table_name}")
		except Exception as e:
			logger.warning(f"Failed to create indexes for table {table_name}: {e}")
		
		# Notify processing complete
		logger.info(f"Processing complete for file {file_id}: {total} rows processed")
		try:
			loop = None
			try:
				loop = asyncio.get_running_loop()
			except RuntimeError:
				loop = None
			message = {"type": "processing_complete", "file_id": file_id, "total_rows": int(total)}
			if loop and loop.is_running():
				loop.create_task(websocket_manager.send_progress(str(file_id), message))
			else:
				asyncio.run(websocket_manager.send_progress(str(file_id), message))
		except Exception:
			pass
		
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


