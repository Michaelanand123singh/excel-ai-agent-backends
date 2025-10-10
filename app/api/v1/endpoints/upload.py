from fastapi import APIRouter, UploadFile, File, BackgroundTasks, Depends, HTTPException, status, Body, Query
import logging
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


router = APIRouter()


def _process_file_background(file_id: int) -> None:
    # Legacy placeholder kept for compatibility
    return None

def process_file_from_path(file_id: int, file_path: str, filename: str) -> None:
    """Process file from disk path instead of memory content for large files."""
    try:
        from app.workers.file_processor import FileProcessor
        processor = FileProcessor()
        processor.run(file_id, content=None, filename=filename, file_path=file_path)
    except Exception as e:
        import logging
        log = logging.getLogger("upload")
        log.error("Background processing failed for file %s: %s", file_id, e)


# In-memory upload session registry for chunked uploads (Cloud Run safe within instance)
# Maps upload_id -> { file_id, tmp_path, filename, content_type, received_bytes, created_at }
_multipart_sessions: dict[str, dict] = {}

# Cleanup old sessions (older than 1 hour)
def cleanup_old_sessions():
    import time
    current_time = time.time()
    expired_sessions = []
    for upload_id, session in _multipart_sessions.items():
        created_at = session.get('created_at', current_time)
        if current_time - created_at > 3600:  # 1 hour
            expired_sessions.append(upload_id)
    
    for upload_id in expired_sessions:
        try:
            import os
            tmp_path = _multipart_sessions[upload_id].get('tmp_path')
            if tmp_path and os.path.exists(tmp_path):
                os.remove(tmp_path)
        except Exception:
            pass
        finally:
            _multipart_sessions.pop(upload_id, None)


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
    sess = _multipart_sessions.get(upload_id)
    if not sess:
        raise HTTPException(status_code=404, detail="Upload session not found")
    try:
        # Append bytes to tmp file
        with open(sess["tmp_path"], "ab") as f:
            f.write(body)
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
    
    sess = _multipart_sessions.get(upload_id)
    if not sess:
        # Try to find the file by upload_id pattern or provide better error
        raise HTTPException(status_code=404, detail=f"Upload session not found. Session may have expired. Please try uploading again.")
    
    try:
        file_id = sess["file_id"]
        tmp_path = sess["tmp_path"]
        filename = sess["filename"]
        content_type = sess["content_type"]
        obj = db.get(FileModel, file_id)
        if not obj:
            raise HTTPException(status_code=404, detail="File not found")
        
        # Read content from temp file efficiently
        try:
            import os
            size_bytes = os.path.getsize(tmp_path)
            # For large files, don't read the entire content into memory
            # Just update the file record and let background processing handle the actual content
            if size_bytes > 100 * 1024 * 1024:  # 100MB threshold for very large files
                # For very large files, skip immediate Supabase upload and process directly
                obj.storage_path = None
                obj.size_bytes = size_bytes
                obj.status = "processing"
                db.add(obj)
                db.commit()
                db.refresh(obj)
                
                # Start processing with file path instead of content
                try:
                    import threading
                    threading.Thread(target=process_file_from_path, args=(obj.id, tmp_path, filename), daemon=True).start()
                except Exception as thread_err:
                    log = logging.getLogger("upload")
                    log.warning("Thread start failed in multipart complete large file: %s", thread_err)
                
                # Clean up session after successful processing start
                _multipart_sessions.pop(upload_id, None)
                
                return {"file_id": file_id, "status": "processing", "size_bytes": obj.size_bytes}
            else:
                # For smaller files, read content and proceed normally
                with open(tmp_path, "rb") as f:
                    content = f.read()
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Read temp failed: {e}")

        path = f"files/{obj.id}/{filename}"
        
        # Upload to Supabase Storage (same as original upload)
        if settings.SUPABASE_STORAGE_BUCKET and settings.SUPABASE_URL and settings.SUPABASE_SERVICE_ROLE_KEY:
            try:
                # For smaller files, also process directly to avoid Supabase upload hanging
                log = logging.getLogger("upload")
                log.info("Processing file directly to avoid Supabase upload timeout")
                obj.storage_path = None
                obj.size_bytes = size_bytes
                obj.status = "processing"
                db.add(obj)
                db.commit()
                db.refresh(obj)
                # Start processing with content directly
                try:
                    import threading
                    threading.Thread(target=process_file, args=(obj.id, content, filename), daemon=True).start()
                except Exception as thread_err:
                    log.warning("Thread start failed in multipart complete: %s", thread_err)
                
                # Clean up session after successful processing start
                _multipart_sessions.pop(upload_id, None)
                
                return {"file_id": file_id, "status": "processing", "size_bytes": obj.size_bytes}
            except Exception as storage_error:
                # Fallback: process directly with in-memory content
                log = logging.getLogger("upload")
                log.warning("Supabase upload failed in multipart, falling back to direct ingestion: %s", storage_error)
                obj.storage_path = None
                obj.size_bytes = size_bytes
                obj.status = "processing"
                db.add(obj)
                db.commit()
                db.refresh(obj)
                # Start processing with content directly
                try:
                    import threading
                    threading.Thread(target=process_file, args=(obj.id, content, filename), daemon=True).start()
                except Exception as thread_err:
                    log.warning("Thread start failed in multipart complete fallback: %s", thread_err)
                
                # Clean up session after successful processing start
                _multipart_sessions.pop(upload_id, None)
                
                return {"file_id": file_id, "status": "processing", "size_bytes": obj.size_bytes}
        else:
            # No Supabase config, process directly
            obj.storage_path = None
            obj.size_bytes = size_bytes
            obj.status = "processing"
            db.add(obj)
            db.commit()
            db.refresh(obj)
            # Start processing with content directly
            try:
                import threading
                threading.Thread(target=process_file, args=(obj.id, content, filename), daemon=True).start()
            except Exception as thread_err:
                log = logging.getLogger("upload")
                log.warning("Thread start failed in multipart complete no-supabase: %s", thread_err)
            
            # Clean up session after successful processing start
            _multipart_sessions.pop(upload_id, None)
            
            return {"file_id": file_id, "status": "processing", "size_bytes": obj.size_bytes}

        # Cleanup temp file
        try:
            import os
            os.remove(tmp_path)
        except Exception:
            pass
    except HTTPException:
        raise
    except Exception as e:
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
    Unified upload endpoint that handles ALL file sizes intelligently (0.1MB to 500MB+).
    
    File Size Routing:
    - 0.1MB - 5MB: Direct upload (fast, simple)
    - 5MB - 100MB: Chunked upload with 20MB chunks (balanced)
    - 100MB - 500MB+: Optimized chunked upload with larger chunks
    """
    log = logging.getLogger("upload")
    try:
        # Read file content
        content = await file.read()
        if not content:
            raise ValueError("empty file body")
        
        file_size = len(content)
        log.info(f"Unified upload: {file.filename}, size: {file_size / (1024*1024):.1f}MB")
        
        # Intelligent file size routing (adjusted for Excel compression)
        if file_size >= 2 * 1024 * 1024:  # 2MB threshold for Excel files
            # Determine optimal chunk size based on file size (adjusted for Excel compression)
            if file_size >= 10 * 1024 * 1024:  # 10MB+ (very large for Excel)
                chunk_size = 50 * 1024 * 1024  # 50MB chunks for very large files
                log.info(f"Very large file detected ({file_size / (1024*1024):.1f}MB), using 50MB chunks")
            else:
                chunk_size = 20 * 1024 * 1024  # 20MB chunks for medium files
                log.info(f"Large file detected ({file_size / (1024*1024):.1f}MB), using 20MB chunks")
            
            return {
                "requires_chunked_upload": True,
                "message": f"File is large ({file_size / (1024*1024):.1f}MB) and requires chunked upload",
                "max_chunk_size": chunk_size,
                "file_size": file_size,
                "estimated_chunks": (file_size + chunk_size - 1) // chunk_size,
                "instructions": "Use /multipart/init, /multipart/part, /multipart/complete endpoints"
            }
        
        # For smaller files (0.1MB - 5MB), process directly
        log.info(f"Processing file directly: {file.filename}, size: {file_size / (1024*1024):.1f}MB")
        
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

        # Process file directly (no Supabase upload to avoid timeouts)
        try:
            import threading
            threading.Thread(target=process_file, args=(obj.id, content, file.filename), daemon=True).start()
            log.info(f"Started background processing for file {obj.id}")
        except Exception as thread_err:
            log.warning("Thread start failed, falling back to BackgroundTasks: %s", thread_err)
            background.add_task(process_file, obj.id, content, file.filename)
        
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


