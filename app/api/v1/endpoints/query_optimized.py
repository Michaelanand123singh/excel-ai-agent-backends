"""
Optimized Bulk Search API Endpoints
Ultra-fast bulk search implementation leveraging all existing optimizations
Target: 10K parts in 5 seconds
"""

from fastapi import APIRouter, Depends, HTTPException, status, BackgroundTasks
from sqlalchemy.orm import Session
from sqlalchemy import text
import time
import asyncio
import json
import logging
from typing import List, Dict, Any, Optional
from concurrent.futures import ThreadPoolExecutor, as_completed
import redis

from app.api.dependencies.database import get_db
from app.api.dependencies.auth import get_current_user
from app.core.cache import get_redis_client
from app.core.config import get_settings
from app.utils.helpers.part_number import normalize, PART_NUMBER_CONFIG

router = APIRouter()
logger = logging.getLogger(__name__)
settings = get_settings()

# Configuration for ultra-fast bulk search
ULTRA_FAST_CONFIG = {
    "max_parts": 10000,
    "batch_size": 1000,
    "parallel_workers": 8,
    "cache_ttl": 3600,  # 1 hour
    "enable_redis_cache": True,
    "enable_parallel_processing": True,
    "enable_single_query_optimization": True,
    "enable_column_caching": True,
    "enable_result_streaming": True
}


@router.post("/search-part-bulk-ultra-fast")
async def search_part_number_bulk_ultra_fast(
    req: dict,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    user=Depends(get_current_user)
) -> dict:
    """
    Ultra-fast bulk search implementation
    Target: 10K parts in 5 seconds
    """
    start_time = time.perf_counter()
    
    try:
        # Extract request parameters
        file_id = req.get("file_id")
        part_numbers = req.get("part_numbers", [])
        search_mode = req.get("search_mode", "hybrid")
        page = req.get("page", 1)
        page_size = req.get("page_size", 50)
        show_all = req.get("show_all", False)
        
        # Validate inputs
        if not file_id or not part_numbers:
            raise HTTPException(status_code=400, detail="file_id and part_numbers are required")
        
        # Limit to max parts for performance
        part_numbers = part_numbers[:ULTRA_FAST_CONFIG["max_parts"]]
        
        # Check cache first
        cache_key = f"ultra_bulk:{file_id}:{hash(tuple(sorted(part_numbers)))}:{search_mode}:{page}:{page_size}:{show_all}"
        cache = get_redis_client()
        
        if ULTRA_FAST_CONFIG["enable_redis_cache"]:
            cached_result = cache.get(cache_key)
            if cached_result:
                result = json.loads(cached_result)
                result["cached"] = True
                result["latency_ms"] = int((time.perf_counter() - start_time) * 1000)
                return result
        
        # Verify dataset exists
        table_name = f"ds_{file_id}"
        exists = db.execute(text(f"""
            SELECT EXISTS (
                SELECT FROM information_schema.tables 
                WHERE table_name = '{table_name}'
            );
        """)).scalar()
        
        if not exists:
            raise HTTPException(status_code=404, detail=f"Dataset {file_id} not found")
        
        # Get cached column mappings
        column_mappings = await get_cached_column_mappings(db, table_name, cache)
        
        # Execute ultra-fast bulk search
        if ULTRA_FAST_CONFIG["enable_single_query_optimization"]:
            results = await execute_single_query_bulk_search(
                db, table_name, part_numbers, column_mappings, 
                search_mode, page, page_size, show_all
            )
        else:
            results = await execute_parallel_bulk_search(
                db, table_name, part_numbers, column_mappings,
                search_mode, page, page_size, show_all
            )
        
        # Prepare response
        total_time = (time.perf_counter() - start_time) * 1000
        response = {
            "results": results,
            "total_parts": len(part_numbers),
            "latency_ms": int(total_time),
            "cached": False,
            "optimization_used": "ultra_fast_single_query" if ULTRA_FAST_CONFIG["enable_single_query_optimization"] else "parallel_processing"
        }
        
        # Cache results
        if ULTRA_FAST_CONFIG["enable_redis_cache"]:
            try:
                cache.setex(cache_key, ULTRA_FAST_CONFIG["cache_ttl"], json.dumps(response))
            except Exception as e:
                logger.warning(f"Failed to cache ultra-fast results: {e}")
        
        return response
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Ultra-fast bulk search failed: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Ultra-fast search failed: {str(e)}")


