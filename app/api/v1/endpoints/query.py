from fastapi import APIRouter, Depends, HTTPException, status, UploadFile, File, Form
from pydantic import BaseModel
from sqlalchemy.orm import Session
from sqlalchemy import text

from app.api.dependencies.database import get_db
from app.api.dependencies.rate_limit import rate_limit
from app.api.dependencies.auth import get_current_user
from app.services.query_engine.service import answer_question
from app.core.cache import get_redis_client

router = APIRouter()


class QueryRequest(BaseModel):
    question: str
    file_id: int


class PartNumberSearchRequest(BaseModel):
    part_number: str
    file_id: int
    page: int | None = 1
    page_size: int | None = 50
    show_all: bool | None = False


class BulkPartSearchRequest(BaseModel):
    file_id: int
    part_numbers: list[str]
    page: int | None = 1
    page_size: int | None = 50
    show_all: bool | None = False


@router.post("/")
async def query(req: QueryRequest, db: Session = Depends(get_db), user=Depends(get_current_user)) -> dict:
    user_id = 0  # map token to user later
    return answer_question(db, user_id, req.question, req.file_id)


@router.post("/search-part")
async def search_part_number(req: PartNumberSearchRequest, db: Session = Depends(get_db), user=Depends(get_current_user)) -> dict:
    """Search for companies that have a specific part number in the uploaded dataset."""
    import time
    start_time = time.perf_counter()
    
    try:
        # Get the table name for this file_id
        table_name = f"ds_{req.file_id}"
        
        # Check cache first
        cache = get_redis_client()
        # Include pagination/show_all in cache key (stats same; page content varies)
        cache_key = f"search:{req.file_id}:{req.part_number.lower()}:p{req.page or 1}:s{req.page_size or 50}:a{1 if req.show_all else 0}"
        cached_result = cache.get(cache_key)
        if cached_result:
            import json
            result = json.loads(cached_result)
            result["cached"] = True
            result["latency_ms"] = int((time.perf_counter() - start_time) * 1000)
            return result
        
        # Quick table existence check
        result = db.execute(text(f"""
            SELECT EXISTS (
                SELECT FROM information_schema.tables 
                WHERE table_name = '{table_name}'
            );
        """))
        table_exists = result.scalar()
        
        if not table_exists:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, 
                detail=f"Dataset {req.file_id} not found or not processed yet"
            )
        
        # Get column names for dynamic search
        columns_result = db.execute(text(f"""
            SELECT column_name, data_type 
            FROM information_schema.columns 
            WHERE table_name = '{table_name}' 
            AND data_type IN ('text', 'character varying', 'character', 'varchar')
            ORDER BY ordinal_position
        """))
        text_columns = [row[0] for row in columns_result.fetchall()]
        
        if not text_columns:
            # Fallback: search in all columns
            all_columns_result = db.execute(text(f"""
                SELECT column_name 
                FROM information_schema.columns 
                WHERE table_name = '{table_name}' 
                ORDER BY ordinal_position
            """))
            text_columns = [row[0] for row in all_columns_result.fetchall()]
        
        # Minimal input length guard to avoid full-table scans on 1 char
        if len(req.part_number.strip()) < 2:
            return {
                "part_number": req.part_number,
                "total_matches": 0,
                "companies": [],
                "message": "Enter at least 2 characters to search",
                "cached": False,
                "latency_ms": int((time.perf_counter() - start_time) * 1000)
            }

        # Build conditions focusing on Item_Description and exact part_number.
        # Normalize input (trim) for more reliable matches
        exact_value = req.part_number.strip()
        # Conditions:
        # 1) Exact derived part_number match
        # 2) Case-insensitive substring match on Item_Description
        # 3) Space-insensitive substring match (helps with formats like AB C-123 vs ABC123)
        search_conditions = [
            "LOWER(\"part_number\") = LOWER(:exact)",
            "CAST(\"Item_Description\" AS TEXT) ILIKE :pattern",
            "REPLACE(LOWER(CAST(\"Item_Description\" AS TEXT)), ' ', '') LIKE REPLACE(LOWER(:pattern), ' ', '')",
        ]
        
        if not search_conditions:
            return {
                "part_number": req.part_number,
                "total_matches": 0,
                "companies": [],
                "message": f"No searchable columns found in dataset {req.file_id}",
                "cached": False,
                "latency_ms": int((time.perf_counter() - start_time) * 1000)
            }
        
        # Get all matching rows with price aggregation (stats independent of pagination)
        search_sql = f"""
            SELECT 
                "Potential Buyer 1" as company_name,
                "Potential Buyer 1 Contact Details" as contact_details,
                "Potential Buyer 1 email id" as email,
                "Quantity",
                "Unit_Price",
                "Item_Description",
                "part_number",
                "UQC",
                "Potential Buyer 2" as secondary_buyer
            FROM {table_name} 
            WHERE {' OR '.join(search_conditions)}
            ORDER BY "Unit_Price" ASC
        """
        
        # Get matching rows count and price stats
        stats_sql = f"""
            SELECT 
                COUNT(*) as total_matches,
                MIN("Unit_Price") as min_price,
                MAX("Unit_Price") as max_price,
                SUM("Quantity") as total_quantity
            FROM {table_name} 
            WHERE {' OR '.join(search_conditions)}
        """
        
        try:
            # Execute both queries with bound parameters
            pattern = f"%{exact_value}%"
            # Pagination parameters (show_all overrides pagination caps, but with a hard safety max)
            page = max(1, int(req.page or 1))
            size = max(1, min(2000, int(req.page_size or 50)))
            if req.show_all:
                # Hard safety cap to avoid returning unbounded payloads
                params = {"pattern": pattern, "exact": exact_value, "limit": 100000, "offset": 0}
                paged_sql = search_sql + "\nLIMIT :limit OFFSET :offset"
            else:
                offset = (page - 1) * size
                paged_sql = search_sql + "\nLIMIT :limit OFFSET :offset"
                params = {"pattern": pattern, "exact": exact_value, "limit": size, "offset": offset}
            matching_rows = db.execute(text(paged_sql), params).fetchall()
            stats = db.execute(text(stats_sql), {"pattern": pattern, "exact": exact_value}).fetchone()
            
            # Convert to list of dicts with clean formatting
            companies = []
            for row in matching_rows:
                company = {
                    "company_name": row[0] or "N/A",
                    "contact_details": row[1] or "N/A", 
                    "email": row[2] or "N/A",
                    "quantity": int(row[3]) if row[3] is not None else 0,
                    "unit_price": float(row[4]) if row[4] is not None else 0.0,
                    "item_description": row[5] or "N/A",
                    "part_number": row[6] or "N/A",
                    "uqc": row[7] or "N/A",
                    "secondary_buyer": row[8] or "N/A"
                }
                companies.append(company)
            
            total_count = stats[0] if stats else 0
            min_price = float(stats[1]) if stats and stats[1] is not None else 0.0
            max_price = float(stats[2]) if stats and stats[2] is not None else 0.0
            total_quantity = int(stats[3]) if stats and stats[3] is not None else 0
            total_pages = 1 if req.show_all else int((total_count + size - 1) // size) if size > 0 else 1
            
        except Exception as e:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Search query failed: {str(e)}"
            )
        
        result = {
            "part_number": req.part_number,
            "total_matches": total_count,
            "companies": companies,
            "price_summary": {
                "min_price": min_price,
                "max_price": max_price,
                "total_quantity": total_quantity
            },
            "page": page,
            "page_size": size,
            "total_pages": total_pages,
            "message": f"Found {total_count} companies with part number '{req.part_number}'. Price range: ${min_price:.2f} - ${max_price:.2f}",
            "cached": False,
            "latency_ms": int((time.perf_counter() - start_time) * 1000),
            "searched_columns": text_columns,
            "table_name": table_name,
            "show_all": bool(req.show_all)
        }
        
        # Cache the result for 5 minutes
        import json
        cache.setex(cache_key, 300, json.dumps(result))
        
        return result
        
    except HTTPException:
        # Re-raise HTTP exceptions (like 404)
        raise
    except Exception as e:
        # Log the error for debugging
        import logging
        logger = logging.getLogger(__name__)
        logger.error(f"Part number search failed for file_id={req.file_id}, part_number={req.part_number}: {str(e)}")
        
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Search failed: {str(e)}"
        )


