from fastapi import APIRouter, Depends, HTTPException, status, UploadFile, File, Form
from pydantic import BaseModel
from sqlalchemy.orm import Session
from sqlalchemy import text

from app.api.dependencies.database import get_db
from app.api.dependencies.rate_limit import rate_limit
from app.api.dependencies.auth import get_current_user
from app.services.query_engine.service import answer_question
from app.core.cache import get_redis_client
from app.utils.helpers.part_number import (
    PART_NUMBER_CONFIG,
    generate_format_variants,
    normalize,
    separator_tokenize,
    similarity_score,
    token_overlap,
)

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
    search_mode: str | None = "exact"  # exact | fuzzy | hybrid


class BulkPartSearchRequest(BaseModel):
    file_id: int
    part_numbers: list[str]
    page: int | None = 1
    page_size: int | None = 50
    show_all: bool | None = False
    search_mode: str | None = "exact"


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
        
        # Check cache first (format-aware)
        cache = get_redis_client()
        # Include pagination/show_all/search_mode and normalization level in cache key
        cache_key = f"search:{req.file_id}:{req.part_number.lower()}:mode:{(req.search_mode or 'exact').lower()}:p{req.page or 1}:s{req.page_size or 50}:a{1 if req.show_all else 0}"
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
        
        # Helpers for SQL expressions to strip separators and non-alphanumerics
        def sql_strip_separators(expr: str) -> str:
            s = expr
            for sep in PART_NUMBER_CONFIG["separators"]:
                s = f"REPLACE({s}, '{sep}', '')"
            return s

        def sql_strip_non_alnum(expr: str) -> str:
            # PostgreSQL regexp_replace to keep alphanumerics
            return f"REGEXP_REPLACE({expr}, '[^a-zA-Z0-9]+', '', 'g')"

        # Build progressive search pipelines
        q_original = req.part_number.strip()
        q_no_seps = normalize(q_original, 2)
        q_alnum = normalize(q_original, 3)

        # Base conditions for exact and like searches
        search_mode = (req.search_mode or "exact").lower()

        # Avoid nested quotes in f-strings by defining SQL expressions once
        pn_expr = '"part_number"'
        item_desc_expr = 'CAST("Item_Description" AS TEXT)'

        # Stage 1: Multi-format exact matches on part_number and normalized projections
        exact_conditions = [
            f"LOWER({pn_expr}) = LOWER(:q_original)",
            f"LOWER({sql_strip_separators(pn_expr)}) = LOWER(:q_no_seps)",
            f"LOWER({sql_strip_non_alnum(pn_expr)}) = LOWER(:q_alnum)",
        ]

        # Stage 2: Description and part_number pattern matches (separator-insensitive)
        like_conditions = [
            f"{item_desc_expr} ILIKE :pattern_any",
            f"LOWER({sql_strip_separators(item_desc_expr)}) LIKE LOWER(:pattern_no_seps)",
            f"LOWER({sql_strip_non_alnum(item_desc_expr)}) LIKE LOWER(:pattern_alnum)",
            # Also allow substring on normalized part_number for cases like ABC123 vs ABC-123
            f"LOWER({sql_strip_separators(pn_expr)}) LIKE LOWER(:pattern_no_seps)",
            f"LOWER({sql_strip_non_alnum(pn_expr)}) LIKE LOWER(:pattern_alnum)",
        ]

        # Fuzzy optional (Postgres pg_trgm)
        fuzzy_conditions = [
            # similarity on lower(Item_Description)
            "similarity(lower(CAST(\"Item_Description\" AS TEXT)), lower(:q_original)) >= :min_sim",
        ] if PART_NUMBER_CONFIG.get("enable_db_fuzzy", True) else []

        # Decide which pipeline to execute
        pipelines: list[tuple[str, dict, str]] = []  # (where_sql, params, match_type)

        # Always try exact first
        pipelines.append((" OR ".join(exact_conditions), {
            "q_original": q_original,
            "q_no_seps": q_no_seps,
            "q_alnum": q_alnum,
        }, "exact"))

        # If mode is exact, we won't try further unless no results
        if search_mode in ("hybrid", "fuzzy"):
            pipelines.append((" OR ".join(like_conditions), {
                "pattern_any": f"%{q_original}%",
                "pattern_no_seps": f"%{q_no_seps}%",
                "pattern_alnum": f"%{q_alnum}%",
            }, "separator_like"))

            if fuzzy_conditions:
                pipelines.append((" OR ".join(fuzzy_conditions), {
                    "q_original": q_original,
                    "min_sim": PART_NUMBER_CONFIG.get("min_similarity", 0.6),
                }, "fuzzy_trgm"))
        
        if not pipelines:
            return {
                "part_number": req.part_number,
                "total_matches": 0,
                "companies": [],
                "message": f"No search strategy available",
                "cached": False,
                "latency_ms": int((time.perf_counter() - start_time) * 1000)
            }
        
        def execute_pipeline(where_sql: str, params: dict, match_type: str) -> tuple[list, tuple | None, str]:
            base_select = f"""
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
                WHERE {where_sql}
            """
            # For fuzzy stage, prefer ordering by similarity if present
            order_clause = "ORDER BY \"Unit_Price\" ASC"
            if match_type == "fuzzy_trgm":
                order_clause = "ORDER BY similarity(lower(CAST(\"Item_Description\" AS TEXT)), lower(:q_original)) DESC, \"Unit_Price\" ASC"

            # Count SQL
            stats_sql_local = f"""
                SELECT 
                    COUNT(*) as total_matches,
                    MIN("Unit_Price") as min_price,
                    MAX("Unit_Price") as max_price,
                    SUM("Quantity") as total_quantity
                FROM {table_name} 
                WHERE {where_sql}
            """

            # Pagination parameters (show_all overrides pagination caps)
            page = max(1, int(req.page or 1))
            size = max(1, min(2000, int(req.page_size or 50)))
            if req.show_all:
                paged_sql = base_select + f"\n{order_clause}\nLIMIT :limit OFFSET :offset"
                run_params = {**params, "limit": 100000, "offset": 0}
            else:
                offset = (page - 1) * size
                paged_sql = base_select + f"\n{order_clause}\nLIMIT :limit OFFSET :offset"
                run_params = {**params, "limit": size, "offset": offset}

            matching_rows = db.execute(text(paged_sql), run_params).fetchall()
            stats = db.execute(text(stats_sql_local), params).fetchone()
            return matching_rows, stats, match_type
        
        companies = []
        total_count = 0
        min_price = 0.0
        max_price = 0.0
        total_quantity = 0
        used_match_type = "none"
        used_normalization = 1

        # Execute pipelines progressively with early termination
        last_exception = None
        for where_sql, params, match_type in pipelines:
            try:
                matching_rows, stats, used_match_type = execute_pipeline(where_sql, params, match_type)
                if stats and stats[0]:
                    # We have matches; stop early for exact/like; for fuzzy ensure cap
                    total_count = stats[0] or 0
                    min_price = float(stats[1]) if stats[1] is not None else 0.0
                    max_price = float(stats[2]) if stats[2] is not None else 0.0
                    total_quantity = int(stats[3]) if stats[3] is not None else 0

                    # Convert to list of dicts
                    for row in matching_rows:
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
                    break
            except Exception as e:  # pragma: no cover
                last_exception = e
                continue

        if total_count == 0 and search_mode in ("hybrid", "fuzzy"):
            # Final Python-side token overlap fallback over limited candidate set
            # Pull up to N candidates by ILIKE on any token to score locally
            tokens = separator_tokenize(q_original)
            tokens = [t for t in tokens if t]
            if tokens:
                clauses = ["CAST(\"Item_Description\" AS TEXT) ILIKE :tok_" + str(i) for i, _ in enumerate(tokens)]
                where = " OR ".join(clauses)
                params = {"tok_" + str(i): f"%{t}%" for i, t in enumerate(tokens)}
                limit = min(1000, PART_NUMBER_CONFIG.get("db_batch_size", 5000))
                rows = db.execute(text(f"""
                    SELECT 
                        "Potential Buyer 1", "Potential Buyer 1 Contact Details", "Potential Buyer 1 email id",
                        "Quantity", "Unit_Price", "Item_Description", "part_number", "UQC", "Potential Buyer 2"
                    FROM {table_name}
                    WHERE {where}
                    LIMIT :lim
                """), {**params, "lim": limit}).fetchall()

                # Score locally and keep above threshold
                scored: list[tuple[float, tuple]] = []
                for r in rows:
                    item_desc = (r[5] or "")
                    pn = (r[6] or "")
                    # Cross-format similarity on part number
                    score = max(
                        similarity_score(normalize(pn, 2).lower(), q_no_seps.lower()),
                        similarity_score(normalize(pn, 3).lower(), q_alnum.lower()),
                        similarity_score(str(pn).lower(), q_original.lower()),
                    )
                    if score >= PART_NUMBER_CONFIG.get("min_similarity", 0.6):
                        scored.append((score, r))
                scored.sort(key=lambda x: x[0], reverse=True)

                # Pagination on the filtered results
                page = max(1, int(req.page or 1))
                size = max(1, min(2000, int(req.page_size or 50)))
                total_count = len(scored)
                min_price = 0.0
                max_price = 0.0
                total_quantity = 0
                start = 0 if req.show_all else (page - 1) * size
                end = None if req.show_all else start + size
                for score, r in scored[start:end]:
                    price = float(r[4]) if r[4] is not None else 0.0
                    qty = int(r[3]) if r[3] is not None else 0
                    if min_price == 0.0 or price < min_price:
                        min_price = price
                    if price > max_price:
                        max_price = price
                    total_quantity += qty
                    companies.append({
                        "company_name": r[0] or "N/A",
                        "contact_details": r[1] or "N/A",
                        "email": r[2] or "N/A",
                        "quantity": qty,
                        "unit_price": price,
                        "item_description": r[5] or "N/A",
                        "part_number": r[6] or "N/A",
                        "uqc": r[7] or "N/A",
                        "secondary_buyer": r[8] or "N/A",
                    })
                used_match_type = "fuzzy_python"
        
        # Compute total_pages
        size = max(1, min(2000, int(req.page_size or 50)))
        total_pages = 1 if req.show_all else int((total_count + size - 1) // size) if size > 0 else 1

        result = {
            "part_number": req.part_number,
            "total_matches": total_count,
            "companies": companies,
            "price_summary": {
                "min_price": min_price,
                "max_price": max_price,
                "total_quantity": total_quantity
            },
            "page": int(req.page or 1),
            "page_size": size,
            "total_pages": total_pages,
            "message": f"Found {total_count} companies with part number '{req.part_number}'. Price range: ${min_price:.2f} - ${max_price:.2f}",
            "cached": False,
            "latency_ms": int((time.perf_counter() - start_time) * 1000),
            "searched_columns": text_columns,
            "table_name": table_name,
            "show_all": bool(req.show_all),
            "search_mode": search_mode,
            "match_type": used_match_type,
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
    search_mode = (req.search_mode or "exact").lower()

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
        cache_key = f"search:{req.file_id}:{pn.lower()}:mode:{search_mode}:p{page}:s{page_size}:a{1 if show_all else 0}"
        cached = cache.get(cache_key)
        if cached:
            try:
                results[pn] = json.loads(cached)
                results[pn]["cached"] = True
                continue
            except Exception:
                pass

        # Reuse single-search logic by calling function directly
        try:
            single_payload = await search_part_number(PartNumberSearchRequest(
                file_id=req.file_id,
                part_number=pn,
                page=page,
                page_size=page_size,
                show_all=show_all,
                search_mode=search_mode,
            ), db, user)
            results[pn] = single_payload
        except Exception as e:
            results[pn] = {"error": f"Search failed: {e}"}

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