async def get_cached_column_mappings(db: Session, table_name: str, cache: redis.Redis) -> Dict[str, str]:
    """Get column mappings with Redis caching"""
    cache_key = f"column_mappings:{table_name}"
    
    if ULTRA_FAST_CONFIG["enable_column_caching"]:
        cached_mappings = cache.get(cache_key)
        if cached_mappings:
            return json.loads(cached_mappings)
    
    # Get all available columns
    columns_result = db.execute(text(f"""
        SELECT column_name, data_type 
        FROM information_schema.columns 
        WHERE table_name = '{table_name}' 
        ORDER BY ordinal_position
    """)).fetchall()
    
    available_columns = {row[0]: row[1] for row in columns_result}
    
    # Define column mappings with fallbacks
    column_mappings = {
        'company_name': ['Potential Buyer 1', 'Company Name', 'Buyer 1', 'Company'],
        'contact_details': ['Potential Buyer 1 Contact Details', 'Contact Details', 'Contact', 'Phone'],
        'email': ['Potential Buyer 1 email id', 'Email', 'Email ID', 'Email Address'],
        'quantity': ['Quantity', 'Qty', 'Amount'],
        'unit_price': ['Unit_Price', 'Unit Price', 'Price', 'Cost'],
        'item_description': ['Item_Description', 'Item Description', 'Description', 'Product'],
        'part_number': ['part_number', 'Part Number', 'Part No', 'Part'],
        'uqc': ['UQC', 'Unit', 'Unit of Measure'],
        'secondary_buyer': ['Potential Buyer 2', 'Buyer 2', 'Secondary Buyer'],
        'secondary_buyer_contact': ['Potential Buyer 2 Contact Details', 'Buyer 2 Contact', 'Secondary Contact'],
        'secondary_buyer_email': ['Potential Buyer 2 email id', 'Buyer 2 Email', 'Secondary Email']
    }
    
    # Find best matches
    final_mappings = {}
    for alias, possible_columns in column_mappings.items():
        found_column = None
        for col in possible_columns:
            if col in available_columns:
                found_column = col
                break
        
        final_mappings[alias] = found_column or "NULL"
    
    # Cache the mappings
    if ULTRA_FAST_CONFIG["enable_column_caching"]:
        try:
            cache.setex(cache_key, 3600, json.dumps(final_mappings))  # Cache for 1 hour
        except Exception as e:
            logger.warning(f"Failed to cache column mappings: {e}")
    
    return final_mappings


