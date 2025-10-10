#!/usr/bin/env python3
"""
All Files Search API - Search across all synced files using Elasticsearch
"""

import time
import logging
import json
from typing import Dict, Any, List
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form
from sqlalchemy.orm import Session
from sqlalchemy import text
from app.core.database import get_db
from app.api.dependencies.auth import get_current_user
from app.models.database.user import User
from app.services.search_engine.elasticsearch_client import ElasticsearchBulkSearch
from app.services.cache.ultra_fast_cache_manager import ultra_fast_cache
from app.services.data_processor.bulk_excel_parser import BulkExcelParser
import hashlib

logger = logging.getLogger(__name__)
router = APIRouter()

@router.post("/search-all-files-text")
async def search_all_files_text(
    req: Dict[str, Any],
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user)
):
    """
    Search part numbers across ALL synced files using Elasticsearch
    Supports up to 50K part numbers
    """
    try:
        part_numbers = req.get('part_numbers', [])
        search_mode = req.get('search_mode', 'hybrid')
        page = req.get('page', 1)
        page_size = req.get('page_size', 100)
        
        if not part_numbers:
            return {
                "results": {},
                "total_parts": 0,
                "total_matches": 0,
                "search_engine": "elasticsearch_all_files",
                "latency_ms": 0,
                "cached": False
            }
        
        # Normalize and de-dup part numbers
        normalized = []
        seen = set()
        for pn in part_numbers:
            v = (pn or "").strip()
            if len(v) >= 2 and v.lower() not in seen:
                seen.add(v.lower())
                normalized.append(v)
        
        # Limit to 50K parts as requested
        if len(normalized) > 50000:
            normalized = normalized[:50000]
        
        if not normalized:
            return {
                "results": {},
                "total_parts": 0,
                "total_matches": 0,
                "search_engine": "elasticsearch_all_files",
                "latency_ms": 0,
                "cached": False
            }
        
        # Create cache key for all-files search
        cache_key = ultra_fast_cache.get_cache_key(
            "all_files_search",
            parts_hash=hashlib.md5(json.dumps(sorted(normalized)).encode()).hexdigest(),
            search_mode=search_mode,
            page=page,
            page_size=page_size
        )
        
        # Check Redis cache first
        logger.info(f"🔍 Checking cache for all-files search: {len(normalized)} parts")
        cached_result = ultra_fast_cache.get_cached_bulk_search_result(
            file_id=None,  # No specific file for all-files search
            part_numbers=normalized,
            search_mode=search_mode
        )
        
        if cached_result:
            logger.info(f"✅ Cache HIT! Returning cached all-files results for {len(normalized)} parts")
            cached_result["cached"] = True
            cached_result["cache_hit"] = True
            cached_result["search_engine"] = "elasticsearch_all_files_cached"
            return cached_result
        
        logger.info(f"❌ Cache MISS! Performing all-files Elasticsearch search for {len(normalized)} parts")
        
        # Get all synced files
        synced_files = db.execute("""
            SELECT id, filename, elasticsearch_synced 
            FROM file 
            WHERE elasticsearch_synced = true 
            ORDER BY id DESC
        """).fetchall()
        
        if not synced_files:
            return {
                "results": {},
                "total_parts": len(normalized),
                "total_matches": 0,
                "search_engine": "elasticsearch_all_files",
                "latency_ms": 0,
                "cached": False,
                "message": "No files are synced to Elasticsearch yet"
            }
        
        logger.info(f"📁 Found {len(synced_files)} synced files for all-files search")
        
        # Use Elasticsearch for all-files search
        es_client = ElasticsearchBulkSearch()
        if not es_client.is_available():
            raise HTTPException(status_code=503, detail="Elasticsearch not available")
        
        start_time = time.perf_counter()
        
        # Search across all files (no file_id filter)
        result = es_client.search_bulk_parts_all_files(
            part_numbers=normalized,
            search_mode=search_mode,
            page=page,
            page_size=page_size
        )
        
        # Add metadata
        result["search_engine"] = "elasticsearch_all_files"
        result["cached"] = False
        result["cache_hit"] = False
        result["synced_files_count"] = len(synced_files)
        result["latency_ms"] = int((time.perf_counter() - start_time) * 1000)
        
        # Cache the result for 30 minutes
        logger.info(f"💾 Caching all-files search results for {len(normalized)} parts")
        cache_success = ultra_fast_cache.cache_bulk_search_result(
            file_id=None,
            part_numbers=normalized,
            search_mode=search_mode,
            result=result
        )
        
        return result
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"❌ All-files search failed: {e}")
        raise HTTPException(status_code=500, detail=f"All-files search failed: {e}")

@router.post("/search-all-files-excel")
async def search_all_files_excel(
    file: UploadFile = File(...),
    search_mode: str = Form("hybrid"),
    page: int = Form(1),
    page_size: int = Form(100),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user)
):
    """
    Search part numbers from Excel file across ALL synced files using Elasticsearch
    """
    try:
        # Parse Excel file
        parser = BulkExcelParser()
        user_parts = parser.parse_excel_file(file)
        
        if not user_parts:
            raise HTTPException(status_code=400, detail="No valid part numbers found in Excel file")
        
        # Extract part numbers
        part_numbers = [p.part_number for p in user_parts if isinstance(p.part_number, str) and p.part_number.strip()]
        
        if not part_numbers:
            raise HTTPException(status_code=400, detail="No valid part numbers found")
        
        # Limit to 50K parts
        if len(part_numbers) > 50000:
            part_numbers = part_numbers[:50000]
        
        # Use the text search endpoint
        return await search_all_files_text({
            "part_numbers": part_numbers,
            "search_mode": search_mode,
            "page": page,
            "page_size": page_size
        }, db, user)
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"❌ All-files Excel search failed: {e}")
        raise HTTPException(status_code=500, detail=f"All-files Excel search failed: {e}")

@router.get("/all-files-status")
async def get_all_files_status(
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user)
):
    """
    Get status of all files and their Elasticsearch sync status
    """
    try:
        files = db.execute(text("""
            SELECT id, filename, status, elasticsearch_synced, elasticsearch_sync_error, rows_count
            FROM file 
            ORDER BY id DESC
        """)).fetchall()
        
        synced_count = sum(1 for f in files if f.elasticsearch_synced)
        total_count = len(files)
        
        return {
            "total_files": total_count,
            "synced_files": synced_count,
            "files": [
                {
                    "id": f.id,
                    "filename": f.filename,
                    "status": f.status,
                    "elasticsearch_synced": f.elasticsearch_synced,
                    "elasticsearch_sync_error": f.elasticsearch_sync_error,
                    "rows_count": f.rows_count
                }
                for f in files
            ]
        }
        
    except Exception as e:
        logger.error(f"❌ Failed to get all-files status: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to get all-files status: {e}")
