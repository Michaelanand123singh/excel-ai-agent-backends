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
    import time
    start_time = time.perf_counter()
    
    try:
        table_name = f"ds_{req.file_id}"
        
        # Verify dataset exists
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

        # Guard small inputs
        if len((req.part_number or "").strip()) < 2:
            return {
                "part_number": req.part_number,
                "total_matches": 0,
                "companies": [],
                "message": "Enter at least 2 characters to search",
                "cached": False,
                "latency_ms": int((time.perf_counter() - start_time) * 1000)
            }
        
        # Helpers for SQL expressions
        def sql_strip_separators(expr: str) -> str:
            s = expr
            for sep in PART_NUMBER_CONFIG["separators"]:
                s = f"REPLACE({s}, '{sep}', '')"
            return s

        def sql_strip_non_alnum(expr: str) -> str:
            return f"REGEXP_REPLACE({expr}, '[^a-zA-Z0-9]+', '', 'g')"

        q_original = req.part_number.strip()
        q_no_seps = normalize(q_original, 2)
        q_alnum = normalize(q_original, 3)

        search_mode = (req.search_mode or "exact").lower()
        pn_expr = '"part_number"'
        item_desc_expr = 'CAST("Item_Description" AS TEXT)'

        exact_conditions = [
            f"LOWER({pn_expr}) = LOWER(:q_original)",
            f"LOWER({sql_strip_separators(pn_expr)}) = LOWER(:q_no_seps)",
            f"LOWER({sql_strip_non_alnum(pn_expr)}) = LOWER(:q_alnum)",
        ]

        like_conditions = [
            f"{item_desc_expr} ILIKE :pattern_any",
            f"LOWER({sql_strip_separators(item_desc_expr)}) LIKE LOWER(:pattern_no_seps)",
            f"LOWER({sql_strip_non_alnum(item_desc_expr)}) LIKE LOWER(:pattern_alnum)",
            f"LOWER({sql_strip_separators(pn_expr)}) LIKE LOWER(:pattern_no_seps)",
            f"LOWER({sql_strip_non_alnum(pn_expr)}) LIKE LOWER(:pattern_alnum)",
        ]

        fuzzy_conditions = [
            "similarity(lower(CAST(\"Item_Description\" AS TEXT)), lower(:q_original)) >= :min_sim",
        ] if PART_NUMBER_CONFIG.get("enable_db_fuzzy", True) else []

        pipelines: list[tuple[str, dict, str]] = []
        pipelines.append((" OR ".join(exact_conditions), {
            "q_original": q_original,
            "q_no_seps": q_no_seps,
            "q_alnum": q_alnum,
        }, "exact"))

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
        
        def execute_pipeline(where_sql: str, params: dict, match_type: str):
            # Build dynamic SELECT statement based on available columns
            def build_select_statement():
                # Get all available columns
                all_columns_result = db.execute(text(f"""
                    SELECT column_name 
                    FROM information_schema.columns 
                    WHERE table_name = '{table_name}' 
                    ORDER BY ordinal_position
                """)).fetchall()
                available_columns = [row[0] for row in all_columns_result]
                
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
                
                select_parts = []
                for alias, possible_columns in column_mappings.items():
                    found_column = None
                    for col in possible_columns:
                        if col in available_columns:
                            found_column = col
                            break
                    
                    if found_column:
                        select_parts.append(f'"{found_column}" as {alias}')
                    else:
                        # Use NULL for missing columns
                        select_parts.append(f'NULL as {alias}')
                
                return ', '.join(select_parts)
            
            base_select = f"""
                SELECT {build_select_statement()}
                FROM {table_name} 
                WHERE {where_sql}
            """
            order_clause = "ORDER BY \"Unit_Price\" ASC"
            if match_type == "fuzzy_trgm":
                order_clause = "ORDER BY similarity(lower(CAST(\"Item_Description\" AS TEXT)), lower(:q_original)) DESC, \"Unit_Price\" ASC"

            stats_sql_local = f"""
                SELECT 
                    COUNT(*) as total_matches,
                    MIN("Unit_Price") as min_price,
                    MAX("Unit_Price") as max_price,
                    SUM("Quantity") as total_quantity
                FROM {table_name} 
                WHERE {where_sql}
            """

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

        last_exception = None
        for where_sql, params, match_type in pipelines:
            try:
                matching_rows, stats, used_match_type = execute_pipeline(where_sql, params, match_type)
                if stats and stats[0]:
                    total_count = stats[0] or 0
                    min_price = float(stats[1]) if stats[1] is not None else 0.0
                    max_price = float(stats[2]) if stats[2] is not None else 0.0
                    total_quantity = int(stats[3]) if stats[3] is not None else 0

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
                            "secondary_buyer_contact": row[9] or "N/A",
                            "secondary_buyer_email": row[10] or "N/A",
                        })
                    break
            except Exception as e:  # pragma: no cover
                last_exception = e
                continue

        # Fallback python-side scoring
        if total_count == 0 and search_mode in ("hybrid", "fuzzy"):
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
                        "Quantity", "Unit_Price", "Item_Description", "part_number", "UQC",
                        "Potential Buyer 2", "Potential Buyer 2 Contact Details", "Potential Buyer 2 email id"
                    FROM {table_name}
                    WHERE {where}
                    LIMIT :lim
                """), {**params, "lim": limit}).fetchall()

                scored: list[tuple[float, tuple]] = []
                for r in rows:
                    pn_val = (r[6] or "")
                    score = max(
                        similarity_score(normalize(pn_val, 2).lower(), q_no_seps.lower()),
                        similarity_score(normalize(pn_val, 3).lower(), q_alnum.lower()),
                        similarity_score(str(pn_val).lower(), q_original.lower()),
                    )
                    if score >= PART_NUMBER_CONFIG.get("min_similarity", 0.6):
                        scored.append((score, r))
                scored.sort(key=lambda x: x[0], reverse=True)

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
                        "secondary_buyer_contact": r[9] or "N/A",
                        "secondary_buyer_email": r[10] or "N/A",
                    })
        
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
            "message": f"Found {total_count} companies with part number '{req.part_number}'. Price range: ₹{min_price:.2f} - ₹{max_price:.2f}",
            "cached": False,
            "latency_ms": int((time.perf_counter() - start_time) * 1000),
            "table_name": table_name,
            "show_all": bool(req.show_all),
            "search_mode": search_mode,
            "match_type": used_match_type,
        }
        return result
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Search failed: {e}")


# Removed single part search endpoint; the system uses bulk search exclusively now


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

    # Prepare response map
    results: dict[str, dict] = {}

    # Shared search params
    base_page = int(req.page or 1)
    base_page_size = int(req.page_size or 50)
    base_show_all = bool(req.show_all)
    base_search_mode = (req.search_mode or "exact").lower()

    # Execute search per part using inlined single-search logic (copy of previous handler)
    for pn in normalized:
        try:
            # Reset transaction state before each search to prevent "aborted transaction" errors
            try:
                db.rollback()
            except:
                pass  # Ignore if no transaction to rollback
            
            # Quick table existence is already checked
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
                all_columns_result = db.execute(text(f"""
                    SELECT column_name 
                    FROM information_schema.columns 
                    WHERE table_name = '{table_name}' 
                    ORDER BY ordinal_position
                """))
                text_columns = [row[0] for row in all_columns_result.fetchall()]

            if len(pn.strip()) < 2:
                results[pn] = {
                    "part_number": pn,
                    "total_matches": 0,
                    "companies": [],
                    "message": "Enter at least 2 characters to search",
                    "cached": False,
                    "latency_ms": int((time.perf_counter() - start_time) * 1000)
                }
                continue

            def sql_strip_separators(expr: str) -> str:
                s = expr
                for sep in PART_NUMBER_CONFIG["separators"]:
                    s = f"REPLACE({s}, '{sep}', '')"
                return s

            def sql_strip_non_alnum(expr: str) -> str:
                return f"REGEXP_REPLACE({expr}, '[^a-zA-Z0-9]+', '', 'g')"

            q_original = pn.strip()
            q_no_seps = normalize(q_original, 2)
            q_alnum = normalize(q_original, 3)

            search_mode = base_search_mode
            pn_expr = '"part_number"'
            item_desc_expr = 'CAST("Item_Description" AS TEXT)'

            exact_conditions = [
                f"LOWER({pn_expr}) = LOWER(:q_original)",
                f"LOWER({sql_strip_separators(pn_expr)}) = LOWER(:q_no_seps)",
                f"LOWER({sql_strip_non_alnum(pn_expr)}) = LOWER(:q_alnum)",
            ]

            like_conditions = [
                f"{item_desc_expr} ILIKE :pattern_any",
                f"LOWER({sql_strip_separators(item_desc_expr)}) LIKE LOWER(:pattern_no_seps)",
                f"LOWER({sql_strip_non_alnum(item_desc_expr)}) LIKE LOWER(:pattern_alnum)",
                f"LOWER({sql_strip_separators(pn_expr)}) LIKE LOWER(:pattern_no_seps)",
                f"LOWER({sql_strip_non_alnum(pn_expr)}) LIKE LOWER(:pattern_alnum)",
            ]

            fuzzy_conditions = [
                "similarity(lower(CAST(\"Item_Description\" AS TEXT)), lower(:q_original)) >= :min_sim",
            ] if PART_NUMBER_CONFIG.get("enable_db_fuzzy", True) else []

            pipelines: list[tuple[str, dict, str]] = []
            pipelines.append((" OR ".join(exact_conditions), {
                "q_original": q_original,
                "q_no_seps": q_no_seps,
                "q_alnum": q_alnum,
            }, "exact"))

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

            def execute_pipeline(where_sql: str, params: dict, match_type: str):
                # Build dynamic SELECT statement based on available columns
                def build_select_statement():
                    # Get all available columns
                    all_columns_result = db.execute(text(f"""
                        SELECT column_name 
                        FROM information_schema.columns 
                        WHERE table_name = '{table_name}' 
                        ORDER BY ordinal_position
                    """)).fetchall()
                    available_columns = [row[0] for row in all_columns_result]
                    
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
                    
                    select_parts = []
                    for alias, possible_columns in column_mappings.items():
                        found_column = None
                        for col in possible_columns:
                            if col in available_columns:
                                found_column = col
                                break
                        
                        if found_column:
                            select_parts.append(f'"{found_column}" as {alias}')
                        else:
                            # Use NULL for missing columns
                            select_parts.append(f'NULL as {alias}')
                    
                    return ', '.join(select_parts)
                
                base_select = f"""
                    SELECT {build_select_statement()}
                    FROM {table_name} 
                    WHERE {where_sql}
                """
                order_clause = "ORDER BY \"Unit_Price\" ASC"
                if match_type == "fuzzy_trgm":
                    order_clause = "ORDER BY similarity(lower(CAST(\"Item_Description\" AS TEXT)), lower(:q_original)) DESC, \"Unit_Price\" ASC"

                stats_sql_local = f"""
                    SELECT 
                        COUNT(*) as total_matches,
                        MIN("Unit_Price") as min_price,
                        MAX("Unit_Price") as max_price,
                        SUM("Quantity") as total_quantity
                    FROM {table_name} 
                    WHERE {where_sql}
                """

                page = max(1, int(base_page))
                size = max(1, min(2000, int(base_page_size)))
                if base_show_all:
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

            last_exception = None
            for where_sql, params, match_type in pipelines:
                try:
                    matching_rows, stats, used_match_type = execute_pipeline(where_sql, params, match_type)
                    if stats and stats[0]:
                        total_count = stats[0] or 0
                        min_price = float(stats[1]) if stats[1] is not None else 0.0
                        max_price = float(stats[2]) if stats[2] is not None else 0.0
                        total_quantity = int(stats[3]) if stats[3] is not None else 0

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
                                "secondary_buyer_contact": row[9] or "N/A",
                                "secondary_buyer_email": row[10] or "N/A",
                            })
                        break
                except Exception as e:  # pragma: no cover
                    last_exception = e
                    # Rollback transaction to reset state for next iteration
                    try:
                        db.rollback()
                    except:
                        pass
                    continue

            # Fallback fuzzy_python if no results and mode allows
            if total_count == 0 and search_mode in ("hybrid", "fuzzy"):
                tokens = separator_tokenize(q_original)
                tokens = [t for t in tokens if t]
                if tokens:
                    clauses = ["CAST(\"Item_Description\" AS TEXT) ILIKE :tok_" + str(i) for i, _ in enumerate(tokens)]
                    where = " OR ".join(clauses)
                    params = {"tok_" + str(i): f"%{t}%" for i, t in enumerate(tokens)}
                    limit = min(1000, PART_NUMBER_CONFIG.get("db_batch_size", 5000))
                    
                    # Build dynamic SELECT for fallback search
                    def build_fallback_select():
                        all_columns_result = db.execute(text(f"""
                            SELECT column_name 
                            FROM information_schema.columns 
                            WHERE table_name = '{table_name}' 
                            ORDER BY ordinal_position
                        """)).fetchall()
                        available_columns = [row[0] for row in all_columns_result]
                        
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
                        
                        select_parts = []
                        for alias, possible_columns in column_mappings.items():
                            found_column = None
                            for col in possible_columns:
                                if col in available_columns:
                                    found_column = col
                                    break
                            
                            if found_column:
                                select_parts.append(f'"{found_column}"')
                            else:
                                select_parts.append('NULL')
                        
                        return ', '.join(select_parts)
                    
                    rows = db.execute(text(f"""
                        SELECT {build_fallback_select()}
                        FROM {table_name}
                        WHERE {where}
                        LIMIT :lim
                    """), {**params, "lim": limit}).fetchall()

                    scored: list[tuple[float, tuple]] = []
                    for r in rows:
                        item_desc = (r[5] or "")
                        pn_val = (r[6] or "")
                        score = max(
                            similarity_score(normalize(pn_val, 2).lower(), q_no_seps.lower()),
                            similarity_score(normalize(pn_val, 3).lower(), q_alnum.lower()),
                            similarity_score(str(pn_val).lower(), q_original.lower()),
                        )
                        if score >= PART_NUMBER_CONFIG.get("min_similarity", 0.6):
                            scored.append((score, r))
                    scored.sort(key=lambda x: x[0], reverse=True)

                    page = max(1, int(base_page))
                    size = max(1, min(2000, int(base_page_size)))
                    total_count = len(scored)
                    min_price = 0.0
                    max_price = 0.0
                    total_quantity = 0
                    start = 0 if base_show_all else (page - 1) * size
                    end = None if base_show_all else start + size
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
                            "secondary_buyer_contact": r[9] or "N/A",
                            "secondary_buyer_email": r[10] or "N/A",
                        })

            size = max(1, min(2000, int(base_page_size)))
            total_pages = 1 if base_show_all else int((total_count + size - 1) // size) if size > 0 else 1

            payload = {
                "part_number": pn,
                "total_matches": total_count,
                "companies": companies,
                "price_summary": {
                    "min_price": min_price,
                    "max_price": max_price,
                    "total_quantity": total_quantity
                },
                "page": int(base_page),
                "page_size": size,
                "total_pages": total_pages,
                "message": f"Found {total_count} companies with part number '{pn}'. Price range: ₹{min_price:.2f} - ₹{max_price:.2f}",
                "cached": False,
                "latency_ms": int((time.perf_counter() - start_time) * 1000),
                "searched_columns": text_columns,
                "table_name": table_name,
                "show_all": bool(base_show_all),
                "search_mode": search_mode,
                "match_type": used_match_type,
            }
            results[pn] = payload
        except Exception as e:
            # Ensure transaction is rolled back on error
            try:
                db.rollback()
            except:
                pass
            
            results[pn] = {
                "part_number": pn,
                "total_matches": 0,
                "companies": [],
                "message": f"Search failed: {str(e)}",
                "cached": False,
                "latency_ms": int((time.perf_counter() - start_time) * 1000),
                "error": str(e)
            }

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

        # 1) Load dataframe with robust fallbacks for CSV/XLSX/XLS
        if name.endswith(".csv"):
            # Try utf-8 first, then fallback to latin1
            try:
                df = pd.read_csv(bio)
            except Exception:
                bio.seek(0)
                df = pd.read_csv(bio, encoding="latin1")
        else:
            # Excel: try without engine (let pandas pick), then fall back to openpyxl
            try:
                df = pd.read_excel(bio)
            except Exception:
                # Fallback to openpyxl explicitly for .xlsx
                try:
                    bio.seek(0)
                    df = pd.read_excel(bio, engine="openpyxl")
                except Exception as e:
                    raise HTTPException(status_code=400, detail=f"Failed to read Excel file: {e}")

        if df is None or df.empty:
            return {"results": {}, "total_parts": 0}

        # 2) Choose the correct column for part numbers using flexible variants
        cols_lower_map = {str(c).strip().lower(): c for c in df.columns}
        # Known header variants
        header_variants = [
            "part_number", "part number", "part no", "part_no", "partno", "pn",
        ]
        chosen_col = None
        for hv in header_variants:
            if hv in cols_lower_map:
                chosen_col = cols_lower_map[hv]
                break
        # Fallback to the first column if nothing matched
        if not chosen_col:
            chosen_col = list(cols_lower_map.values())[0]

        # 3) Extract and sanitize values (normalize numeric-like part numbers e.g. 3585720.0 -> 3585720)
        import re
        try:
            import numpy as np  # type: ignore
        except Exception:  # pragma: no cover
            np = None  # type: ignore

        def normalize_pn(v):
            if v is None:
                return ""
            # numpy types
            if np is not None and isinstance(v, (np.integer, np.floating)):
                try:
                    f = float(v)
                    if float(f).is_integer():
                        return str(int(f))
                    return str(v)
                except Exception:
                    return str(v)
            if isinstance(v, (int,)):
                return str(int(v))
            if isinstance(v, float):
                if float(v).is_integer():
                    return str(int(v))
                return str(v)
            s = str(v).replace('\u00A0', ' ').replace(',', '').strip()
            if re.fullmatch(r"\d+\.0+", s):
                return s.split(".")[0]
            m = re.fullmatch(r"(\d+)\.(0+)", s)
            if m:
                return m.group(1)
            return s

        parts = []
        for v in df[chosen_col].tolist():
            s = normalize_pn(v)
            s = (s or "").strip()
            if not s:
                continue
            low = s.lower()
            if low in ("nan", "none", "null"):
                continue
            if len(s) >= 2:
                parts.append(s)

        # De-dup while preserving order
        seen = set()
        unique_parts = []
        for p in parts:
            k = p.lower()
            if k not in seen:
                seen.add(k)
                unique_parts.append(p)

        parts = unique_parts[:10000]
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Failed to parse file: {e}")

    # Route through Elasticsearch-powered endpoint (has built-in fallback to PostgreSQL)
    from app.api.v1.endpoints.query_elasticsearch import search_part_number_bulk_elasticsearch
    payload = {
        'file_id': file_id, 
        'part_numbers': parts, 
        'page': 1, 
        'page_size': 50, 
        'show_all': False,
        'search_mode': 'hybrid'
    }
    return await search_part_number_bulk_elasticsearch(payload, db, user)

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


