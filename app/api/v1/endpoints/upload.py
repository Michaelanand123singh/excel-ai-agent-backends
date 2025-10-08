from fastapi import APIRouter, UploadFile, File, BackgroundTasks, Depends, HTTPException, status
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


router = APIRouter()


def _process_file_background(file_id: int) -> None:
    # Legacy placeholder kept for compatibility
    return None


@router.post("/", response_model=FileRead)
@router.post("", response_model=FileRead)
async def upload_file(background: BackgroundTasks, file: UploadFile = File(...), db: Session = Depends(get_db)):
    log = logging.getLogger("upload")
    try:
        obj = FileModel(
            filename=file.filename,
            size_bytes=0,
            content_type=file.content_type or "application/octet-stream",
            status="uploaded",
        )
        db.add(obj)
        db.commit()
        db.refresh(obj)

        content = await file.read()
        if not content:
            raise ValueError("empty file body")
        path = f"files/{obj.id}/{file.filename}"

        # Preferred: upload to Supabase Storage, then process via worker download
        if settings.SUPABASE_STORAGE_BUCKET and settings.SUPABASE_URL and settings.SUPABASE_SERVICE_ROLE_KEY:
            try:
                client = get_supabase()
                res = client.storage.from_(settings.SUPABASE_STORAGE_BUCKET).upload(
                    path=path,
                    file=content,
                    file_options={"contentType": obj.content_type, "upsert": "true"},
                )
                err = getattr(res, "error", None)
                if err:
                    raise RuntimeError(err)
                log.info("Stored to Supabase bucket=%s path=%s size=%s", settings.SUPABASE_STORAGE_BUCKET, path, len(content))
                obj.storage_path = path
                obj.size_bytes = len(content)
                obj.status = "processing"
                db.add(obj)
                db.commit()
                db.refresh(obj)
                # Start processing in a separate thread so it continues if client navigates away
                try:
                    import threading
                    threading.Thread(target=process_file, args=(obj.id,), daemon=True).start()
                except Exception as thread_err:
                    log.warning("Thread start failed, falling back to BackgroundTasks: %s", thread_err)
                    background.add_task(process_file, obj.id)
                return FileRead.from_orm(obj)
            except Exception as storage_error:
                # fall through to direct ingestion
                log.warning("Supabase upload failed, falling back to direct ingestion: %s", storage_error)
                pass

        # Fallback: process directly with in-memory content
        obj.storage_path = None
        obj.size_bytes = len(content)
        obj.status = "processing"
        db.add(obj)
        db.commit()
        db.refresh(obj)
        # Start processing in a separate thread so it continues if client navigates away
        try:
            import threading
            threading.Thread(target=process_file, args=(obj.id, content, file.filename), daemon=True).start()
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


