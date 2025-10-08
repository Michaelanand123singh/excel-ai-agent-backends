"""
Unified Search Engine for Consistent Part Number Matching
Uses Elasticsearch as primary search engine with PostgreSQL fallback
Ensures single search and bulk search return identical results
"""

import time
import logging
from typing import Dict, Any, List, Optional, Tuple
from sqlalchemy.orm import Session
from sqlalchemy import text
from collections import defaultdict

from app.utils.helpers.part_number import (
    normalize, 
    similarity_score, 
    separator_tokenize,
    PART_NUMBER_CONFIG
)
from app.services.query_engine.confidence_calculator import confidence_calculator
from app.services.search_engine.elasticsearch_client import ElasticsearchBulkSearch
from app.services.search_engine.google_cloud_search_client import GoogleCloudSearchClient

logger = logging.getLogger(__name__)


class UnifiedSearchEngine:
    """Unified search engine that provides consistent results for both single and bulk search
    Uses Elasticsearch as primary search engine with PostgreSQL fallback for large datasets
    """
    
    def __init__(self, db: Session, table_name: str, file_id: int = None):
        self.db = db
        self.table_name = table_name
        self.file_id = file_id
        self.cache = {}  # Simple in-memory cache for repeated searches
        
        # Initialize Google Cloud Search client (primary) with error handling
        try:
            self.gcs_client = GoogleCloudSearchClient()
            self.gcs_available = self.gcs_client.is_available()
        except Exception as e:
            logger.warning(f"⚠️ Failed to initialize Google Cloud Search client: {e}")
            self.gcs_client = None
            self.gcs_available = False
        
        # Initialize Elasticsearch client (fallback) with error handling
        try:
            self.es_client = ElasticsearchBulkSearch()
            self.es_available = self.es_client.is_available()
        except Exception as e:
            logger.warning(f"⚠️ Failed to initialize Elasticsearch client: {e}")
            self.es_client = None
            self.es_available = False
        
        if self.gcs_available:
            logger.info(f"✅ Google Cloud Search available for {table_name}")
        elif self.es_available:
            logger.info(f"✅ Elasticsearch available for {table_name}")
        else:
            logger.warning(f"⚠️ Neither GCS nor ES available, using PostgreSQL fallback for {table_name}")
        
    def search_single_part(self, part_number: str, search_mode: str = "hybrid", 
                          page: int = 1, page_size: int = 100, show_all: bool = False) -> Dict[str, Any]:
        """
        Search for a single part number with comprehensive matching
        Uses Elasticsearch as primary search engine with PostgreSQL fallback
        Returns all similar matches available in the dataset
        """
        start_time = time.perf_counter()
        
        if not part_number or len(part_number.strip()) < 2:
            return self._create_empty_result(part_number, "Enter at least 2 characters to search")
        
        part_number = part_number.strip()
        
        # Try Google Cloud Search first (primary)
        if self.gcs_available and self.gcs_client and self.file_id:
            try:
                logger.info(f"🔍 Using Google Cloud Search for single search: {part_number}")
                result = self.gcs_client.search_single_part(
                    part_number=part_number,
                    file_id=self.file_id,
                    search_mode=search_mode,
                    page=page,
                    page_size=page_size,
                    show_all=show_all
                )
                if result and result.get('total_matches', 0) > 0:
                    result['search_engine'] = 'google_cloud_search'
                    result['latency_ms'] = int((time.perf_counter() - start_time) * 1000)
                    return result
                else:
                    logger.warning(f"⚠️ Google Cloud Search returned 0 results, falling back to Elasticsearch")
            except Exception as e:
                logger.warning(f"⚠️ Google Cloud Search failed, falling back to Elasticsearch: {e}")
        
        # Try Elasticsearch as fallback
        if self.es_available and self.es_client and self.file_id:
            try:
                logger.info(f"🔍 Using Elasticsearch for single search: {part_number}")
                result = self._search_with_elasticsearch([part_number], search_mode, page, page_size, show_all)
                if result and result.get('results', {}).get(part_number):
                    es_result = result['results'][part_number]
                    # Check if Elasticsearch returned meaningful results
                    if es_result.get('total_matches', 0) > 0:
                        es_result['search_engine'] = 'elasticsearch'
                        es_result['latency_ms'] = int((time.perf_counter() - start_time) * 1000)
                        return es_result
                    else:
                        logger.warning(f"⚠️ Elasticsearch returned 0 results, falling back to PostgreSQL")
                else:
                    logger.warning(f"⚠️ Elasticsearch returned no results, falling back to PostgreSQL")
            except Exception as e:
                logger.warning(f"⚠️ Elasticsearch search failed, falling back to PostgreSQL: {e}")
        
        # Fallback to PostgreSQL comprehensive search
        logger.info(f"🔍 Using PostgreSQL fallback for single search: {part_number}")
        all_matches, total_count = self._comprehensive_search_postgresql(part_number, search_mode, page, page_size)
        
        if not all_matches:
            return self._create_empty_result(part_number, f"No matches found for part number '{part_number}'")
        
        # Use the paginated results directly
        paginated_matches = all_matches
        prices = [match.get('unit_price', 0) for match in paginated_matches if match.get('unit_price', 0) > 0]
        quantities = [match.get('quantity', 0) for match in paginated_matches if match.get('quantity', 0) > 0]
        
        min_price = min(prices) if prices else 0.0
        max_price = max(prices) if prices else 0.0
        total_quantity = sum(quantities)
        
        # Format companies for response
        companies = []
        for match in paginated_matches:
            # Calculate confidence score using unified confidence calculator
            db_record = {
                "part_number": match.get('part_number', ''),
                "item_description": match.get('item_description', ''),
                "manufacturer": match.get('manufacturer', '')
            }
            
            confidence_data = confidence_calculator.calculate_confidence(
                search_part=part_number,
                search_name="",  # Not available in single search
                search_manufacturer="",  # Not available in single search
                db_record=db_record
            )
            
            company_data = {
                "company_name": match.get('company_name', 'N/A'),
                "contact_details": match.get('contact_details', 'N/A'),
                "email": match.get('email', 'N/A'),
                "quantity": int(match.get('quantity', 0)) if match.get('quantity') is not None else 0,
                "unit_price": float(match.get('unit_price', 0)) if match.get('unit_price') is not None else 0.0,
                "item_description": match.get('item_description', 'N/A'),
                "part_number": match.get('part_number', 'N/A'),
                "uqc": match.get('uqc', 'N/A'),
                "secondary_buyer": match.get('secondary_buyer', 'N/A'),
                "secondary_buyer_contact": match.get('secondary_buyer_contact', 'N/A'),
                "secondary_buyer_email": match.get('secondary_buyer_email', 'N/A'),
                "confidence": confidence_data["confidence"],
                "match_type": confidence_data["match_type"],
                "match_status": confidence_data["match_status"],
                "confidence_breakdown": confidence_data["breakdown"]
            }
            companies.append(company_data)
        
        # Calculate total pages
        total_pages = 1 if show_all else int((total_count + page_size - 1) // page_size) if page_size > 0 else 1
        
        return {
            "part_number": part_number,
            "total_matches": total_count,
            "companies": companies,
            "price_summary": {
                "min_price": min_price,
                "max_price": max_price,
                "total_quantity": total_quantity
            },
            "page": page,
            "page_size": page_size,
            "total_pages": total_pages,
            "message": f"Found {total_count} companies with part number '{part_number}'. Price range: ₹{min_price:.2f} - ₹{max_price:.2f}",
            "cached": False,
            "latency_ms": int((time.perf_counter() - start_time) * 1000),
            "table_name": self.table_name,
            "show_all": show_all,
            "search_mode": search_mode,
            "match_type": "unified_comprehensive",
            "search_engine": "postgresql_fallback"
        }
    
    def search_bulk_parts(self, part_numbers: List[str], search_mode: str = "hybrid",
                         page: int = 1, page_size: int = 100, show_all: bool = False) -> Dict[str, Any]:
        """
        Search for multiple part numbers using Elasticsearch as primary with PostgreSQL fallback
        Ensures consistent results between single and bulk search
        """
        start_time = time.perf_counter()
        
        # Try Google Cloud Search first (primary) - optimized for massive bulk searches
        if self.gcs_available and self.gcs_client and self.file_id:
            try:
                logger.info(f"🚀 Using Google Cloud Search for bulk search: {len(part_numbers)} parts (optimized for 50 lakh+ parts)")
                
                # For very large bulk searches (50 lakh+ parts), use chunked processing
                if len(part_numbers) > 10000:
                    logger.info(f"📦 Large bulk search detected ({len(part_numbers)} parts), using chunked processing")
                    return self._search_with_gcs_chunked(part_numbers, start_time)
                else:
                    # For smaller bulk searches, use direct bulk search
                    result = self.gcs_client.bulk_search(
                        part_numbers=part_numbers,
                        file_id=self.file_id,
                        limit_per_part=10000000  # Show ALL results from dataset (up to 1 crore)
                    )
                    if result and result.get('total_matches', 0) > 0:
                        result['search_engine'] = 'google_cloud_search'
                        result['latency_ms'] = int((time.perf_counter() - start_time) * 1000)
                        return result
                    else:
                        logger.warning(f"⚠️ Google Cloud Search returned 0 results for all parts, falling back to Elasticsearch")
            except Exception as e:
                logger.warning(f"⚠️ Google Cloud Search bulk search failed, falling back to Elasticsearch: {e}")
        
        # Try Elasticsearch as fallback
        if self.es_available and self.es_client and self.file_id:
            try:
                logger.info(f"🔍 Using Elasticsearch for bulk search: {len(part_numbers)} parts")
                
                # Add timeout handling for bulk search
                import signal
                import threading
                
                result = None
                timeout_occurred = False
                
                def timeout_handler():
                    nonlocal timeout_occurred
                    timeout_occurred = True
                    logger.warning(f"⚠️ Elasticsearch bulk search timed out after 25 seconds")
                
                # Set timeout for 25 seconds
                timer = threading.Timer(25.0, timeout_handler)
                timer.start()
                
                try:
                    result = self._search_with_elasticsearch(part_numbers, search_mode, page, page_size, show_all)
                finally:
                    timer.cancel()
                
                if timeout_occurred:
                    logger.warning(f"⚠️ Elasticsearch bulk search timed out, falling back to PostgreSQL")
                elif result:
                    # Check if Elasticsearch returned meaningful results for any part
                    has_results = False
                    for part_number in part_numbers:
                        if part_number in result.get('results', {}):
                            part_result = result['results'][part_number]
                            if part_result.get('total_matches', 0) > 0:
                                has_results = True
                                break
                    
                    if has_results:
                        result['search_engine'] = 'elasticsearch'
                        result['latency_ms'] = int((time.perf_counter() - start_time) * 1000)
                        return result
                    else:
                        logger.warning(f"⚠️ Elasticsearch returned 0 results for all parts, falling back to PostgreSQL")
                else:
                    logger.warning(f"⚠️ Elasticsearch returned no results, falling back to PostgreSQL")
            except Exception as e:
                logger.warning(f"⚠️ Elasticsearch bulk search failed, falling back to PostgreSQL: {e}")
        
        # Fallback to PostgreSQL - optimized bulk search
        logger.info(f"🔍 Using PostgreSQL fallback for bulk search: {len(part_numbers)} parts")
        results = {}
        
        try:
            # Use optimized bulk PostgreSQL search instead of individual searches
            results = self._search_with_postgresql_bulk(part_numbers, search_mode, page, page_size, show_all)
        except Exception as e:
            logger.error(f"❌ PostgreSQL bulk search failed: {e}")
            # Fallback to individual searches only if bulk fails
            for part_number in part_numbers:
                try:
                    result = self.search_single_part(part_number, search_mode, page, page_size, show_all)
                    results[part_number] = result
                except Exception as e:
                    results[part_number] = {
                        "part_number": part_number,
                        "total_matches": 0,
                        "companies": [],
                        "message": f"Search failed: {str(e)}",
                        "cached": False,
                        "latency_ms": 0,
                        "error": str(e)
                    }
        
        return {
            "results": results,
            "total_parts": len(part_numbers),
            "latency_ms": int((time.perf_counter() - start_time) * 1000),
            "search_engine": "postgresql_fallback"
        }
    
    def _search_with_gcs_chunked(self, part_numbers: List[str], start_time: float) -> Dict[str, Any]:
        """
        Handle massive bulk searches (50 lakh+ parts) using chunked Google Cloud Search
        Optimized for ultra-large datasets
        """
        try:
            logger.info(f"🚀 Processing massive bulk search with Google Cloud Search: {len(part_numbers)} parts")
            
            # Use optimal chunk size for Google Cloud Search (1000 parts per chunk)
            chunk_size = 1000
            aggregated_results = {}
            total_matches = 0
            processed_chunks = 0
            
            for i in range(0, len(part_numbers), chunk_size):
                chunk = part_numbers[i:i + chunk_size]
                processed_chunks += 1
                
                logger.info(f"📦 Processing chunk {processed_chunks}/{(len(part_numbers) + chunk_size - 1) // chunk_size} ({len(chunk)} parts)")
                
                try:
                    # Process chunk with Google Cloud Search
                    chunk_result = self.gcs_client.bulk_search(
                        part_numbers=chunk,
                        file_id=self.file_id,
                        limit_per_part=10000000  # Show ALL results from dataset
                    )
                    
                    if chunk_result and chunk_result.get('results'):
                        # Merge chunk results
                        for part_number, part_result in chunk_result['results'].items():
                            aggregated_results[part_number] = part_result
                            total_matches += part_result.get('total_matches', 0)
                    
                    logger.info(f"✅ Chunk {processed_chunks} completed: {chunk_result.get('total_matches', 0)} total matches")
                    
                except Exception as e:
                    logger.warning(f"⚠️ Chunk {processed_chunks} failed: {e}")
                    # Add empty results for failed chunk
                    for part_number in chunk:
                        aggregated_results[part_number] = {
                            "part_number": part_number,
                            "total_matches": 0,
                            "companies": [],
                            "message": f"Search failed: {str(e)}",
                            "cached": False,
                            "latency_ms": 0,
                            "error": str(e)
                        }
            
            logger.info(f"🎯 Massive bulk search completed: {total_matches} total matches across {len(part_numbers)} parts")
            
            return {
                "results": aggregated_results,
                "total_parts": len(part_numbers),
                "total_matches": total_matches,
                "latency_ms": int((time.perf_counter() - start_time) * 1000),
                "search_engine": "google_cloud_search_chunked",
                "chunks_processed": processed_chunks
            }
            
        except Exception as e:
            logger.error(f"❌ Massive bulk search with Google Cloud Search failed: {e}")
            raise e
    
    def _search_with_postgresql_bulk(self, part_numbers: List[str], search_mode: str, 
                                   page: int, page_size: int, show_all: bool) -> Dict[str, Any]:
        """
        Optimized bulk PostgreSQL search using a single query with ANY() operator
        Much faster than individual searches
        """
        try:
            # Create a single optimized query for all parts
            if search_mode == "exact":
                # Exact match search
                query = f"""
                SELECT 
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
                    'exact' as match_type,
                    100 as confidence
                FROM {self.table_name}
                WHERE LOWER(part_number) = ANY(%s)
                ORDER BY unit_price ASC
                LIMIT 10000
                """
                params = [part_numbers]
            elif search_mode == "fuzzy":
                # Fuzzy match search using similarity
                query = f"""
                SELECT 
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
                    'fuzzy' as match_type,
                    LEAST(100, GREATEST(0, (1 - levenshtein(LOWER(part_number), LOWER(%s)) / GREATEST(LENGTH(part_number), LENGTH(%s))) * 100)) as confidence
                FROM {self.table_name}
                WHERE LOWER(part_number) ILIKE ANY(%s)
                ORDER BY confidence DESC, unit_price ASC
                LIMIT 10000
                """
                # Create fuzzy patterns for each part
                fuzzy_patterns = [f"%{part}%" for part in part_numbers]
                params = [part_numbers[0], part_numbers[0], fuzzy_patterns]
            else:  # hybrid
                # Hybrid search: exact matches first, then fuzzy
                query = f"""
                WITH exact_matches AS (
                    SELECT 
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
                        'exact' as match_type,
                        100 as confidence,
                        part_number as search_part
                    FROM {self.table_name}
                    WHERE LOWER(part_number) = ANY(%s)
                ),
                fuzzy_matches AS (
                    SELECT 
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
                        'fuzzy' as match_type,
                        LEAST(100, GREATEST(0, (1 - levenshtein(LOWER(part_number), LOWER(%s)) / GREATEST(LENGTH(part_number), LENGTH(%s))) * 100)) as confidence,
                        %s as search_part
                    FROM {self.table_name}
                    WHERE LOWER(part_number) ILIKE ANY(%s)
                    AND LOWER(part_number) != ANY(%s)
                )
                SELECT * FROM exact_matches
                UNION ALL
                SELECT * FROM fuzzy_matches
                ORDER BY confidence DESC, unit_price ASC
                LIMIT 10000
                """
                fuzzy_patterns = [f"%{part}%" for part in part_numbers]
                params = [part_numbers, part_numbers[0], part_numbers[0], part_numbers[0], fuzzy_patterns, part_numbers]
            
            # Execute the optimized query
            result = self.db.execute(text(query), params)
            rows = result.fetchall()
            
            # Group results by part number
            results = {}
            for part_number in part_numbers:
                results[part_number] = {
                    "part_number": part_number,
                    "total_matches": 0,
                    "companies": [],
                    "message": "No matches found",
                    "cached": False,
                    "latency_ms": 0
                }
            
            # Process results and group by part number
            for row in rows:
                part_number = row.part_number
                if part_number in results:
                    company_data = {
                        "company_name": row.company_name or "N/A",
                        "contact_details": row.contact_details or "N/A",
                        "email": row.email or "N/A",
                        "quantity": row.quantity or 0,
                        "unit_price": float(row.unit_price or 0.0),
                        "item_description": row.item_description or "N/A",
                        "part_number": row.part_number or "N/A",
                        "uqc": row.uqc or "N/A",
                        "secondary_buyer": row.secondary_buyer or "N/A",
                        "secondary_buyer_contact": row.secondary_buyer_contact or "N/A",
                        "secondary_buyer_email": row.secondary_buyer_email or "N/A",
                        "confidence": float(row.confidence or 0),
                        "match_type": row.match_type or "unknown",
                        "match_status": "found",
                        "confidence_breakdown": {
                            "part_number": {"score": float(row.confidence or 0), "method": "postgresql_bulk", "details": "Bulk search optimization"},
                            "description": {"score": 0, "method": "not_calculated", "details": "Skipped for speed"},
                            "manufacturer": {"score": 0, "method": "not_calculated", "details": "Skipped for speed"},
                            "length_penalty": 0
                        }
                    }
                    results[part_number]["companies"].append(company_data)
                    results[part_number]["total_matches"] += 1
                    results[part_number]["message"] = f"Found {results[part_number]['total_matches']} matches"
            
            return results
            
        except Exception as e:
            logger.error(f"❌ PostgreSQL bulk search failed: {e}")
            raise e
    
    def _search_with_elasticsearch(self, part_numbers: List[str], search_mode: str, 
                                  page: int, page_size: int, show_all: bool) -> Dict[str, Any]:
        """
        Search using Elasticsearch for high performance with large datasets
        """
        try:
            # Use Elasticsearch bulk search with chunking to avoid oversized msearch bodies
            # For bulk search, show ALL results from dataset for each part
            limit_per_part = 10000000  # Show ALL results from dataset (up to 1 crore for massive datasets)

            # Optimized chunk size for ultra-fast ES searches
            # 50 parts per chunk = faster processing, better timeout handling
            chunk_size = 50  # Optimized for speed and timeout handling
            aggregated: Dict[str, Any] = {"results": {}, "total_parts": len(part_numbers)}

            for i in range(0, len(part_numbers), chunk_size):
                chunk = part_numbers[i:i + chunk_size]
                es_result = self.es_client.bulk_search(
                    part_numbers=chunk,
                    file_id=self.file_id,
                    limit_per_part=limit_per_part
                )

                # Merge chunk results
                for part_number in chunk:
                    if part_number in es_result.get('results', {}):
                        es_part_result = es_result['results'][part_number]
                        companies = es_part_result.get('companies', [])

                        # Apply pagination if needed
                        if not show_all and len(companies) > page_size:
                            start_idx = (page - 1) * page_size
                            end_idx = start_idx + page_size
                            companies = companies[start_idx:end_idx]

                        # Calculate price summary
                        prices = [c.get('unit_price', 0) for c in companies if c.get('unit_price', 0) > 0]
                        quantities = [c.get('quantity', 0) for c in companies if c.get('quantity', 0) > 0]

                        min_price = min(prices) if prices else 0.0
                        max_price = max(prices) if prices else 0.0
                        total_quantity = sum(quantities)

                        aggregated["results"][part_number] = {
                            "part_number": part_number,
                            "total_matches": len(companies),
                            "companies": companies,
                            "price_summary": {
                                "min_price": min_price,
                                "max_price": max_price,
                                "total_quantity": total_quantity
                            },
                            "page": page,
                            "page_size": page_size,
                            "total_pages": 1 if show_all else int((len(companies) + page_size - 1) // page_size),
                            "message": f"Found {len(companies)} companies with part number '{part_number}'. Price range: ₹{min_price:.2f} - ₹{max_price:.2f}",
                            "cached": False,
                            "latency_ms": 0,  # Will be set by caller
                            "table_name": self.table_name,
                            "show_all": show_all,
                            "search_mode": search_mode,
                            "match_type": "elasticsearch_comprehensive"
                        }
                    else:
                        aggregated["results"][part_number] = self._create_empty_result(part_number, f"No matches found for part number '{part_number}'")

            return {
                "results": aggregated["results"],
                "total_parts": len(part_numbers),
                "latency_ms": 0,  # Will be set by caller
                "search_engine": "elasticsearch"
            }
            
        except Exception as e:
            logger.error(f"❌ Elasticsearch search failed: {e}")
            raise e
    
    def _comprehensive_search_postgresql(self, part_number: str, search_mode: str, page: int = 1, page_size: int = 1000) -> Tuple[List[Dict[str, Any]], int]:
        """
        Comprehensive search that finds ALL similar matches in the dataset with pagination
        Uses multiple search strategies to ensure no matches are missed
        Returns (matches, total_count) for efficient pagination
        """
        all_matches = []
        seen_matches = set()  # To avoid duplicates
        
        # Strategy 1: Exact matches (highest priority)
        exact_matches = self._search_exact_matches(part_number)
        for match in exact_matches:
            match_key = self._get_match_key(match)
            if match_key not in seen_matches:
                all_matches.append(match)
                seen_matches.add(match_key)
        
        # Strategy 2: Normalized exact matches
        if search_mode in ("hybrid", "fuzzy"):
            normalized_matches = self._search_normalized_matches(part_number)
            for match in normalized_matches:
                match_key = self._get_match_key(match)
                if match_key not in seen_matches:
                    all_matches.append(match)
                    seen_matches.add(match_key)
        
        # Strategy 3: Fuzzy matches using PostgreSQL similarity
        if search_mode in ("hybrid", "fuzzy"):
            fuzzy_matches = self._search_fuzzy_matches(part_number)
            for match in fuzzy_matches:
                match_key = self._get_match_key(match)
                if match_key not in seen_matches:
                    all_matches.append(match)
                    seen_matches.add(match_key)
        
        # Strategy 4: Description-based matches
        if search_mode in ("hybrid", "fuzzy"):
            desc_matches = self._search_description_matches(part_number)
            for match in desc_matches:
                match_key = self._get_match_key(match)
                if match_key not in seen_matches:
                    all_matches.append(match)
                    seen_matches.add(match_key)
        
        # Strategy 5: Token-based matches (fallback)
        if search_mode in ("hybrid", "fuzzy") and not all_matches:
            token_matches = self._search_token_matches(part_number)
            for match in token_matches:
                match_key = self._get_match_key(match)
                if match_key not in seen_matches:
                    all_matches.append(match)
                    seen_matches.add(match_key)
        
        # Sort by relevance (exact matches first, then by similarity)
        all_matches.sort(key=lambda x: self._calculate_relevance_score(part_number, x), reverse=True)
        
        # Apply pagination
        total_count = len(all_matches)
        start_idx = (page - 1) * page_size
        end_idx = start_idx + page_size
        paginated_matches = all_matches[start_idx:end_idx]
        
        return paginated_matches, total_count
    
    def _search_exact_matches(self, part_number: str) -> List[Dict[str, Any]]:
        """Search for exact matches"""
        sql = f"""
            SELECT 
                "Potential Buyer 1" as company_name,
                "Potential Buyer 1 Contact Details" as contact_details,
                "Potential Buyer 1 email id" as email,
                "Quantity" as quantity,
                "Unit_Price" as unit_price,
                "Item_Description" as item_description,
                "part_number" as part_number,
                "UQC" as uqc,
                "Potential Buyer 2" as secondary_buyer,
                NULL as secondary_buyer_contact,
                NULL as secondary_buyer_email
            FROM {self.table_name}
            WHERE LOWER("part_number") = LOWER(:part_number)
            ORDER BY "Unit_Price" ASC
        """
        
        try:
            results = self.db.execute(text(sql), {"part_number": part_number}).fetchall()
            return [dict(row._mapping) for row in results]
        except Exception as e:
            logger.error(f"❌ Exact search failed: {e}")
            return []
    
    def _search_normalized_matches(self, part_number: str) -> List[Dict[str, Any]]:
        """Search for normalized matches (removing separators)"""
        normalized = normalize(part_number, 2)
        alnum_normalized = normalize(part_number, 3)
        
        sql = f"""
            SELECT 
                "Potential Buyer 1" as company_name,
                "Potential Buyer 1 Contact Details" as contact_details,
                "Potential Buyer 1 email id" as email,
                "Quantity" as quantity,
                "Unit_Price" as unit_price,
                "Item_Description" as item_description,
                "part_number" as part_number,
                "UQC" as uqc,
                "Potential Buyer 2" as secondary_buyer,
                NULL as secondary_buyer_contact,
                NULL as secondary_buyer_email
            FROM {self.table_name}
            WHERE 
                LOWER(REPLACE(REPLACE(REPLACE(REPLACE(REPLACE(REPLACE(REPLACE(REPLACE("part_number", '-', ''), '/', ''), ',', ''), '*', ''), '&', ''), '~', ''), '.', ''), '%', '')) = LOWER(:normalized)
                OR LOWER(REGEXP_REPLACE("part_number", '[^a-zA-Z0-9]+', '', 'g')) = LOWER(:alnum_normalized)
            ORDER BY "Unit_Price" ASC
        """
        
        try:
            results = self.db.execute(text(sql), {
                "normalized": normalized,
                "alnum_normalized": alnum_normalized
            }).fetchall()
            return [dict(row._mapping) for row in results]
        except Exception:
            return []
    
    def _search_fuzzy_matches(self, part_number: str) -> List[Dict[str, Any]]:
        """Search for fuzzy matches using PostgreSQL similarity"""
        min_similarity = PART_NUMBER_CONFIG.get("min_similarity", 0.3)  # Lower threshold for more matches
        
        sql = f"""
            SELECT 
                "Potential Buyer 1" as company_name,
                "Potential Buyer 1 Contact Details" as contact_details,
                "Potential Buyer 1 email id" as email,
                "Quantity" as quantity,
                "Unit_Price" as unit_price,
                "Item_Description" as item_description,
                "part_number" as part_number,
                "UQC" as uqc,
                "Potential Buyer 2" as secondary_buyer,
                NULL as secondary_buyer_contact,
                NULL as secondary_buyer_email,
                similarity(lower("part_number"), lower(:part_number)) as sim_score
            FROM {self.table_name}
            WHERE similarity(lower("part_number"), lower(:part_number)) >= :min_similarity
            ORDER BY sim_score DESC, "Unit_Price" ASC
        """
        
        try:
            results = self.db.execute(text(sql), {
                "part_number": part_number,
                "min_similarity": min_similarity
            }).fetchall()
            return [dict(row._mapping) for row in results]
        except Exception:
            return []
    
    def _search_description_matches(self, part_number: str) -> List[Dict[str, Any]]:
        """Search for matches in item descriptions"""
        sql = f"""
            SELECT 
                "Potential Buyer 1" as company_name,
                "Potential Buyer 1 Contact Details" as contact_details,
                "Potential Buyer 1 email id" as email,
                "Quantity" as quantity,
                "Unit_Price" as unit_price,
                "Item_Description" as item_description,
                "part_number" as part_number,
                "UQC" as uqc,
                "Potential Buyer 2" as secondary_buyer,
                NULL as secondary_buyer_contact,
                NULL as secondary_buyer_email,
                similarity(lower(CAST("Item_Description" AS TEXT)), lower(:part_number)) as sim_score
            FROM {self.table_name}
            WHERE 
                CAST("Item_Description" AS TEXT) ILIKE :pattern
                OR similarity(lower(CAST("Item_Description" AS TEXT)), lower(:part_number)) >= 0.3
            ORDER BY sim_score DESC, "Unit_Price" ASC
        """
        
        try:
            results = self.db.execute(text(sql), {
                "part_number": part_number,
                "pattern": f"%{part_number}%"
            }).fetchall()
            return [dict(row._mapping) for row in results]
        except Exception:
            return []
    
    def _search_token_matches(self, part_number: str) -> List[Dict[str, Any]]:
        """Search using token-based matching"""
        tokens = separator_tokenize(part_number)
        if not tokens:
            return []
        
        # Use first few tokens for broad matching
        search_tokens = tokens[:3]
        conditions = []
        params = {}
        
        for i, token in enumerate(search_tokens):
            conditions.append(f'CAST("Item_Description" AS TEXT) ILIKE :token_{i}')
            params[f'token_{i}'] = f'%{token}%'
        
        where_clause = " OR ".join(conditions)
        
        sql = f"""
            SELECT 
                "Potential Buyer 1" as company_name,
                "Potential Buyer 1 Contact Details" as contact_details,
                "Potential Buyer 1 email id" as email,
                "Quantity" as quantity,
                "Unit_Price" as unit_price,
                "Item_Description" as item_description,
                "part_number" as part_number,
                "UQC" as uqc,
                "Potential Buyer 2" as secondary_buyer,
                NULL as secondary_buyer_contact,
                NULL as secondary_buyer_email
            FROM {self.table_name}
            WHERE {where_clause}
            ORDER BY "Unit_Price" ASC
        """
        
        try:
            results = self.db.execute(text(sql), params).fetchall()
            return [dict(row._mapping) for row in results]
        except Exception:
            return []
    
    def _get_match_key(self, match: Dict[str, Any]) -> str:
        """Generate a unique key for a match to avoid duplicates"""
        return f"{match.get('part_number', '')}_{match.get('company_name', '')}_{match.get('unit_price', 0)}"
    
    def _calculate_relevance_score(self, search_part: str, match: Dict[str, Any]) -> float:
        """Calculate relevance score for sorting matches"""
        db_part = match.get('part_number', '')
        db_desc = match.get('item_description', '')
        
        # Exact match gets highest score
        if search_part.lower() == db_part.lower():
            return 100.0
        
        # Normalized exact match
        if normalize(search_part, 2).lower() == normalize(db_part, 2).lower():
            return 95.0
        
        # Alphanumeric exact match
        if normalize(search_part, 3).lower() == normalize(db_part, 3).lower():
            return 90.0
        
        # Similarity-based scoring
        part_similarity = similarity_score(search_part.lower(), db_part.lower())
        desc_similarity = similarity_score(search_part.lower(), db_desc.lower())
        
        return max(part_similarity * 100, desc_similarity * 80)
    
    def _create_empty_result(self, part_number: str, message: str) -> Dict[str, Any]:
        """Create empty result for no matches or errors"""
        return {
            "part_number": part_number,
            "total_matches": 0,
            "companies": [],
            "price_summary": {
                "min_price": 0.0,
                "max_price": 0.0,
                "total_quantity": 0
            },
            "page": 1,
            "page_size": 50,
            "total_pages": 1,
            "message": message,
            "cached": False,
            "latency_ms": 0,
            "table_name": self.table_name,
            "show_all": False,
            "search_mode": "hybrid",
            "match_type": "none"
        }
