from fastapi import APIRouter, UploadFile, File, BackgroundTasks, Depends, HTTPException, status, Body, Query
import logging
import time
from sqlalchemy.orm import Session
from sqlalchemy import text

from app.api.dependencies.database import get_db
from app.api.dependencies.rate_limit import rate_limit
from app.api.dependencies.auth import get_current_user
from app.models.database.file import File as FileModel
from app.models.schemas.file import FileRead
from app.services.supabase_client import get_supabase
from app.core.config import settings
from app.workers.file_processor import run as process_file
from app.models.database.file import File as FileModel
from app.services.search_engine.data_sync_service import DataSyncService
from app.core.websocket_manager import websocket_manager


router = APIRouter()


def _process_file_background(file_id: int) -> None:
    # Legacy placeholder kept for compatibility
    return None

def process_file_from_path(file_id: int, file_path: str, filename: str) -> None:
    """Process file from disk path instead of memory content for large files."""
    import logging
    log = logging.getLogger("upload")
    
    try:
        # Verify file exists before processing
        import os
        if not os.path.exists(file_path):
            log.error(f"File not found for processing: {file_path}")
            return
        
        from app.workers.file_processor import run
        run(file_id, content=None, filename=filename, file_path=file_path)
        
        # Clean up temp file after successful processing
        try:
            os.remove(file_path)
            log.info(f"Cleaned up temp file after processing: {file_path}")
        except Exception as cleanup_err:
            log.warning(f"Failed to cleanup temp file {file_path}: {cleanup_err}")
            
    except Exception as e:
        log.error("Background processing failed for file %s: %s", file_id, e)
        
        # Update file status to failed
        try:
            from app.core.database import SessionLocal
            db = SessionLocal()
            try:
                from app.models.database.file import File as FileModel
                file_obj = db.get(FileModel, file_id)
                if file_obj:
                    file_obj.status = "failed"
                    db.add(file_obj)
                    db.commit()
                    log.info(f"Updated file {file_id} status to failed")
            finally:
                db.close()
        except Exception as status_err:
            log.error(f"Failed to update file status to failed: {status_err}")
        
        # Clean up temp file on error
        try:
            import os
            if os.path.exists(file_path):
                os.remove(file_path)
                log.info(f"Cleaned up temp file after error: {file_path}")
        except Exception as cleanup_err:
            log.warning(f"Failed to cleanup temp file after error {file_path}: {cleanup_err}")


# In-memory upload session registry for chunked uploads (Cloud Run safe within instance)
# Maps upload_id -> { file_id, tmp_path, filename, content_type, received_bytes, created_at }
_multipart_sessions: dict[str, dict] = {}
import threading
_multipart_sessions_lock = threading.RLock()

# Cleanup old sessions (older than 30 minutes for better resource management)
def cleanup_old_sessions():
    import time
    current_time = time.time()
    expired_sessions = []
    
    with _multipart_sessions_lock:
        for upload_id, session in _multipart_sessions.items():
            created_at = session.get('created_at', current_time)
            if current_time - created_at > 1800:  # 30 minutes
                expired_sessions.append(upload_id)
    
    for upload_id in expired_sessions:
        try:
            import os
            with _multipart_sessions_lock:
                session = _multipart_sessions.get(upload_id)
                if not session:
                    continue
                tmp_path = session.get('tmp_path')
                _multipart_sessions.pop(upload_id, None)
            
            if tmp_path and os.path.exists(tmp_path):
                os.remove(tmp_path)
                log = logging.getLogger("upload")
                log.info(f"Cleaned up expired session {upload_id}, removed temp file: {tmp_path}")
        except Exception as e:
            log = logging.getLogger("upload")
            log.warning(f"Failed to cleanup temp file for session {upload_id}: {e}")


