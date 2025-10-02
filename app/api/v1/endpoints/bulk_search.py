"""
Bulk Excel Part Number Search API Endpoints
Handles user-uploaded Excel files for comprehensive part number search
"""

from fastapi import APIRouter, UploadFile, File, Form, Depends, HTTPException, status, BackgroundTasks
from sqlalchemy.orm import Session
from sqlalchemy import text
import time
import asyncio
from typing import List, Dict, Any
import logging

from app.api.dependencies.database import get_db
from app.api.dependencies.auth import get_current_user
from app.services.data_processor.bulk_excel_parser import BulkExcelParser, BulkSearchConfig, UserPartData
from app.services.data_processor.multi_field_search import MultiFieldSearchEngine, BulkSearchResult, SearchResult
from app.core.cache import get_redis_client

router = APIRouter()
logger = logging.getLogger(__name__)

# Configuration for bulk search
BULK_SEARCH_CONFIG = BulkSearchConfig(
    max_file_size_mb=50,
    batch_size=500,
    max_results_per_part=3,
    required_headers=["Part Number", "Part name", "Quantity", "Manufacturer name"],
    processing_timeout_seconds=30,
    enable_manufacturer_cross_check=True,
    confidence_threshold=0.3
)


@router.post("/bulk-excel-search")
async def bulk_excel_search(
    file: UploadFile = File(...),
    file_id: int = Form(...),
    search_mode: str = Form("hybrid"),
    db: Session = Depends(get_db),
    user=Depends(get_current_user)
) -> dict:
    """
    Upload Excel file and perform comprehensive bulk part number search.
    
    Expected Excel format:
    - Part Number (required)
    - Part name (required) 
    - Quantity (required)
    - Manufacturer name (required)
    """
    start_time = time.perf_counter()
    
    try:
        # Validate file
        if not file.filename:
            raise HTTPException(status_code=400, detail="No filename provided")
        
        if not file.filename.lower().endswith(('.xlsx', '.xls', '.csv')):
            raise HTTPException(status_code=400, detail="File must be Excel (.xlsx, .xls) or CSV format")
        
        # Read file content
        content = await file.read()
        if not content:
            raise HTTPException(status_code=400, detail="Empty file uploaded")
        
        # Validate file size
        parser = BulkExcelParser(BULK_SEARCH_CONFIG)
        is_valid_size, size_error = parser.validate_file_size(content)
        if not is_valid_size:
            raise HTTPException(status_code=400, detail=size_error)
        
        # Parse Excel file
        user_parts, parse_errors = parser.parse_excel_file(content, file.filename)
        if not user_parts:
            raise HTTPException(status_code=400, detail=f"No valid parts found. Errors: {'; '.join(parse_errors)}")
        
        # Verify target dataset exists
        table_name = f"ds_{file_id}"
        exists = db.execute(text(f"""
            SELECT EXISTS (
                SELECT FROM information_schema.tables 
                WHERE table_name = '{table_name}'
            );
        """)).scalar()
        
        if not exists:
            raise HTTPException(status_code=404, detail=f"Dataset {file_id} not found")
        
        # Build list of parsed part numbers
        parsed_parts = [p.part_number for p in user_parts if isinstance(p.part_number, str) and p.part_number.strip()]
        total_parts = len(user_parts)

        # Prefer Elasticsearch bulk search (same as textarea flow) for consistency
        es_results_map: Dict[str, Any] = {}
        try:
            from app.api.v1.endpoints.query_elasticsearch import search_part_number_bulk_elasticsearch
            es_payload = {
                'file_id': file_id,
                'part_numbers': parsed_parts,
                'page': 1,
                'page_size': 3,
                'show_all': False,
                'search_mode': search_mode,
            }
            es_resp = await search_part_number_bulk_elasticsearch(es_payload, db, user)
            # es_resp['results'] is a mapping part_number -> { companies: [...] }
            es_results_map = (es_resp or {}).get('results', {})
        except Exception:
            # Fallback to multi-field DB search if ES fails
            search_engine = MultiFieldSearchEngine(db, table_name)
            es_results_map = {}

        results = []
        found_matches = 0
        partial_matches = 0
        no_matches = 0

        for up in user_parts:
            pn = (up.part_number or '').strip()
            es_entry = es_results_map.get(pn)
            if es_entry and isinstance(es_entry, dict):
                companies = es_entry.get('companies') or []
                if companies:
                    top = companies[0]
                    db_record = {
                        'company_name': top.get('company_name', 'N/A'),
                        'contact_details': top.get('contact_details', 'N/A'),
                        'email': top.get('email', 'N/A'),
                        'quantity': top.get('quantity', 0),
                        'unit_price': top.get('unit_price', 0.0),
                        'item_description': top.get('item_description', 'N/A'),
                        'part_number': top.get('part_number', pn),
                        'uqc': top.get('uqc', 'N/A'),
                        'secondary_buyer': top.get('secondary_buyer', 'N/A'),
                        'secondary_buyer_contact': top.get('secondary_buyer_contact', 'N/A'),
                        'secondary_buyer_email': top.get('secondary_buyer_email', 'N/A'),
                    }
                    search_result = {
                        'match_status': 'found',
                        'match_type': es_entry.get('match_type', 'bulk_optimized'),
                        'confidence': 100.0,
                        'database_record': db_record,
                        'price_calculation': {
                            'unit_price': db_record['unit_price'],
                            'total_cost': float(db_record['unit_price'] or 0) * float(up.quantity or 0),
                            'available_quantity': db_record.get('quantity', 0),
                        },
                        'search_time_ms': es_entry.get('latency_ms', 0)
                    }
                    results.append(BulkSearchResult(user_data={
                        'part_number': up.part_number,
                        'part_name': up.part_name,
                        'quantity': up.quantity,
                        'manufacturer_name': up.manufacturer_name,
                        'row_index': up.row_index
                    }, search_result=SearchResult(**search_result), processing_errors=[]))
                    found_matches += 1
                    continue

            # If no ES result, optionally fallback to multi-field search for this row
            try:
                if 'search_engine' not in locals():
                    search_engine = MultiFieldSearchEngine(db, table_name)
                sr = search_engine.search_single_part({
                    'part_number': up.part_number,
                    'part_name': up.part_name,
                    'manufacturer_name': up.manufacturer_name,
                    'quantity': up.quantity
                }, search_mode)
                if sr and sr.match_status != 'not_found':
                    results.append(BulkSearchResult(user_data={
                        'part_number': up.part_number,
                        'part_name': up.part_name,
                        'quantity': up.quantity,
                        'manufacturer_name': up.manufacturer_name,
                        'row_index': up.row_index
                    }, search_result=sr, processing_errors=[]))
                    if sr.match_status == 'found':
                        found_matches += 1
                    else:
                        partial_matches += 1
                else:
                    results.append(BulkSearchResult(user_data={
                        'part_number': up.part_number,
                        'part_name': up.part_name,
                        'quantity': up.quantity,
                        'manufacturer_name': up.manufacturer_name,
                        'row_index': up.row_index
                    }, search_result=search_engine._create_empty_result(), processing_errors=[]))
                    no_matches += 1
            except Exception as e:
                empty_result = None
                try:
                    if 'search_engine' in locals():
                        empty_result = search_engine._create_empty_result()
                except Exception:
                    empty_result = SearchResult(
                        match_status="not_found",
                        match_type="none",
                        confidence=0.0,
                        database_record={},
                        price_calculation={"unit_price": 0.0, "total_cost": 0.0, "available_quantity": 0},
                        search_time_ms=0.0
                    )
                results.append(BulkSearchResult(user_data={
                    'part_number': up.part_number,
                    'part_name': up.part_name,
                    'quantity': up.quantity,
                    'manufacturer_name': up.manufacturer_name,
                    'row_index': up.row_index
                }, search_result=empty_result, processing_errors=[f"Search failed: {str(e)}"]))
                no_matches += 1
        
        processing_time = (time.perf_counter() - start_time) * 1000
        
        # Prepare response
        response = {
            "upload_summary": {
                "total_parts": total_parts,
                "found_matches": found_matches,
                "partial_matches": partial_matches,
                "no_matches": no_matches,
                "processing_time_ms": int(processing_time),
                "parse_errors": parse_errors
            },
            "results": [
                {
                    "user_data": {
                        "part_number": result.user_data["part_number"],
                        "part_name": result.user_data["part_name"],
                        "quantity": result.user_data["quantity"],
                        "manufacturer_name": result.user_data["manufacturer_name"],
                        "row_index": result.user_data["row_index"]
                    },
                    "search_result": {
                        "match_status": result.search_result.match_status,
                        "match_type": result.search_result.match_type,
                        "confidence": result.search_result.confidence,
                        "database_record": result.search_result.database_record,
                        "price_calculation": result.search_result.price_calculation,
                        "search_time_ms": result.search_result.search_time_ms
                    },
                    "processing_errors": result.processing_errors
                }
                for result in results
            ],
            "file_info": {
                "filename": file.filename,
                "file_size_bytes": len(content),
                "search_mode": search_mode
            }
        }
        
        # Cache results for 10 minutes
        cache = get_redis_client()
        cache_key = f"bulk_search:{file_id}:{hash(file.filename)}:{search_mode}"
        try:
            import json
            cache.setex(cache_key, 600, json.dumps(response))
        except Exception as e:
            logger.warning(f"Failed to cache bulk search results: {e}")
        
        return response
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Bulk Excel search failed: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail=f"Bulk search failed: {str(e)}"
        )