async def execute_single_query_bulk_search(
    db: Session, table_name: str, part_numbers: List[str], 
    column_mappings: Dict[str, str], search_mode: str, 
    page: int, page_size: int, show_all: bool
) -> Dict[str, Any]:
    """
    Ultra-optimized single query approach for bulk search
    Uses PostgreSQL arrays and vectorized operations
    """
    
    # Build dynamic SELECT statement
    select_parts = []
    for alias, column in column_mappings.items():
        if column != "NULL":
            select_parts.append(f'"{column}" as {alias}')
        else:
            select_parts.append(f'NULL as {alias}')
    
    select_clause = ', '.join(select_parts)
    
    # Start timing
    start_time = time.perf_counter()
    
    # For large batches (>20 parts), use ultra-optimized approach
    if len(part_numbers) > 20:
        # Use a much simpler approach: exact matches first, then description matches
        all_results = []
        
        # Step 1: Get exact matches (fastest)
        exact_parts_str = "', '".join(part_numbers)
        exact_query = f"""
            SELECT 
                "part_number" as search_part_number,
                {select_clause},
                'exact_part' as match_type,
                1.0 as similarity_score
            FROM {table_name}
            WHERE LOWER("part_number") IN ('{exact_parts_str.lower()}')
        """
        
        exact_results = db.execute(text(exact_query)).fetchall()
        all_results.extend(exact_results)
        
        # Step 2: Get description matches for parts not found in exact matches
        found_parts = {row[0].lower() for row in exact_results}
        remaining_parts = [p for p in part_numbers if p.lower() not in found_parts]
        
        if remaining_parts:
            # Process remaining parts in smaller batches
            batch_size = 10
            for i in range(0, len(remaining_parts), batch_size):
                batch_parts = remaining_parts[i:i + batch_size]
                
                # Create simple description match query
                desc_queries = []
                for part in batch_parts:
                    desc_queries.append(f"""
                        SELECT 
                            '{part}' as search_part_number,
                            {select_clause},
                            'description_match' as match_type,
                            similarity(lower(CAST("Item_Description" AS TEXT)), lower('{part}')) as similarity_score
                        FROM {table_name}
                        WHERE CAST("Item_Description" AS TEXT) ILIKE '%' || '{part}' || '%'
                        LIMIT 3
                    """)
                
                batch_query = " UNION ALL ".join(desc_queries)
                batch_results = db.execute(text(batch_query)).fetchall()
                all_results.extend(batch_results)
        
        # Group results by part number and limit to top 3 per part
        from collections import defaultdict
        grouped_by_part = defaultdict(list)
        
        for row in all_results:
            part_num = row[0]  # search_part_number
            grouped_by_part[part_num].append(row)
        
        # Sort and limit results for each part
        processed_results = []
        for part_num, part_rows in grouped_by_part.items():
            # Sort by match type priority and similarity
            sorted_rows = sorted(part_rows, key=lambda x: (
                1 if x[2] == 'exact_part' else 2 if x[2] == 'description_match' else 3,
                -x[3] if x[3] is not None else 0,  # similarity_score (descending)
                x[7] if x[7] is not None else 0    # unit_price (ascending)
            ))
            
            # Take top 3 results
            processed_results.extend(sorted_rows[:3])
        
        results = processed_results
    else:
        # For smaller batches, use single UNION ALL query
        union_queries = []
        for part in part_numbers:
            union_queries.append(f"""
                SELECT 
                    '{part}' as search_part_number,
                    {select_clause},
                    CASE 
                        WHEN LOWER("part_number") = LOWER('{part}') THEN 'exact_part'
                        WHEN LOWER(CAST("Item_Description" AS TEXT)) ILIKE '%' || LOWER('{part}') || '%' THEN 'description_match'
                        WHEN similarity(lower(CAST("Item_Description" AS TEXT)), lower('{part}')) >= 0.6 THEN 'fuzzy_match'
                        ELSE 'no_match'
                    END as match_type,
                    similarity(lower(CAST("Item_Description" AS TEXT)), lower('{part}')) as similarity_score
                FROM {table_name}
                WHERE 
                    LOWER("part_number") = LOWER('{part}')
                    OR CAST("Item_Description" AS TEXT) ILIKE '%' || '{part}' || '%'
                    OR similarity(lower(CAST("Item_Description" AS TEXT)), lower('{part}')) >= 0.6
            """)
        
        base_query = " UNION ALL ".join(union_queries)
        optimized_query = f"""
            WITH all_results AS (
                {base_query}
            ),
            grouped_results AS (
                SELECT 
                    search_part_number,
                    match_type,
                    similarity_score,
                    company_name,
                    contact_details,
                    email,
                    quantity,
                    unit_price,
                    item_description,
                    part_number,
                    uqc,
                    secondary_buyer,
                    secondary_buyer_contact,
                    secondary_buyer_email,
                    ROW_NUMBER() OVER (PARTITION BY search_part_number ORDER BY 
                        CASE match_type 
                            WHEN 'exact_part' THEN 1
                            WHEN 'description_match' THEN 2
                            WHEN 'fuzzy_match' THEN 3
                            ELSE 4
                        END,
                        similarity_score DESC,
                        unit_price ASC
                    ) as rn
                FROM all_results
            )
            SELECT 
                search_part_number,
                match_type,
                similarity_score,
                company_name,
                contact_details,
                email,
                quantity,
                unit_price,
                item_description,
                part_number,
                uqc,
                secondary_buyer,
                secondary_buyer_contact,
                secondary_buyer_email
            FROM grouped_results
            WHERE rn <= 3
            ORDER BY search_part_number, rn
        """
        results = db.execute(text(optimized_query)).fetchall()
    
    # Query execution time is already measured above
    query_time = (time.perf_counter() - start_time) * 1000
    
    # Group results by part number
    grouped_results = {}
    for row in results:
        part_num = row[0]  # search_part_number
        if part_num not in grouped_results:
            grouped_results[part_num] = {
                "part_number": part_num,
                "total_matches": 0,
                "companies": [],
                "message": "",
                "cached": False,
                "latency_ms": int(query_time),
                "search_mode": search_mode,
                "match_type": "bulk_optimized"
            }
        
        # Add company data
        # Column order: search_part_number, match_type, similarity_score, company_name, contact_details, email, quantity, unit_price, item_description, part_number, uqc, secondary_buyer, secondary_buyer_contact, secondary_buyer_email
        company_data = {
            "company_name": row[3] or "N/A",
            "contact_details": row[4] or "N/A",
            "email": row[5] or "N/A",
            "quantity": int(row[6]) if row[6] is not None else 0,
            "unit_price": float(row[7]) if row[7] is not None else 0.0,
            "item_description": row[8] or "N/A",
            "part_number": row[9] or "N/A",
            "uqc": row[10] or "N/A",
            "secondary_buyer": row[11] or "N/A",
            "secondary_buyer_contact": row[12] or "N/A",
            "secondary_buyer_email": row[13] or "N/A"
        }
        
        grouped_results[part_num]["companies"].append(company_data)
        grouped_results[part_num]["total_matches"] += 1
    
    # Add summary messages
    for part_num, result in grouped_results.items():
        if result["total_matches"] > 0:
            prices = [c["unit_price"] for c in result["companies"] if c["unit_price"] > 0]
            if prices:
                min_price = min(prices)
                max_price = max(prices)
                result["message"] = f"Found {result['total_matches']} companies with part number '{part_num}'. Price range: ₹{min_price:.2f} - ₹{max_price:.2f}"
            else:
                result["message"] = f"Found {result['total_matches']} companies with part number '{part_num}'"
        else:
            result["message"] = f"No matches found for part number '{part_num}'"
    
    return grouped_results