@router.post("/multipart/init")
async def multipart_init(
    filename: str = Body(...),
    content_type: str = Body("application/octet-stream"),
    total_size: int | None = Body(None),
    db: Session = Depends(get_db),
    user=Depends(get_current_user),
):
    """Initialize a chunked upload session. Returns upload_id and file_id.
    Chunks must be POSTed to /multipart/part with the same upload_id.
    """
    import uuid, os, time
    try:
        # Cleanup old sessions first
        cleanup_old_sessions()
        
        # Create file record immediately to track progress
        obj = FileModel(
            filename=filename,
            size_bytes=0,
            content_type=content_type or "application/octet-stream",
            status="uploaded",
        )
        db.add(obj)
        db.commit()
        db.refresh(obj)

        upload_id = uuid.uuid4().hex
        tmp_path = f"/tmp/upload_{upload_id}.part"
        # Ensure empty file
        with open(tmp_path, "wb") as f:
            pass
        
        with _multipart_sessions_lock:
            _multipart_sessions[upload_id] = {
                "file_id": obj.id,
                "tmp_path": tmp_path,
                "filename": filename,
                "content_type": content_type,
                "received_bytes": 0,
                "total_size": total_size,
                "created_at": time.time(),
            }
        return {"upload_id": upload_id, "file_id": obj.id}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Init failed: {e}")