@router.post("/search-part-bulk")
async def search_part_number_bulk(req: BulkPartSearchRequest, db: Session = Depends(get_db), user=Depends(get_current_user)) -> dict:
    """Bulk search for multiple part numbers in a dataset.

    Returns a mapping from part_number -> result payload used in single search.
    """
    import time, json
    start_time = time.perf_counter()

    if not req.part_numbers:
        return {"results": {}, "total_parts": 0, "latency_ms": 0}

    # Normalize and de-dup small list first
    normalized = []
    seen = set()
    for pn in req.part_numbers:
        v = (pn or "").strip()
        if len(v) >= 2 and v.lower() not in seen:
            seen.add(v.lower())
            normalized.append(v)

    if not normalized:
        return {"results": {}, "total_parts": 0, "latency_ms": int((time.perf_counter() - start_time) * 1000)}

    # Reuse the single-search path logic by calling the SQL once per part.
    # This keeps implementation simple and leverages existing caching.
    results: dict[str, dict] = {}
    page = req.page or 1
    page_size = req.page_size or 50
    show_all = bool(req.show_all)

    # Verify dataset exists once up-front
    table_name = f"ds_{req.file_id}"
    exists = db.execute(text(
        f"""
        SELECT EXISTS (
            SELECT FROM information_schema.tables 
            WHERE table_name = '{table_name}'
        );
        """
    )).scalar()
    if not exists:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Dataset {req.file_id} not found or not processed yet")

    cache = get_redis_client()
    for pn in normalized:
        cache_key = f"search:{req.file_id}:{pn.lower()}:p{page}:s{page_size}:a{1 if show_all else 0}"
        cached = cache.get(cache_key)
        if cached:
            try:
                results[pn] = json.loads(cached)
                results[pn]["cached"] = True
                continue
            except Exception:
                pass

        # Build SQL same as single endpoint
        search_conditions = [
            "LOWER(\"part_number\") = LOWER(:exact)",
            "CAST(\"Item_Description\" AS TEXT) ILIKE :pattern",
            "REPLACE(LOWER(CAST(\"Item_Description\" AS TEXT)), ' ', '') LIKE REPLACE(LOWER(:pattern), ' ', '')",
        ]
        search_sql = f"""
            SELECT 
                "Potential Buyer 1" as company_name,
                "Potential Buyer 1 Contact Details" as contact_details,
                "Potential Buyer 1 email id" as email,
                "Quantity",
                "Unit_Price",
                "Item_Description",
                "part_number",
                "UQC",
                "Potential Buyer 2" as secondary_buyer
            FROM {table_name} 
            WHERE {' OR '.join(search_conditions)}
            ORDER BY "Unit_Price" ASC
        """
        stats_sql = f"""
            SELECT 
                COUNT(*) as total_matches,
                MIN("Unit_Price") as min_price,
                MAX("Unit_Price") as max_price,
                SUM("Quantity") as total_quantity
            FROM {table_name} 
            WHERE {' OR '.join(search_conditions)}
        """

        pattern = f"%{pn}%"
        size = max(1, min(2000, int(page_size)))
        if show_all:
            params = {"pattern": pattern, "exact": pn, "limit": 100000, "offset": 0}
            paged_sql = search_sql + "\nLIMIT :limit OFFSET :offset"
        else:
            offset = (max(1, int(page)) - 1) * size
            paged_sql = search_sql + "\nLIMIT :limit OFFSET :offset"
            params = {"pattern": pattern, "exact": pn, "limit": size, "offset": offset}

        try:
            rows = db.execute(text(paged_sql), params).fetchall()
            stats = db.execute(text(stats_sql), {"pattern": pattern, "exact": pn}).fetchone()
        except Exception as e:
            results[pn] = {"error": f"Search failed: {e}"}
            continue

        companies = []
        for row in rows:
            companies.append({
                "company_name": row[0] or "N/A",
                "contact_details": row[1] or "N/A",
                "email": row[2] or "N/A",
                "quantity": int(row[3]) if row[3] is not None else 0,
                "unit_price": float(row[4]) if row[4] is not None else 0.0,
                "item_description": row[5] or "N/A",
                "part_number": row[6] or "N/A",
                "uqc": row[7] or "N/A",
                "secondary_buyer": row[8] or "N/A",
            })

        total_count = stats[0] if stats else 0
        min_price = float(stats[1]) if stats and stats[1] is not None else 0.0
        max_price = float(stats[2]) if stats and stats[2] is not None else 0.0
        total_quantity = int(stats[3]) if stats and stats[3] is not None else 0
        total_pages = 1 if show_all else int((total_count + size - 1) // size) if size > 0 else 1

        payload = {
            "part_number": pn,
            "total_matches": total_count,
            "companies": companies,
            "price_summary": {
                "min_price": min_price,
                "max_price": max_price,
                "total_quantity": total_quantity,
            },
            "page": page,
            "page_size": size,
            "total_pages": total_pages,
            "show_all": show_all,
        }
        results[pn] = payload
        # cache ~5 minutes
        try:
            cache.setex(cache_key, 300, json.dumps(payload))
        except Exception:
            pass

    return {
        "results": results,
        "total_parts": len(results),
        "latency_ms": int((time.perf_counter() - start_time) * 1000),
        "file_id": req.file_id,
    }


@router.post("/search-part-bulk-upload")
async def search_part_number_bulk_upload(file_id: int = Form(...), file: UploadFile = File(...), db: Session = Depends(get_db), user=Depends(get_current_user)) -> dict:
    """Accept an Excel/CSV file containing a column of part numbers and perform bulk search.

    Extraction strategy:
    - If a column named 'part_number' (case-insensitive) exists, use it
    - Otherwise use the first non-empty column
    - Limit to first 10,000 entries to protect the service
    """
    import io
    import pandas as pd

    content = await file.read()
    if not content:
        raise HTTPException(status_code=400, detail="Empty file uploaded")

    try:
        name = (file.filename or "").lower()
        df = None
        bio = io.BytesIO(content)
        if name.endswith(".csv"):
            df = pd.read_csv(bio)
        else:
            # xlsx/xls
            df = pd.read_excel(bio, engine="openpyxl")
        if df is None or df.empty:
            return {"results": {}, "total_parts": 0}

        # Pick part number column
        cols_lower = {c.lower(): c for c in df.columns}
        chosen = cols_lower.get("part_number") or cols_lower.get("part no") or list(cols_lower.values())[0]
        parts = [str(v).strip() for v in df[chosen].astype(str).tolist() if str(v).strip() and str(v).strip().lower() != "nan"]
        # Cap to 10k
        parts = parts[:10000]
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Failed to parse file: {e}")

    # Reuse bulk API path
    payload = BulkPartSearchRequest(file_id=file_id, part_numbers=parts, page=1, page_size=50, show_all=False)
    return await search_part_number_bulk(payload, db, user)

@router.get("/test-search/{file_id}")
async def test_search_endpoint(file_id: int, db: Session = Depends(get_db), user=Depends(get_current_user)) -> dict:
    """Test endpoint to verify search functionality."""
    try:
        table_name = f"ds_{file_id}"
        
        # Check if table exists
        result = db.execute(text(f"""
            SELECT EXISTS (
                SELECT FROM information_schema.tables 
                WHERE table_name = '{table_name}'
            );
        """))
        table_exists = result.scalar()
        
        if not table_exists:
            return {
                "status": "error",
                "message": f"Table {table_name} does not exist",
                "table_exists": False
            }
        
        # Get table info
        columns_result = db.execute(text(f"SELECT column_name, data_type FROM information_schema.columns WHERE table_name = '{table_name}' ORDER BY ordinal_position"))
        columns_info = columns_result.fetchall()
        
        # Get row count
        count_result = db.execute(text(f"SELECT COUNT(*) FROM {table_name}"))
        row_count = count_result.scalar()
        
        return {
            "status": "success",
            "table_name": table_name,
            "table_exists": True,
            "row_count": row_count,
            "columns": [{"name": col[0], "type": col[1]} for col in columns_info]
        }
        
    except Exception as e:
        return {
            "status": "error",
            "message": str(e),
            "table_exists": False
        }