async def execute_parallel_bulk_search(
    db: Session, table_name: str, part_numbers: List[str],
    column_mappings: Dict[str, str], search_mode: str,
    page: int, page_size: int, show_all: bool
) -> Dict[str, Any]:
    """
    Parallel processing approach for bulk search
    Uses ThreadPoolExecutor for concurrent processing
    """
    
    # Split part numbers into batches
    batch_size = ULTRA_FAST_CONFIG["batch_size"]
    batches = [part_numbers[i:i + batch_size] for i in range(0, len(part_numbers), batch_size)]
    
    # Process batches in parallel
    results = {}
    
    with ThreadPoolExecutor(max_workers=ULTRA_FAST_CONFIG["parallel_workers"]) as executor:
        # Submit all batches
        future_to_batch = {
            executor.submit(process_batch_parallel, db, table_name, batch, column_mappings, search_mode, page, page_size, show_all): batch
            for batch in batches
        }
        
        # Collect results as they complete
        for future in as_completed(future_to_batch):
            try:
                batch_results = future.result()
                results.update(batch_results)
            except Exception as e:
                logger.error(f"Batch processing failed: {e}")
                # Add error results for this batch
                batch = future_to_batch[future]
                for part_num in batch:
                    results[part_num] = {
                        "part_number": part_num,
                        "total_matches": 0,
                        "companies": [],
                        "message": f"Search failed: {str(e)}",
                        "cached": False,
                        "latency_ms": 0,
                        "error": True
                    }
    
    return results