async def process_batch(search_engine: MultiFieldSearchEngine, 
                       user_parts: List[UserPartData], 
                       search_mode: str) -> List[BulkSearchResult]:
    """Process a batch of user parts"""
    results = []
    
    for user_part in user_parts:
        try:
            # Convert UserPartData to dict for search
            user_data = {
                "part_number": user_part.part_number,
                "part_name": user_part.part_name,
                "quantity": user_part.quantity,
                "manufacturer_name": user_part.manufacturer_name,
                "row_index": user_part.row_index
            }
            
            # Search for the part
            search_result = search_engine.search_single_part(user_data, search_mode)
            
            # Create result
            result = BulkSearchResult(
                user_data=user_data,
                search_result=search_result,
                processing_errors=[]
            )
            results.append(result)
            
        except Exception as e:
            # Create error result
            error_result = BulkSearchResult(
                user_data={
                    "part_number": user_part.part_number,
                    "part_name": user_part.part_name,
                    "quantity": user_part.quantity,
                    "manufacturer_name": user_part.manufacturer_name,
                    "row_index": user_part.row_index
                },
                search_result=search_engine._create_empty_result(),
                processing_errors=[f"Search failed: {str(e)}"]
            )
            results.append(error_result)
    
    return results


@router.get("/bulk-search-status/{file_id}")
async def get_bulk_search_status(
    file_id: int,
    db: Session = Depends(get_db),
    user=Depends(get_current_user)
) -> dict:
    """Get status of bulk search operations for a dataset"""
    
    # Check if dataset exists
    table_name = f"ds_{file_id}"
    exists = db.execute(text(f"""
        SELECT EXISTS (
            SELECT FROM information_schema.tables 
            WHERE table_name = '{table_name}'
        );
    """)).scalar()
    
    if not exists:
        raise HTTPException(status_code=404, detail=f"Dataset {file_id} not found")
    
    # Get dataset info
    try:
        row_count = db.execute(text(f"SELECT COUNT(*) FROM {table_name}")).scalar()
        
        return {
            "file_id": file_id,
            "table_name": table_name,
            "row_count": row_count,
            "status": "ready",
            "search_capabilities": {
                "exact_match": True,
                "fuzzy_match": True,
                "multi_field_search": True,
                "separator_aware": True
            }
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get dataset status: {str(e)}")


@router.post("/bulk-search-export")
async def export_bulk_search_results(
    results: dict,
    format: str = "excel",
    db: Session = Depends(get_db),
    user=Depends(get_current_user)
) -> dict:
    """
    Export bulk search results in various formats
    """
    try:
        if format == "excel":
            # Generate Excel file
            import pandas as pd
            import io
            
            # Flatten results for Excel export
            export_data = []
            for result in results.get("results", []):
                user_data = result.get("user_data", {})
                search_result = result.get("search_result", {})
                db_record = search_result.get("database_record", {})
                price_calc = search_result.get("price_calculation", {})
                
                export_data.append({
                    "User_Part_Number": user_data.get("part_number", ""),
                    "User_Part_Name": user_data.get("part_name", ""),
                    "User_Quantity": user_data.get("quantity", 0),
                    "User_Manufacturer": user_data.get("manufacturer_name", ""),
                    "Match_Status": search_result.get("match_status", ""),
                    "Match_Type": search_result.get("match_type", ""),
                    "Confidence": search_result.get("confidence", 0),
                    "Found_Part_Number": db_record.get("part_number", ""),
                    "Found_Description": db_record.get("item_description", ""),
                    "Found_Company": db_record.get("company_name", ""),
                    "Found_Contact": db_record.get("contact_details", ""),
                    "Found_Email": db_record.get("email", ""),
                    "Secondary_Buyer": db_record.get("secondary_buyer", ""),
                    "Secondary_Buyer_Contact": db_record.get("secondary_buyer_contact", ""),
                    "Secondary_Buyer_Email": db_record.get("secondary_buyer_email", ""),
                    "Unit_Price": price_calc.get("unit_price", 0),
                    "Total_Cost": price_calc.get("total_cost", 0),
                    "Available_Quantity": price_calc.get("available_quantity", 0),
                    "UQC": db_record.get("uqc", ""),
                    "Search_Time_Ms": search_result.get("search_time_ms", 0)
                })
            
            # Create DataFrame and Excel file
            df = pd.DataFrame(export_data)
            excel_buffer = io.BytesIO()
            df.to_excel(excel_buffer, index=False, engine='openpyxl')
            excel_buffer.seek(0)
            
            return {
                "format": "excel",
                "filename": f"bulk_search_results_{int(time.time())}.xlsx",
                "data": excel_buffer.getvalue(),
                "content_type": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
            }
        
        elif format == "csv":
            # Generate CSV file
            import csv
            import io
            
            csv_buffer = io.StringIO()
            if results.get("results"):
                fieldnames = [
                    "User_Part_Number", "User_Part_Name", "User_Quantity", "User_Manufacturer",
                    "Match_Status", "Match_Type", "Confidence", "Found_Part_Number",
                    "Found_Description", "Found_Company", "Found_Contact", "Found_Email",
                    "Secondary_Buyer", "Secondary_Buyer_Contact", "Secondary_Buyer_Email",
                    "Unit_Price", "Total_Cost", "Available_Quantity", "UQC", "Search_Time_Ms"
                ]
                writer = csv.DictWriter(csv_buffer, fieldnames=fieldnames)
                writer.writeheader()
                
                for result in results.get("results", []):
                    user_data = result.get("user_data", {})
                    search_result = result.get("search_result", {})
                    db_record = search_result.get("database_record", {})
                    price_calc = search_result.get("price_calculation", {})
                    
                    writer.writerow({
                        "User_Part_Number": user_data.get("part_number", ""),
                        "User_Part_Name": user_data.get("part_name", ""),
                        "User_Quantity": user_data.get("quantity", 0),
                        "User_Manufacturer": user_data.get("manufacturer_name", ""),
                        "Match_Status": search_result.get("match_status", ""),
                        "Match_Type": search_result.get("match_type", ""),
                        "Confidence": search_result.get("confidence", 0),
                        "Found_Part_Number": db_record.get("part_number", ""),
                        "Found_Description": db_record.get("item_description", ""),
                        "Found_Company": db_record.get("company_name", ""),
                        "Found_Contact": db_record.get("contact_details", ""),
                        "Found_Email": db_record.get("email", ""),
                        "Secondary_Buyer": db_record.get("secondary_buyer", ""),
                        "Secondary_Buyer_Contact": db_record.get("secondary_buyer_contact", ""),
                        "Secondary_Buyer_Email": db_record.get("secondary_buyer_email", ""),
                        "Unit_Price": price_calc.get("unit_price", 0),
                        "Total_Cost": price_calc.get("total_cost", 0),
                        "Available_Quantity": price_calc.get("available_quantity", 0),
                        "UQC": db_record.get("uqc", ""),
                        "Search_Time_Ms": search_result.get("search_time_ms", 0)
                    })
            
            return {
                "format": "csv",
                "filename": f"bulk_search_results_{int(time.time())}.csv",
                "data": csv_buffer.getvalue(),
                "content_type": "text/csv"
            }
        
        else:
            raise HTTPException(status_code=400, detail="Unsupported export format")
            
    except Exception as e:
        logger.error(f"Export failed: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Export failed: {str(e)}")