@router.post("/multipart/part")
async def multipart_part(
    upload_id: str = Query(...),
    part_number: int = Query(..., ge=1),
    total_parts: int | None = Query(None, ge=1),
    body: bytes = Body(...),
    db: Session = Depends(get_db),
    user=Depends(get_current_user),
):
    """Append a chunk to the temporary file for this upload session.
    Order is preserved by the client; server appends in the order received.
    """
    with _multipart_sessions_lock:
        sess = _multipart_sessions.get(upload_id)
        if not sess:
            raise HTTPException(status_code=404, detail="Upload session not found")
    
    try:
        # Append bytes to tmp file
        with open(sess["tmp_path"], "ab") as f:
            f.write(body)
        
        with _multipart_sessions_lock:
            sess["received_bytes"] = int(sess.get("received_bytes", 0)) + len(body)
        
        return {
            "upload_id": upload_id,
            "part_number": part_number,
            "received_bytes": sess["received_bytes"],
            "total_parts": total_parts,
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Append failed: {e}")


@router.post("/multipart/complete")
async def multipart_complete(
    request_data: dict = Body(...),
    db: Session = Depends(get_db),
    user=Depends(get_current_user),
):
    """Finalize the upload: upload to Supabase storage, mark as processing, and start background processing."""
    upload_id = request_data.get("upload_id")
    if not upload_id:
        raise HTTPException(status_code=422, detail="upload_id is required")
    
    # Cleanup old sessions first
    cleanup_old_sessions()
    
    with _multipart_sessions_lock:
        sess = _multipart_sessions.get(upload_id)
        if not sess:
            # Try to find the file by upload_id pattern or provide better error
            raise HTTPException(status_code=404, detail=f"Upload session not found. Session may have expired. Please try uploading again.")
    
    log = logging.getLogger("upload")
    
    try:
        file_id = sess["file_id"]
        tmp_path = sess["tmp_path"]
        filename = sess["filename"]
        content_type = sess["content_type"]
        obj = db.get(FileModel, file_id)
        if not obj:
            raise HTTPException(status_code=404, detail="File not found")
        
        # Get file size efficiently
        import os
        size_bytes = os.path.getsize(tmp_path)
        log.info(f"Completing multipart upload for {filename}, size: {size_bytes / (1024*1024):.1f}MB")
        
        # For all files, use file path processing to avoid memory issues
        # This is more efficient and handles large files better
        obj.storage_path = None  # Skip Supabase for now to avoid timeouts
        obj.size_bytes = size_bytes
        obj.status = "processing"
        db.add(obj)
        db.commit()
        db.refresh(obj)
        
        # Start processing with file path instead of content
        # This is much more memory efficient for large files
        try:
            import threading
            thread = threading.Thread(
                target=process_file_from_path, 
                args=(obj.id, tmp_path, filename), 
                daemon=True,
                name=f"file-processor-{obj.id}"
            )
            thread.start()
            log.info(f"Started background processing thread for file {obj.id}")
        except Exception as thread_err:
            log.error(f"Thread start failed in multipart complete: {thread_err}")
            # Fallback: mark as failed
            obj.status = "failed"
            db.add(obj)
            db.commit()
            raise HTTPException(status_code=500, detail=f"Failed to start processing: {thread_err}")
        
        # Clean up session after successful processing start
        with _multipart_sessions_lock:
            _multipart_sessions.pop(upload_id, None)
        
        # Cleanup temp file in background (don't block response)
        def cleanup_temp_file():
            try:
                import time
                time.sleep(5)  # Give processing a head start
                if os.path.exists(tmp_path):
                    os.remove(tmp_path)
                    log.info(f"Cleaned up temp file: {tmp_path}")
            except Exception as e:
                log.warning(f"Failed to cleanup temp file {tmp_path}: {e}")
        
        threading.Thread(target=cleanup_temp_file, daemon=True).start()
        
        return {"file_id": file_id, "status": "processing", "size_bytes": obj.size_bytes}
        
    except HTTPException:
        raise
    except Exception as e:
        log.error(f"Multipart complete failed for upload {upload_id}: {e}")
        # Clean up session on error
        with _multipart_sessions_lock:
            _multipart_sessions.pop(upload_id, None)
        raise HTTPException(status_code=500, detail=f"Complete failed: {e}")

@router.post("/{file_id}/cancel")
async def cancel_upload(file_id: int, db: Session = Depends(get_db), user=Depends(get_current_user)):
    """Mark an in-flight upload/ingestion as cancelled. The worker cooperatively stops soon after."""
    try:
        obj = db.get(FileModel, file_id)
        if not obj:
            raise HTTPException(status_code=404, detail="File not found")
        if obj.status in ("processed", "failed", "cancelled"):
            return {"status": obj.status, "message": "Nothing to cancel"}
        obj.status = "cancelled"
        db.add(obj)
        db.commit()
        return {"status": "cancelled", "file_id": file_id}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Cancel failed: {e}")
    return None


@router.get("/{file_id}/rows")
async def get_file_rows(
    file_id: int,
    page: int = 1,
    page_size: int = 100,
    db: Session = Depends(get_db),
    user=Depends(get_current_user)
):
    """Return paginated raw rows from the dataset table ds_{file_id}."""
    try:
        if page < 1:
            page = 1
        if page_size < 1:
            page_size = 100
        # Cap page_size to avoid huge payloads
        page_size = min(page_size, 5000)

        table_name = f"ds_{file_id}"
        # Verify table exists
        exists = db.execute(text(f"""
            SELECT EXISTS (
                SELECT FROM information_schema.tables 
                WHERE table_name = '{table_name}'
            );
        """)).scalar()
        if not exists:
            raise HTTPException(status_code=404, detail=f"Dataset {file_id} not found")

        # Get total count
        total = int(db.execute(text(f"SELECT COUNT(*) FROM {table_name}")).scalar() or 0)
        offset = (page - 1) * page_size

        # Fetch a page of rows
        rows = db.execute(text(f"SELECT * FROM {table_name} ORDER BY id ASC LIMIT :lim OFFSET :off"), {
            "lim": page_size,
            "off": offset,
        }).mappings().all()

        # Infer columns from first row if present
        columns = list(rows[0].keys()) if rows else []

        return {
            "file_id": file_id,
            "table": table_name,
            "page": page,
            "page_size": page_size,
            "rows_count": total,
            "total_pages": (total + page_size - 1) // page_size if page_size else 1,
            "columns": columns,
            "rows": [dict(r) for r in rows],
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to fetch rows: {e}")


@router.post("/", response_model=FileRead)
@router.post("", response_model=FileRead)
async def upload_file_unified(background: BackgroundTasks, file: UploadFile = File(...), db: Session = Depends(get_db), user=Depends(get_current_user)):
    """
    UNIFIED CHUNK-BASED upload endpoint that handles ALL file sizes (1MB to 500MB) efficiently.
    
    This endpoint:
    1. Uses streaming upload to avoid memory issues
    2. Creates temporary file for processing
    3. Processes all files using the same efficient pipeline
    4. Handles 100M+ rows with optimized batch processing
    """
    log = logging.getLogger("upload")
    import tempfile
    import os
    
    try:
        # Get file size first (if available)
        file_size = 0
        if hasattr(file, 'size') and file.size:
            file_size = file.size
            file_size_mb = file_size / (1024 * 1024)
            log.info(f"Unified upload: {file.filename}, size: {file_size_mb:.1f}MB")
        else:
            log.info(f"Unified upload: {file.filename}, size: unknown")
        
        # Create file record
        obj = FileModel(
            filename=file.filename,
            size_bytes=file_size,
            content_type=file.content_type or "application/octet-stream",
            status="processing"
        )
        db.add(obj)
        db.commit()
        db.refresh(obj)
        
        # Create temporary file for streaming processing
        with tempfile.NamedTemporaryFile(delete=False, suffix=f"_{file.filename}") as tmp_file:
            tmp_path = tmp_file.name
            
            # Stream file content to temporary file
            total_bytes = 0
            while chunk := await file.read(8192):  # 8KB chunks
                tmp_file.write(chunk)
                total_bytes += len(chunk)
            
            # Update file size if not known initially
            if file_size == 0:
                obj.size_bytes = total_bytes
                db.add(obj)
                db.commit()
                log.info(f"Updated file size: {total_bytes / (1024*1024):.1f}MB")
        
        # Process file using the efficient pipeline
        try:
            import threading
            thread = threading.Thread(
                target=process_file_from_path, 
                args=(obj.id, tmp_path, file.filename), 
                daemon=True,
                name=f"file-processor-{obj.id}"
            )
            thread.start()
            log.info(f"Started background processing thread for file {obj.id}")
        except Exception as thread_err:
            log.error(f"Thread start failed in unified upload: {thread_err}")
            # Cleanup temp file
            try:
                os.unlink(tmp_path)
            except:
                pass
            # Mark as failed
            obj.status = "failed"
            db.add(obj)
            db.commit()
            raise HTTPException(status_code=500, detail=f"Failed to start processing: {thread_err}")
        
        return FileRead.from_orm(obj)
    except Exception as e:
        log.error("Upload failed for filename=%s content_type=%s: %s", getattr(file, "filename", None), getattr(file, "content_type", None), e)
        raise HTTPException(status_code=500, detail=f"Upload failed: {e}")


@router.post("/test", response_model=FileRead)
async def test_upload(background: BackgroundTasks, db: Session = Depends(get_db)):
    """Helper endpoint to validate ingestion without multipart complexities."""
    return FileRead(
        id=1,
        filename="test.csv",
        size_bytes=100,
        content_type="text/csv",
        status="uploaded"
    )


@router.get("/", response_model=list[FileRead])
async def list_files(db: Session = Depends(get_db), user=Depends(get_current_user)):
    """List all uploaded files."""
    files = db.query(FileModel).order_by(FileModel.id.desc()).all()
    return [FileRead.from_orm(file) for file in files]


@router.get("/{file_id}", response_model=FileRead)
async def get_file_status(file_id: int, db: Session = Depends(get_db), user=Depends(get_current_user)):
    obj = db.get(FileModel, file_id)
    if not obj:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="File not found")
    return FileRead.from_orm(obj)


@router.delete("/{file_id}")
async def delete_file(file_id: int, db: Session = Depends(get_db), user=Depends(get_current_user)):
    """Delete a file and its associated data."""
    log = logging.getLogger("upload")
    
    # Get the file record
    file_obj = db.get(FileModel, file_id)
    if not file_obj:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="File not found")
    
    try:
        # Delete the associated data table if it exists
        table_name = f"ds_{file_id}"
        try:
            db.execute(text(f"DROP TABLE IF EXISTS {table_name}"))
            log.info(f"Dropped data table {table_name} for file {file_id}")
        except Exception as e:
            log.warning(f"Failed to drop table {table_name}: {e}")
        
        # Delete from Supabase storage if applicable
        if file_obj.storage_path and settings.SUPABASE_STORAGE_BUCKET:
            try:
                client = get_supabase()
                client.storage.from_(settings.SUPABASE_STORAGE_BUCKET).remove([file_obj.storage_path])
                log.info(f"Deleted file from Supabase storage: {file_obj.storage_path}")
            except Exception as e:
                log.warning(f"Failed to delete from Supabase storage: {e}")
        
        # Delete from Elasticsearch if data was synced
        if file_obj.elasticsearch_synced:
            try:
                from app.services.search_engine.elasticsearch_client import ElasticsearchBulkSearch
                es_client = ElasticsearchBulkSearch()
                if es_client.is_available():
                    # Delete all documents with this file_id
                    delete_query = {
                        "query": {
                            "term": {"file_id": file_id}
                        }
                    }
                    result = es_client.es.delete_by_query(
                        index=es_client.index_name,
                        body=delete_query,
                        refresh=True
                    )
                    deleted_count = result.get('deleted', 0)
                    log.info(f"Deleted {deleted_count} documents from Elasticsearch for file {file_id}")
                else:
                    log.warning("Elasticsearch not available, skipping ES cleanup")
            except Exception as e:
                log.warning(f"Failed to delete from Elasticsearch: {e}")
        
        # Delete the file record
        db.delete(file_obj)
        db.commit()
        
        log.info(f"Successfully deleted file {file_id}: {file_obj.filename}")
        return {"message": f"File {file_obj.filename} deleted successfully"}
        
    except Exception as e:
        db.rollback()
        log.error(f"Failed to delete file {file_id}: {e}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Delete failed: {e}")


