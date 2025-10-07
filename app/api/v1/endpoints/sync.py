"""
Data Sync Endpoints for Elasticsearch synchronization
"""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from typing import Dict, Any

from app.core.database import get_db
from app.api.dependencies.auth import get_current_user
from app.services.search_engine.data_sync_service import DataSyncService

router = APIRouter()


@router.post("/sync-file/{file_id}")
async def sync_file_to_elasticsearch(
    file_id: int,
    db: Session = Depends(get_db),
    user=Depends(get_current_user)
) -> Dict[str, Any]:
    """
    Sync a specific file's data from PostgreSQL to Elasticsearch
    """
    try:
        sync_service = DataSyncService()
        success = sync_service.sync_file_to_elasticsearch(file_id)
        
        if success:
            return {
                "message": f"Successfully synced file {file_id} to Elasticsearch",
                "file_id": file_id,
                "status": "success"
            }
        else:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Failed to sync file {file_id} to Elasticsearch"
            )
            
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Sync failed: {str(e)}"
        )


@router.post("/sync-all")
async def sync_all_files_to_elasticsearch(
    db: Session = Depends(get_db),
    user=Depends(get_current_user)
) -> Dict[str, Any]:
    """
    Sync all files from PostgreSQL to Elasticsearch
    """
    try:
        sync_service = DataSyncService()
        results = sync_service.sync_all_files()
        
        if "error" in results:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=results["error"]
            )
        
        return {
            "message": f"Sync completed: {results['synced_files']} successful, {results['failed_files']} failed",
            "results": results
        }
        
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Sync failed: {str(e)}"
        )


@router.get("/sync-status")
async def get_sync_status(
    db: Session = Depends(get_db),
    user=Depends(get_current_user)
) -> Dict[str, Any]:
    """
    Get the current sync status between PostgreSQL and Elasticsearch
    """
    try:
        sync_service = DataSyncService()
        status_info = sync_service.get_sync_status()
        
        return {
            "message": "Sync status retrieved successfully",
            "status": status_info
        }
        
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get sync status: {str(e)}"
        )