def process_batch_parallel(
    db: Session, table_name: str, part_numbers: List[str],
    column_mappings: Dict[str, str], search_mode: str,
    page: int, page_size: int, show_all: bool
) -> Dict[str, Any]:
    """
    Process a batch of part numbers in parallel
    """
    results = {}
    
    for part_num in part_numbers:
        try:
            # Use the existing single search logic but optimized
            result = search_single_part_optimized(
                db, table_name, part_num, column_mappings, 
                search_mode, page, page_size, show_all
            )
            results[part_num] = result
        except Exception as e:
            results[part_num] = {
                "part_number": part_num,
                "total_matches": 0,
                "companies": [],
                "message": f"Search failed: {str(e)}",
                "cached": False,
                "latency_ms": 0,
                "error": True
            }
    
    return results


def search_single_part_optimized(
    db: Session, table_name: str, part_number: str,
    column_mappings: Dict[str, str], search_mode: str,
    page: int, page_size: int, show_all: bool
) -> Dict[str, Any]:
    """
    Optimized single part search using cached column mappings
    """
    start_time = time.perf_counter()
    
    # Build dynamic SELECT statement
    select_parts = []
    for alias, column in column_mappings.items():
        if column != "NULL":
            select_parts.append(f'"{column}" as {alias}')
        else:
            select_parts.append(f'NULL as {alias}')
    
    select_clause = ', '.join(select_parts)
    
    # Build optimized query
    q_original = part_number.strip()
    q_no_seps = normalize(q_original, 2)
    q_alnum = normalize(q_original, 3)
    
    # Exact match query
    exact_query = f"""
        SELECT {select_clause}
        FROM {table_name}
        WHERE LOWER("part_number") = LOWER(:q_original)
        ORDER BY "Unit_Price" ASC
        LIMIT :limit
    """
    
    # Execute exact match first
    try:
        results = db.execute(text(exact_query), {
            "q_original": q_original,
            "limit": page_size if not show_all else 1000
        }).fetchall()
        
        if results:
            companies = []
            for row in results:
                company = {
                    "company_name": row[0] or "N/A",
                    "contact_details": row[1] or "N/A",
                    "email": row[2] or "N/A",
                    "quantity": int(row[3]) if row[3] is not None else 0,
                    "unit_price": float(row[4]) if row[4] is not None else 0.0,
                    "item_description": row[5] or "N/A",
                    "part_number": row[6] or "N/A",
                    "uqc": row[7] or "N/A",
                    "secondary_buyer": row[8] or "N/A",
                    "secondary_buyer_contact": row[9] or "N/A",
                    "secondary_buyer_email": row[10] or "N/A"
                }
                companies.append(company)
            
            # Calculate price range
            prices = [c["unit_price"] for c in companies if c["unit_price"] > 0]
            min_price = min(prices) if prices else 0.0
            max_price = max(prices) if prices else 0.0
            
            return {
                "part_number": part_number,
                "total_matches": len(companies),
                "companies": companies,
                "message": f"Found {len(companies)} companies with part number '{part_number}'. Price range: ₹{min_price:.2f} - ₹{max_price:.2f}",
                "cached": False,
                "latency_ms": int((time.perf_counter() - start_time) * 1000),
                "search_mode": search_mode,
                "match_type": "exact"
            }
    except Exception as e:
        logger.warning(f"Exact search failed for {part_number}: {e}")
    
    # Fallback to fuzzy search if exact match fails
    try:
        fuzzy_query = f"""
            SELECT {select_clause}, similarity(lower(CAST("Item_Description" AS TEXT)), lower(:q_original)) as sim_score
            FROM {table_name}
            WHERE similarity(lower(CAST("Item_Description" AS TEXT)), lower(:q_original)) >= 0.6
            ORDER BY sim_score DESC, "Unit_Price" ASC
            LIMIT :limit
        """
        
        results = db.execute(text(fuzzy_query), {
            "q_original": q_original,
            "limit": page_size if not show_all else 1000
        }).fetchall()
        
        if results:
            companies = []
            for row in results:
                company = {
                    "company_name": row[0] or "N/A",
                    "contact_details": row[1] or "N/A",
                    "email": row[2] or "N/A",
                    "quantity": int(row[3]) if row[3] is not None else 0,
                    "unit_price": float(row[4]) if row[4] is not None else 0.0,
                    "item_description": row[5] or "N/A",
                    "part_number": row[6] or "N/A",
                    "uqc": row[7] or "N/A",
                    "secondary_buyer": row[8] or "N/A",
                    "secondary_buyer_contact": row[9] or "N/A",
                    "secondary_buyer_email": row[10] or "N/A"
                }
                companies.append(company)
            
            return {
                "part_number": part_number,
                "total_matches": len(companies),
                "companies": companies,
                "message": f"Found {len(companies)} companies with part number '{part_number}' (fuzzy match)",
                "cached": False,
                "latency_ms": int((time.perf_counter() - start_time) * 1000),
                "search_mode": search_mode,
                "match_type": "fuzzy"
            }
    except Exception as e:
        logger.warning(f"Fuzzy search failed for {part_number}: {e}")
    
    # No matches found
    return {
        "part_number": part_number,
        "total_matches": 0,
        "companies": [],
        "message": f"No matches found for part number '{part_number}'",
        "cached": False,
        "latency_ms": int((time.perf_counter() - start_time) * 1000),
        "search_mode": search_mode,
        "match_type": "none"
    }


