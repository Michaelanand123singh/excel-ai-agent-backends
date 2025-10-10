#!/usr/bin/env python3
"""
Elasticsearch-powered ultra-fast bulk search endpoint
"""

import time
import logging
import json
import hashlib
from typing import Dict, Any, List
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from app.core.database import get_db
from app.api.dependencies.auth import get_current_user
from app.models.database.user import User
from app.services.search_engine.elasticsearch_client import ElasticsearchBulkSearch
from app.services.search_engine.data_sync import DataSyncService
from app.services.cache.ultra_fast_cache_manager import ultra_fast_cache

logger = logging.getLogger(__name__)
router = APIRouter()

@router.post("/search-part-bulk-elasticsearch")
async def search_part_number_bulk_elasticsearch(
    req: Dict[str, Any],
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user)
):
    """
    Ultra-fast bulk search using Elasticsearch with Redis caching
    Target: 10K parts in under 5 seconds with 90% cache hit rate
    """
    try:
        file_id = req.get('file_id')
        part_numbers = req.get('part_numbers', [])
        page = req.get('page', 1)
        page_size = req.get('page_size', 50)
        show_all = req.get('show_all', False)
        search_mode = req.get('search_mode', 'hybrid')
        
        if not file_id:
            raise HTTPException(status_code=400, detail="File ID is required")
        
        if not part_numbers:
            raise HTTPException(status_code=400, detail="Part numbers are required")
        
        # Create cache key for this search
        cache_key = ultra_fast_cache.get_cache_key(
            "bulk_search_elasticsearch",
            file_id=file_id,
            parts_hash=hashlib.md5(json.dumps(sorted(part_numbers)).encode()).hexdigest(),
            search_mode=search_mode,
            show_all=show_all,
            page_size=page_size
        )
        
        # Check Redis cache first
        logger.info(f"🔍 Checking cache for bulk search: {len(part_numbers)} parts")
        cached_result = ultra_fast_cache.get_cached_bulk_search_result(
            file_id=file_id,
            part_numbers=part_numbers,
            search_mode=search_mode
        )
        
        if cached_result:
            logger.info(f"✅ Cache HIT! Returning cached results for {len(part_numbers)} parts")
            cached_result["cached"] = True
            cached_result["cache_hit"] = True
            cached_result["search_engine"] = "elasticsearch_cached"
            return cached_result
        
        logger.info(f"❌ Cache MISS! Performing Elasticsearch search for {len(part_numbers)} parts")
        
        # Initialize Elasticsearch client
        es_client = ElasticsearchBulkSearch()
        
        if not es_client.is_available():
            # Fallback to PostgreSQL if Elasticsearch is not available
            logger.warning("Elasticsearch not available, falling back to PostgreSQL")
            from app.api.v1.endpoints.query_optimized import search_part_number_bulk_ultra_fast
            return await search_part_number_bulk_ultra_fast(req, None, db, user)
        
        # Perform Elasticsearch bulk search
        start_time = time.perf_counter()
        
        # Determine per-part limit based on request
        if show_all:
            per_part_limit = 100000
        else:
            # Use requested page_size when provided, fallback to 50
            try:
                per_part_limit = max(1, int(page_size))
            except Exception:
                per_part_limit = 500000

        result = es_client.bulk_search(
            part_numbers=part_numbers,
            file_id=file_id,
            limit_per_part=per_part_limit
        )
        
        total_time = (time.perf_counter() - start_time) * 1000
        
        # Add performance metrics
        result.update({
            "total_time_ms": total_time,
            "performance_rating": "excellent" if total_time < 5000 else "good" if total_time < 10000 else "acceptable",
            "search_engine": "elasticsearch",
            "cached": False,
            "cache_hit": False
        })
        
        # Cache the result for 30 minutes
        logger.info(f"💾 Caching search results for {len(part_numbers)} parts")
        cache_success = ultra_fast_cache.cache_bulk_search_result(
            file_id=file_id,
            part_numbers=part_numbers,
            search_mode=search_mode,
            result=result
        )
        
        if cache_success:
            logger.info(f"✅ Successfully cached search results")
        else:
            logger.warning(f"⚠️ Failed to cache search results")
        
        logger.info(f"✅ Elasticsearch bulk search completed: {len(part_numbers)} parts in {total_time:.2f}ms")
        
        return result
        
    except Exception as e:
        logger.error(f"❌ Elasticsearch bulk search failed: {e}")
        raise HTTPException(status_code=500, detail=f"Elasticsearch search failed: {str(e)}")

@router.post("/sync-to-elasticsearch/{file_id}")
async def sync_file_to_elasticsearch(
    file_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user)
):
    """Sync a file's data to Elasticsearch"""
    try:
        sync_service = DataSyncService()
        success = sync_service.sync_file_to_elasticsearch(file_id)
        
        if success:
            return {"message": f"Successfully synced file {file_id} to Elasticsearch", "status": "success"}
        else:
            raise HTTPException(status_code=500, detail="Failed to sync file to Elasticsearch")
            
    except Exception as e:
        logger.error(f"❌ Sync failed for file {file_id}: {e}")
        raise HTTPException(status_code=500, detail=f"Sync failed: {str(e)}")

@router.post("/sync-all-to-elasticsearch")
async def sync_all_files_to_elasticsearch(
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user)
):
    """Sync all files to Elasticsearch"""
    try:
        sync_service = DataSyncService()
        results = sync_service.sync_all_files()
        
        return {
            "message": "Bulk sync completed",
            "results": results
        }
        
    except Exception as e:
        logger.error(f"❌ Bulk sync failed: {e}")
        raise HTTPException(status_code=500, detail=f"Bulk sync failed: {str(e)}")

@router.get("/elasticsearch-status")
async def get_elasticsearch_status(
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user)
):
    """Get Elasticsearch status and sync information"""
    try:
        sync_service = DataSyncService()
        status = sync_service.get_sync_status()
        
        return status
        
    except Exception as e:
        logger.error(f"❌ Failed to get Elasticsearch status: {e}")
        raise HTTPException(status_code=500, detail=f"Status check failed: {str(e)}")

@router.delete("/elasticsearch-index")
async def delete_elasticsearch_index(
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user)
):
    """Delete Elasticsearch index (for testing/reset)"""
    try:
        es_client = ElasticsearchBulkSearch()
        
        if not es_client.is_available():
            raise HTTPException(status_code=503, detail="Elasticsearch not available")
        
        success = es_client.delete_index()
        
        if success:
            return {"message": "Elasticsearch index deleted successfully", "status": "success"}
        else:
            raise HTTPException(status_code=500, detail="Failed to delete Elasticsearch index")
            
    except Exception as e:
        logger.error(f"❌ Failed to delete Elasticsearch index: {e}")
        raise HTTPException(status_code=500, detail=f"Delete failed: {str(e)}")