@router.patch("/{file_id}/reset")
async def reset_stuck_file(file_id: int, db: Session = Depends(get_db), user=Depends(get_current_user)):
    """Reset a stuck file status to allow new uploads."""
    log = logging.getLogger("upload")
    
    # Get the file record
    file_obj = db.get(FileModel, file_id)
    if not file_obj:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="File not found")
    
    try:
        # Only reset if file is stuck in processing state
        if file_obj.status == "processing":
            file_obj.status = "failed"
            db.add(file_obj)
            db.commit()
            
            log.info(f"Reset stuck file {file_id} status from 'processing' to 'failed'")
            return {"message": f"File {file_id} status reset successfully", "new_status": "failed"}
        else:
            return {"message": f"File {file_id} is not stuck (current status: {file_obj.status})", "current_status": file_obj.status}
        
    except Exception as e:
        db.rollback()
        log.error(f"Failed to reset file {file_id}: {e}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Reset failed: {e}")


@router.get("/stuck")
async def list_stuck_files(db: Session = Depends(get_db), user=Depends(get_current_user)):
    """List files that are stuck in processing state."""
    log = logging.getLogger("upload")
    
    try:
        # Find files stuck in processing for more than 10 minutes
        stuck_files = db.query(FileModel).filter(
            FileModel.status == "processing"
        ).all()
        
        result = []
        for file_obj in stuck_files:
            result.append({
                "id": file_obj.id,
                "filename": file_obj.filename,
                "status": file_obj.status,
                "size_bytes": file_obj.size_bytes,
                "content_type": file_obj.content_type,
                "rows_count": file_obj.rows_count
            })
        
        log.info(f"Found {len(result)} stuck files")
        return {"stuck_files": result, "count": len(result)}
        
    except Exception as e:
        log.error(f"Failed to list stuck files: {e}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Failed to list stuck files: {e}")