@router.get("/bulk-search-performance")
async def get_bulk_search_performance(
    db: Session = Depends(get_db),
    user=Depends(get_current_user)
) -> dict:
    """Get performance metrics for bulk search operations"""
    
    cache = get_redis_client()
    
    try:
        # Get cache statistics
        cache_info = cache.info()
        
        # Get database statistics
        db_stats = db.execute(text("""
            SELECT 
                schemaname,
                tablename,
                n_tup_ins as inserts,
                n_tup_upd as updates,
                n_tup_del as deletes,
                n_live_tup as live_tuples,
                n_dead_tup as dead_tuples
            FROM pg_stat_user_tables 
            WHERE tablename LIKE 'ds_%'
            ORDER BY n_live_tup DESC
            LIMIT 10
        """)).fetchall()
        
        return {
            "cache_performance": {
                "connected_clients": cache_info.get("connected_clients", 0),
                "used_memory": cache_info.get("used_memory_human", "0B"),
                "keyspace_hits": cache_info.get("keyspace_hits", 0),
                "keyspace_misses": cache_info.get("keyspace_misses", 0),
                "hit_rate": cache_info.get("keyspace_hits", 0) / max(cache_info.get("keyspace_hits", 0) + cache_info.get("keyspace_misses", 0), 1)
            },
            "database_performance": {
                "table_stats": [
                    {
                        "table": row[1],
                        "live_tuples": row[5],
                        "dead_tuples": row[6]
                    }
                    for row in db_stats
                ]
            },
            "optimization_config": ULTRA_FAST_CONFIG,
            "status": "operational"
        }
        
    except Exception as e:
        logger.error(f"Failed to get performance metrics: {e}")
        return {
            "error": str(e),
            "status": "degraded"
        }
