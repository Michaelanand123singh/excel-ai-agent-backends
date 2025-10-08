from fastapi import APIRouter, Depends, HTTPException, status, UploadFile, File, Form
from pydantic import BaseModel
from sqlalchemy.orm import Session
from sqlalchemy import text

from app.api.dependencies.database import get_db
from app.api.dependencies.rate_limit import rate_limit
from app.api.dependencies.auth import get_current_user
from app.services.query_engine.service import answer_question
from app.services.query_engine.confidence_calculator import confidence_calculator
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
    page_size: int | None = 1000  # Reasonable default for pagination
    show_all: bool | None = False  # Use pagination by default for better performance
    search_mode: str | None = "hybrid"  # Changed default to hybrid for better matching


class BulkPartSearchRequest(BaseModel):
    file_id: int
    part_numbers: list[str]
    page: int | None = 1
    page_size: int | None = 1000  # Reasonable default for pagination
    show_all: bool | None = False  # Use pagination by default for better performance
    search_mode: str | None = "hybrid"  # Changed default to hybrid for better matching


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

        # Use unified search engine for consistent results
        from app.services.search_engine.unified_search_engine import UnifiedSearchEngine
        
        search_engine = UnifiedSearchEngine(db, table_name, file_id=req.file_id)
        result = search_engine.search_single_part(
            part_number=req.part_number,
            search_mode=req.search_mode or "hybrid",
            page=req.page or 1,
            page_size=req.page_size or 1000,  # Reasonable default for pagination
            show_all=req.show_all or False  # Use pagination by default for better performance
        )
        
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
    Uses unified search engine for consistent results.
    """
    import time, json
    start_time = time.perf_counter()

    if not req.part_numbers:
        return {"results": {}, "total_parts": 0, "latency_ms": 0}

    # Normalize and de-dup list first - support up to 1 lakh parts
    normalized = []
    seen = set()
    for pn in req.part_numbers:
        v = (pn or "").strip()
        if len(v) >= 2 and v.lower() not in seen:
            seen.add(v.lower())
            normalized.append(v)
    
    # Limit to 1 lakh parts for performance
    if len(normalized) > 100000:
        normalized = normalized[:100000]

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

    # Use unified search engine for consistent results
    from app.services.search_engine.unified_search_engine import UnifiedSearchEngine
    
    search_engine = UnifiedSearchEngine(db, table_name, file_id=req.file_id)
    result = search_engine.search_bulk_parts(
        part_numbers=normalized,
        search_mode=req.search_mode or "hybrid",
        page=req.page or 1,
        page_size=10000000,  # Show ALL results from dataset (up to 1 crore)
        show_all=True  # Always show all results for bulk search
    )
    
    return result


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

        parts = unique_parts[:100000]  # Support up to 1 lakh parts for bulk upload
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Failed to parse file: {e}")

    # Use unified search engine for consistent results
    from app.services.search_engine.unified_search_engine import UnifiedSearchEngine
    
    table_name = f"ds_{file_id}"
    search_engine = UnifiedSearchEngine(db, table_name, file_id=file_id)
    result = search_engine.search_bulk_parts(
        part_numbers=parts,
        search_mode='hybrid',
        page=1,
        page_size=10000000,  # Show ALL results from dataset (up to 1 crore)
        show_all=True  # Always show all results for bulk search
    )
    
    return result

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


@router.get("/test-comprehensive-search/{file_id}")
async def test_comprehensive_search(file_id: int, db: Session = Depends(get_db), user=Depends(get_current_user)) -> dict:
    """Test endpoint to verify comprehensive search results for SMD."""
    try:
        table_name = f"ds_{file_id}"
        
        # Check if table exists
        exists = db.execute(text(f"""
            SELECT EXISTS (
                SELECT FROM information_schema.tables 
                WHERE table_name = '{table_name}'
            );
        """)).scalar()
        
        if not exists:
            return {"error": f"Dataset {file_id} not found"}
        
        # Get total row count
        total_rows = db.execute(text(f"SELECT COUNT(*) FROM {table_name}")).scalar()
        
        # Test search for "SMD" to see how many results we get
        from app.services.search_engine.unified_search_engine import UnifiedSearchEngine
        
        search_engine = UnifiedSearchEngine(db, table_name, file_id=file_id)
        
        # Test with comprehensive settings
        result = search_engine.search_single_part(
            "SMD", 
            search_mode="hybrid", 
            page=1, 
            page_size=10000, 
            show_all=True
        )
        
        # Also test bulk search
        bulk_result = search_engine.search_bulk_parts(
            ["SMD"], 
            search_mode="hybrid", 
            page=1, 
            page_size=10000, 
            show_all=True
        )
        
        return {
            "file_id": file_id,
            "table_name": table_name,
            "total_rows_in_dataset": total_rows,
            "single_search_results": {
                "part_number": "SMD",
                "total_matches": result.get("total_matches", 0),
                "companies_returned": len(result.get("companies", [])),
                "search_engine_used": result.get("search_engine", "unknown"),
                "message": result.get("message", ""),
                "page": result.get("page", 1),
                "page_size": result.get("page_size", 1000),
                "total_pages": result.get("total_pages", 1)
            },
            "bulk_search_results": {
                "part_number": "SMD",
                "total_matches": bulk_result.get("results", {}).get("SMD", {}).get("total_matches", 0),
                "companies_returned": len(bulk_result.get("results", {}).get("SMD", {}).get("companies", [])),
                "search_engine_used": bulk_result.get("search_engine", "unknown"),
                "page": bulk_result.get("results", {}).get("SMD", {}).get("page", 1),
                "page_size": bulk_result.get("results", {}).get("SMD", {}).get("page_size", 1000),
                "total_pages": bulk_result.get("results", {}).get("SMD", {}).get("total_pages", 1)
            },
            "expected_results": "Should show all 7333+ results with proper pagination support for 100,000+ results"
        }
        
    except Exception as e:
        return {"error": str(e)}


@router.get("/test-unlimited-search/{file_id}")
async def test_unlimited_search(
    file_id: int, 
    part_number: str = "SMD",
    page: int = 1,
    page_size: int = 1000,
    show_all: bool = False,
    db: Session = Depends(get_db), 
    user=Depends(get_current_user)
) -> dict:
    """Test endpoint to verify unlimited search results with pagination."""
    try:
        table_name = f"ds_{file_id}"
        
        # Check if table exists
        exists = db.execute(text(f"""
            SELECT EXISTS (
                SELECT FROM information_schema.tables 
                WHERE table_name = '{table_name}'
            );
        """)).scalar()
        
        if not exists:
            return {"error": f"Dataset {file_id} not found"}
        
        # Get total row count
        total_rows = db.execute(text(f"SELECT COUNT(*) FROM {table_name}")).scalar()
        
        # Test search with specified parameters
        from app.services.search_engine.unified_search_engine import UnifiedSearchEngine
        
        search_engine = UnifiedSearchEngine(db, table_name, file_id=file_id)
        
        # Test with specified pagination settings
        result = search_engine.search_single_part(
            part_number, 
            search_mode="hybrid", 
            page=page, 
            page_size=page_size, 
            show_all=show_all
        )
        
        return {
            "file_id": file_id,
            "table_name": table_name,
            "total_rows_in_dataset": total_rows,
            "search_parameters": {
                "part_number": part_number,
                "page": page,
                "page_size": page_size,
                "show_all": show_all,
                "search_mode": "hybrid"
            },
            "search_results": {
                "total_matches": result.get("total_matches", 0),
                "companies_returned": len(result.get("companies", [])),
                "search_engine_used": result.get("search_engine", "unknown"),
                "message": result.get("message", ""),
                "page": result.get("page", 1),
                "page_size": result.get("page_size", 1000),
                "total_pages": result.get("total_pages", 1),
                "latency_ms": result.get("latency_ms", 0)
            },
            "pagination_info": {
                "current_page": page,
                "page_size": page_size,
                "total_pages": result.get("total_pages", 1),
                "has_next_page": page < result.get("total_pages", 1),
                "has_previous_page": page > 1,
                "next_page": page + 1 if page < result.get("total_pages", 1) else None,
                "previous_page": page - 1 if page > 1 else None
            },
            "performance_note": "System now supports unlimited results with efficient pagination"
        }
        
    except Exception as e:
        return {"error": str(e)}