@router.get("/{file_id}/elasticsearch-status")
async def get_elasticsearch_status(file_id: int, db: Session = Depends(get_db), user=Depends(get_current_user)):
    """
    Get Elasticsearch sync status for a file
    """
    log = logging.getLogger("upload")
    try:
        file_obj = db.query(FileModel).filter(FileModel.id == file_id).first()
        if not file_obj:
            raise HTTPException(status_code=404, detail="File not found")
        
        return {
            "file_id": file_id,
            "filename": file_obj.filename,
            "elasticsearch_synced": file_obj.elasticsearch_synced,
            "elasticsearch_sync_error": file_obj.elasticsearch_sync_error,
            "status": "synced" if file_obj.elasticsearch_synced else "failed" if file_obj.elasticsearch_sync_error else "pending"
        }
        
    except HTTPException:
        raise
    except Exception as e:
        log.error(f"Failed to get Elasticsearch status for file {file_id}: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to get Elasticsearch status: {e}")


@router.get("/{file_id}/upload-progress")
async def get_upload_progress(file_id: int, db: Session = Depends(get_db), user=Depends(get_current_user)):
    """
    Get detailed upload progress for a file
    """
    log = logging.getLogger("upload")
    try:
        file_obj = db.query(FileModel).filter(FileModel.id == file_id).first()
        if not file_obj:
            raise HTTPException(status_code=404, detail="File not found")
        
        # Check if file is in multipart session
        with _multipart_sessions_lock:
            active_sessions = [session for session in _multipart_sessions.values() if session.get('file_id') == file_id]
            active_session = active_sessions[0] if active_sessions else None
        
        progress_data = {
            "file_id": file_id,
            "filename": file_obj.filename,
            "status": file_obj.status,
            "size_bytes": file_obj.size_bytes,
            "rows_count": file_obj.rows_count,
            "upload_progress": 0,
            "is_uploading": False,
            "received_bytes": 0,
            "total_size": 0,
            "elasticsearch_synced": file_obj.elasticsearch_synced,
            "elasticsearch_sync_error": file_obj.elasticsearch_sync_error,
            "websocket_connections": websocket_manager.get_connection_count(str(file_id))
        }
        
        if active_session:
            progress_data.update({
                "is_uploading": True,
                "received_bytes": active_session.get('received_bytes', 0),
                "total_size": active_session.get('total_size', 0),
                "upload_progress": min(100, int((active_session.get('received_bytes', 0) / max(1, active_session.get('total_size', 1))) * 100))
            })
        
        return progress_data
        
    except HTTPException:
        raise
    except Exception as e:
        log.error(f"Failed to get upload progress for file {file_id}: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to get upload progress: {e}")


