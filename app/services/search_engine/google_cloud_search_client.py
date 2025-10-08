#!/usr/bin/env python3
"""
Google Cloud Search Client - Optimized for massive bulk searches
Handles 50 lakh+ part numbers with parallel processing
"""

import time
import logging
import json
from typing import Dict, Any, List, Optional
from google.cloud import discoveryengine_v1beta as discoveryengine
from google.oauth2 import service_account

logger = logging.getLogger(__name__)

class GoogleCloudSearchClient:
    """Google Cloud Search client optimized for massive bulk searches"""
    
    def __init__(self):
        """Initialize Google Cloud Search client"""
        self.client = None
        self.data_store_name = None
        self._is_available = None
        
        try:
            # Load credentials
            credentials = self._load_credentials()
            if not credentials:
                logger.warning("⚠️ Google Cloud Search credentials not available")
                return
            
            # Initialize client
            self.client = discoveryengine.SearchServiceClient(credentials=credentials)
            
            # Set data store name
            from app.core.config import get_settings
            settings = get_settings()
            project_id = settings.GOOGLE_CLOUD_PROJECT_ID
            index_id = settings.GOOGLE_CLOUD_SEARCH_INDEX_ID
            
            if project_id and index_id:
                self.data_store_name = f"projects/{project_id}/locations/global/collections/default_collection/dataStores/{index_id}"
                logger.info(f"✅ Google Cloud Search client initialized: {self.data_store_name}")
            else:
                logger.warning("⚠️ Google Cloud Search configuration incomplete")
                self.client = None
                
        except Exception as e:
            logger.error(f"❌ Failed to initialize Google Cloud Search client: {e}")
            self.client = None
    
    def _load_credentials(self):
        """Load Google Cloud credentials"""
        try:
            from app.core.config import get_settings
            settings = get_settings()
            
            # Try to load from file path first
            if settings.GOOGLE_APPLICATION_CREDENTIALS:
                try:
                    # Check if it's a file path or JSON content
                    if settings.GOOGLE_APPLICATION_CREDENTIALS.startswith('{'):
                        # It's JSON content
                        credentials_info = json.loads(settings.GOOGLE_APPLICATION_CREDENTIALS)
                        return service_account.Credentials.from_service_account_info(credentials_info)
                    else:
                        # It's a file path
                        return service_account.Credentials.from_service_account_file(settings.GOOGLE_APPLICATION_CREDENTIALS)
                except Exception as e:
                    logger.warning(f"⚠️ Failed to load credentials: {e}")
            
            # Try default credentials
            return None
            
        except Exception as e:
            logger.warning(f"⚠️ Failed to load credentials: {e}")
            return None
    
    def is_available(self) -> bool:
        """Check if Google Cloud Search is available"""
        if self._is_available is not None:
            return self._is_available
        
        if not self.client or not self.data_store_name:
            self._is_available = False
            logger.warning("⚠️ Google Cloud Search client not initialized")
            return False
        
        try:
            # Test the connection
            request = discoveryengine.SearchRequest(
                serving_config=f"{self.data_store_name}/servingConfigs/default_config",
                query="test",
                page_size=1
            )
            self.client.search(request=request)
            self._is_available = True
            logger.info("✅ Google Cloud Search is available")
            return True
        except Exception as e:
            self._is_available = False
            logger.warning(f"⚠️ Google Cloud Search not available: {e}")
            return False
    
    def create_index(self, table_name: str, file_id: int) -> bool:
        """Create data store for Google Cloud Search"""
        if not self.client:
            logger.warning("⚠️ Google Cloud Search client not available")
            return False
        
        try:
            from app.core.config import get_settings
            settings = get_settings()
            project_id = settings.GOOGLE_CLOUD_PROJECT_ID
            index_id = settings.GOOGLE_CLOUD_SEARCH_INDEX_ID
            
            if not project_id or not index_id:
                logger.warning("⚠️ Google Cloud Search configuration incomplete")
                return False
            
            # Data store already exists, just update the name
            self.data_store_name = f"projects/{project_id}/locations/global/collections/default_collection/dataStores/{index_id}"
            logger.info(f"✅ Google Cloud Search data store ready: {self.data_store_name}")
            return True
            
        except Exception as e:
            logger.error(f"❌ Failed to create Google Cloud Search index: {e}")
            return False
    
    def index_data(self, data: List[Dict], file_id: int) -> bool:
        """Index data to Google Cloud Search"""
        if not self.client or not self.data_store_name:
            logger.warning("⚠️ Google Cloud Search client not available")
            return False
        
        try:
            documents = []
            for row in data:
                doc = discoveryengine.Document(
                    id=f"ds_{file_id}_{row.get('id', '')}",
                    struct_data={
                        "file_id": file_id,
                        "part_number": row.get("Part_Number", ""),
                        "item_description": row.get("Item_Description", ""),
                        "company_name": row.get("Potential Buyer 1", ""),
                        "contact_details": row.get("Potential Buyer 1 Contact Details", ""),
                        "email": row.get("Potential Buyer 1 email id", ""),
                        "quantity": row.get("Quantity", 0),
                        "unit_price": row.get("Unit_Price", 0.0),
                        "uqc": row.get("UQC", ""),
                        "secondary_buyer": row.get("Potential Buyer 2", ""),
                        "secondary_buyer_contact": row.get("Potential Buyer 2 Contact Details", ""),
                        "secondary_buyer_email": row.get("Potential Buyer 2 email id", "")
                    }
                )
                documents.append(doc)
            
            # Batch index documents
            chunk_size = 1000
            for i in range(0, len(documents), chunk_size):
                chunk = documents[i:i + chunk_size]
                request = discoveryengine.BatchCreateDocumentsRequest(
                    parent=self.data_store_name,
                    documents=chunk
                )
                
                response = self.client.batch_create_documents(request=request)
                logger.info(f"✅ Indexed {len(chunk)} documents to Google Cloud Search (chunk {i//chunk_size + 1})")
            
            logger.info(f"✅ Successfully indexed {len(documents)} total documents to Google Cloud Search")
            return True
            
        except Exception as e:
            logger.error(f"❌ Failed to index data: {e}")
            return False
    
    def bulk_search(self, part_numbers: List[str], file_id: int, limit_per_part: int = 10000000) -> Dict[str, Any]:
        """Perform ultra-fast bulk search using Google Cloud Search - optimized for massive datasets"""
        if not self.client:
            logger.warning("⚠️ Google Cloud Search client not available")
            raise Exception("Google Cloud Search client not available")
            
        try:
            start_time = time.perf_counter()
            results = {}
            total_matches = 0
            
            logger.info(f"🚀 Google Cloud Search bulk search: {len(part_numbers)} parts (limit: {limit_per_part} per part)")
            
            # Process parts in parallel for better performance
            import concurrent.futures
            
            def _iterate_gcs(part: str):
                """Fetch all pages from GCS for a single part up to limit_per_part."""
                collected = []
                next_token = ""
                remaining = max(0, int(limit_per_part)) if limit_per_part else 10000000
                while remaining > 0:
                    page_size = min(remaining, 1000)  # GCS page_size practical cap
                    request = discoveryengine.SearchRequest(
                        serving_config=f"{self.data_store_name}/servingConfigs/default_config",
                        query=f"part_number:{part} AND file_id:{file_id}",
                        page_size=page_size,
                        page_token=next_token or None,
                        query_expansion_spec=discoveryengine.SearchRequest.QueryExpansionSpec(
                            mode=discoveryengine.SearchRequest.QueryExpansionSpec.Mode.AUTO
                        ),
                        spell_correction_spec=discoveryengine.SearchRequest.SpellCorrectionSpec(
                            mode=discoveryengine.SearchRequest.SpellCorrectionSpec.Mode.AUTO
                        ),
                        content_search_spec=discoveryengine.SearchRequest.ContentSearchSpec(
                            extractive_content_spec=discoveryengine.SearchRequest.ContentSearchSpec.ExtractiveContentSpec(
                                max_extractive_answer_count=1
                            ),
                            snippet_spec=discoveryengine.SearchRequest.ContentSearchSpec.SnippetSpec(
                                return_snippets=True
                            )
                        )
                    )
                    response = self.client.search(request=request)
                    batch = []
                    for result in response.results:
                        struct_data = result.document.struct_data
                        relevance_score = getattr(result, 'relevance_score', 0.0)
                        confidence = min(100, max(0, relevance_score * 100))
                        if relevance_score > 0.9:
                            match_type = "exact"
                        elif relevance_score > 0.7:
                            match_type = "prefix"
                        else:
                            match_type = "fuzzy"
                        batch.append({
                            "company_name": struct_data.get("company_name", "N/A"),
                            "contact_details": struct_data.get("contact_details", "N/A"),
                            "email": struct_data.get("email", "N/A"),
                            "quantity": int(struct_data.get("quantity", 0)) if struct_data.get("quantity") is not None else 0,
                            "unit_price": float(struct_data.get("unit_price", 0)) if struct_data.get("unit_price") is not None else 0.0,
                            "item_description": struct_data.get("item_description", "N/A"),
                            "part_number": struct_data.get("part_number", "N/A"),
                            "uqc": struct_data.get("uqc", "N/A"),
                            "secondary_buyer": struct_data.get("secondary_buyer", "N/A"),
                            "secondary_buyer_contact": struct_data.get("secondary_buyer_contact", "N/A"),
                            "secondary_buyer_email": struct_data.get("secondary_buyer_email", "N/A"),
                            "confidence": confidence,
                            "match_type": match_type,
                            "match_status": "found",
                            "confidence_breakdown": {
                                "part_number": {"score": confidence, "method": "google_cloud_search", "details": f"Relevance: {relevance_score}"},
                                "description": {"score": 0, "method": "not_calculated", "details": "Skipped for speed"},
                                "manufacturer": {"score": 0, "method": "not_calculated", "details": "Skipped for speed"},
                                "length_penalty": 0
                            }
                        })
                    collected.extend(batch)
                    remaining -= len(batch)
                    next_token = getattr(response, 'next_page_token', '') or ''
                    if not next_token or len(batch) == 0:
                        break
                return collected

            def search_single_part_gcs(part):
                try:
                    # Pull all pages up to limit_per_part
                    companies = _iterate_gcs(part)
                    
                    if companies:
                        # Calculate price summary
                        prices = [c.get('unit_price', 0) for c in companies if c.get('unit_price', 0) > 0]
                        quantities = [c.get('quantity', 0) for c in companies if c.get('quantity', 0) > 0]
                        
                        min_price = min(prices) if prices else 0.0
                        max_price = max(prices) if prices else 0.0
                        total_quantity = sum(quantities)
                        
                        return {
                            "part_number": part,
                            "total_matches": len(companies),
                            "companies": companies,
                            "price_summary": {
                                "min_price": min_price,
                                "max_price": max_price,
                                "total_quantity": total_quantity
                            },
                            "page": 1,
                            "page_size": limit_per_part,
                            "total_pages": 1,
                            "message": f"Found {len(companies)} companies with part number '{part}'. Price range: ₹{min_price:.2f} - ₹{max_price:.2f}",
                            "cached": False,
                            "latency_ms": 0,
                            "table_name": f"ds_{file_id}",
                            "show_all": True,
                            "search_mode": "hybrid",
                            "match_type": "google_cloud_search",
                            "search_engine": "google_cloud_search"
                        }
                    else:
                        return {
                            "part_number": part,
                            "total_matches": 0,
                            "companies": [],
                            "price_summary": {
                                "min_price": 0.0,
                                "max_price": 0.0,
                                "total_quantity": 0
                            },
                            "page": 1,
                            "page_size": limit_per_part,
                            "total_pages": 1,
                            "message": f"No companies found with part number '{part}'",
                            "cached": False,
                            "latency_ms": 0,
                            "table_name": f"ds_{file_id}",
                            "show_all": True,
                            "search_mode": "hybrid",
                            "match_type": "google_cloud_search",
                            "search_engine": "google_cloud_search"
                        }
                        
                except Exception as e:
                    logger.warning(f"⚠️ Google Cloud Search failed for part {part}: {e}")
                    return {
                        "part_number": part,
                        "total_matches": 0,
                        "companies": [],
                        "message": f"Search failed: {str(e)}",
                        "cached": False,
                        "latency_ms": 0,
                        "error": str(e)
                    }
            
            # Use ThreadPoolExecutor for parallel processing
            max_workers = min(10, len(part_numbers))  # Limit to 10 concurrent requests
            with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as executor:
                # Submit all search tasks
                future_to_part = {executor.submit(search_single_part_gcs, part): part for part in part_numbers}
                
                # Collect results as they complete
                for future in concurrent.futures.as_completed(future_to_part):
                    part = future_to_part[future]
                    try:
                        result = future.result()
                        results[part] = result
                        total_matches += result.get('total_matches', 0)
                    except Exception as e:
                        logger.warning(f"⚠️ Failed to process part {part}: {e}")
                        results[part] = {
                            "part_number": part,
                            "total_matches": 0,
                            "companies": [],
                            "message": f"Search failed: {str(e)}",
                            "cached": False,
                            "latency_ms": 0,
                            "error": str(e)
                        }
            
            query_time = (time.perf_counter() - start_time) * 1000
            logger.info(f"🎯 Google Cloud Search bulk completed: {total_matches} matches in {query_time:.2f}ms")
            
            return {
                "results": results,
                "total_parts": len(part_numbers),
                "total_matches": total_matches,
                "latency_ms": query_time,
                "search_engine": "google_cloud_search"
            }
            
        except Exception as e:
            logger.error(f"❌ Google Cloud Search failed: {e}")
            raise Exception(f"Google Cloud Search failed: {e}")
    
    def search_single_part(self, part_number: str, file_id: int, search_mode: str = "hybrid", 
                          page: int = 1, page_size: int = 100, show_all: bool = False) -> Dict[str, Any]:
        """Search for a single part number using Google Cloud Search"""
        if not self.client:
            logger.warning("⚠️ Google Cloud Search client not available")
            raise Exception("Google Cloud Search client not available")
            
        try:
            start_time = time.perf_counter()
            
            # Build search query
            query = f"part_number:{part_number} AND file_id:{file_id}"
            
            # Execute search
            request = discoveryengine.SearchRequest(
                serving_config=f"{self.data_store_name}/servingConfigs/default_config",
                query=query,
                page_size=page_size if not show_all else 1000,
                query_expansion_spec=discoveryengine.SearchRequest.QueryExpansionSpec(
                    mode=discoveryengine.SearchRequest.QueryExpansionSpec.Mode.AUTO
                ),
                spell_correction_spec=discoveryengine.SearchRequest.SpellCorrectionSpec(
                    mode=discoveryengine.SearchRequest.SpellCorrectionSpec.Mode.AUTO
                ),
                content_search_spec=discoveryengine.SearchRequest.ContentSearchSpec(
                    extractive_content_spec=discoveryengine.SearchRequest.ContentSearchSpec.ExtractiveContentSpec(
                        max_extractive_answer_count=1
                    ),
                    snippet_spec=discoveryengine.SearchRequest.ContentSearchSpec.SnippetSpec(
                        return_snippets=True
                    )
                )
            )
            
            response = self.client.search(request=request)
            
            # Process results
            companies = []
            for result in response.results:
                struct_data = result.document.struct_data
                
                # Calculate confidence based on relevance score
                relevance_score = getattr(result, 'relevance_score', 0.0)
                confidence = min(100, max(0, relevance_score * 100))
                
                # Determine match type
                if relevance_score > 0.9:
                    match_type = "exact"
                elif relevance_score > 0.7:
                    match_type = "prefix"
                else:
                    match_type = "fuzzy"
                
                company_data = {
                    "company_name": struct_data.get("company_name", "N/A"),
                    "contact_details": struct_data.get("contact_details", "N/A"),
                    "email": struct_data.get("email", "N/A"),
                    "quantity": int(struct_data.get("quantity", 0)) if struct_data.get("quantity") is not None else 0,
                    "unit_price": float(struct_data.get("unit_price", 0)) if struct_data.get("unit_price") is not None else 0.0,
                    "item_description": struct_data.get("item_description", "N/A"),
                    "part_number": struct_data.get("part_number", "N/A"),
                    "uqc": struct_data.get("uqc", "N/A"),
                    "secondary_buyer": struct_data.get("secondary_buyer", "N/A"),
                    "secondary_buyer_contact": struct_data.get("secondary_buyer_contact", "N/A"),
                    "secondary_buyer_email": struct_data.get("secondary_buyer_email", "N/A"),
                    "confidence": confidence,
                    "match_type": match_type,
                    "match_status": "found",
                    "confidence_breakdown": {
                        "part_number": {"score": confidence, "method": "google_cloud_search", "details": f"Relevance: {relevance_score}"},
                        "description": {"score": 0, "method": "not_calculated", "details": "Skipped for speed"},
                        "manufacturer": {"score": 0, "method": "not_calculated", "details": "Skipped for speed"},
                        "length_penalty": 0
                    }
                }
                companies.append(company_data)
            
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
            
            query_time = (time.perf_counter() - start_time) * 1000
            
            return {
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
                "total_pages": 1,
                "message": f"Found {len(companies)} companies with part number '{part_number}'. Price range: ₹{min_price:.2f} - ₹{max_price:.2f}",
                "cached": False,
                "latency_ms": query_time,
                "table_name": f"ds_{file_id}",
                "show_all": show_all,
                "search_mode": search_mode,
                "match_type": "google_cloud_search",
                "search_engine": "google_cloud_search"
            }
            
        except Exception as e:
            logger.error(f"❌ Google Cloud Search failed: {e}")
            raise Exception(f"Google Cloud Search failed: {e}")