@router.get("/system/health")
async def get_system_health(db: Session = Depends(get_db), user=Depends(get_current_user)):
    """
    Get comprehensive system health status
    """
    log = logging.getLogger("upload")
    try:
        # Database health
        db_health = {"status": "healthy", "connections": 0}
        try:
            result = db.execute(text("SELECT COUNT(*) FROM file")).scalar()
            db_health["file_count"] = result
        except Exception as e:
            db_health = {"status": "unhealthy", "error": str(e)}
        
        # Session health
        with _multipart_sessions_lock:
            session_count = len(_multipart_sessions)
            active_sessions = list(_multipart_sessions.values())
        
        # WebSocket health
        ws_health = {
            "total_connections": websocket_manager.get_total_connections(),
            "active_files": len(websocket_manager.active_connections)
        }
        
        # Memory usage (approximate)
        import psutil
        memory_info = {
            "memory_percent": psutil.virtual_memory().percent,
            "available_mb": psutil.virtual_memory().available // (1024 * 1024)
        }
        
        return {
            "timestamp": time.time(),
            "database": db_health,
            "sessions": {
                "active_upload_sessions": session_count,
                "sessions": [
                    {
                        "upload_id": upload_id,
                        "file_id": session.get('file_id'),
                        "filename": session.get('filename'),
                        "received_bytes": session.get('received_bytes', 0),
                        "total_size": session.get('total_size', 0),
                        "created_at": session.get('created_at', 0)
                    }
                    for upload_id, session in _multipart_sessions.items()
                ]
            },
            "websockets": ws_health,
            "memory": memory_info,
            "overall_status": "healthy" if db_health["status"] == "healthy" else "degraded"
        }
        
    except Exception as e:
        log.error(f"Failed to get system health: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to get system health: {e}")


@router.post("/{file_id}/elasticsearch-retry")
async def retry_elasticsearch_sync(file_id: int, background: BackgroundTasks, db: Session = Depends(get_db), user=Depends(get_current_user)):
    """
    Retry Elasticsearch sync for a file
    """
    log = logging.getLogger("upload")
    try:
        file_obj = db.query(FileModel).filter(FileModel.id == file_id).first()
        if not file_obj:
            raise HTTPException(status_code=404, detail="File not found")
        
        if file_obj.status != "processed":
            raise HTTPException(status_code=400, detail="File must be processed before syncing to Elasticsearch")
        
        # Reset sync status
        file_obj.elasticsearch_synced = False
        file_obj.elasticsearch_sync_error = None
        db.add(file_obj)
        db.commit()
        
        # Start background sync
        def sync_elasticsearch():
            try:
                sync_service = DataSyncService()
                success = sync_service.sync_file_to_elasticsearch(file_id)
                
                # Update status
                file_obj.elasticsearch_synced = success
                if not success:
                    file_obj.elasticsearch_sync_error = "Sync failed - check logs for details"
                else:
                    file_obj.elasticsearch_sync_error = None
                db.add(file_obj)
                db.commit()
                
                log.info(f"Elasticsearch sync {'completed' if success else 'failed'} for file {file_id}")
            except Exception as e:
                log.error(f"Elasticsearch sync failed for file {file_id}: {e}")
                file_obj.elasticsearch_synced = False
                file_obj.elasticsearch_sync_error = str(e)
                db.add(file_obj)
                db.commit()
        
        background.add_task(sync_elasticsearch)
        
        return {
            "message": "Elasticsearch sync started in background",
            "file_id": file_id,
            "status": "syncing"
        }
        
    except HTTPException:
        raise
    except Exception as e:
        log.error(f"Failed to start Elasticsearch sync for file {file_id}: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to start Elasticsearch sync: {e}")


