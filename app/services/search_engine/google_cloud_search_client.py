#!/usr/bin/env python3
"""
Google Cloud Search Client for ultra-fast part number search
Primary search engine with Elasticsearch and PostgreSQL fallback
"""

import json
import time
import logging
from typing import List, Dict, Any, Optional
from google.cloud import discoveryengine_v1beta as discoveryengine
from google.oauth2 import service_account
import os

logger = logging.getLogger(__name__)

class GoogleCloudSearchClient:
    """Google Cloud Search client for part number search"""
    
    def __init__(self):
        self.project_id = os.getenv("GOOGLE_CLOUD_PROJECT_ID")
        self.index_id = os.getenv("GOOGLE_CLOUD_SEARCH_INDEX_ID", "parts-search-index")
        self.client = None
        self._is_available = None
        
        # Validate required environment variables
        if not self.project_id:
            logger.warning("⚠️ GOOGLE_CLOUD_PROJECT_ID not set, Google Cloud Search will not be available")
            return
        
        try:
            # Initialize credentials - handle both file path and JSON content
            credentials_path = os.getenv("GOOGLE_APPLICATION_CREDENTIALS")
            
            if credentials_path:
                # Check if it's a file path or JSON content
                if credentials_path.startswith('{'):
                    # It's JSON content, not a file path
                    import json
                    from google.oauth2 import service_account
                    try:
                        credentials_info = json.loads(credentials_path)
                        credentials = service_account.Credentials.from_service_account_info(credentials_info)
                        self.client = discoveryengine.SearchServiceClient(credentials=credentials)
                        logger.info("✅ Using service account from JSON content")
                    except Exception as e:
                        logger.warning(f"⚠️ Failed to parse JSON credentials, using default: {e}")
                        self.client = discoveryengine.SearchServiceClient()
                elif os.path.exists(credentials_path):
                    # It's a valid file path
                    from google.oauth2 import service_account
                    credentials = service_account.Credentials.from_service_account_file(credentials_path)
                    self.client = discoveryengine.SearchServiceClient(credentials=credentials)
                    logger.info("✅ Using service account from file")
                else:
                    # File doesn't exist, use default
                    logger.warning(f"⚠️ Credentials file not found: {credentials_path}, using default service account")
                    self.client = discoveryengine.SearchServiceClient()
            else:
                # No credentials specified, use default service account for Cloud Run
                self.client = discoveryengine.SearchServiceClient()
                logger.info("✅ Using default service account for Cloud Run")
            
            # Use data store format for Discovery Engine API
            self.data_store_name = f"projects/{self.project_id}/locations/global/dataStores/{self.index_id}"
            
        except Exception as e:
            logger.error(f"❌ Failed to initialize Google Cloud Search client: {e}")
            self.client = None
    
    def is_available(self) -> bool:
        """Check if Google Cloud Search is available"""
        if self._is_available is not None:
            return self._is_available
        
        # Check if client was initialized successfully
        if not self.client:
            self._is_available = False
            logger.warning("⚠️ Google Cloud Search client not initialized")
            return False
            
        try:
            # Try to get data store info
            request = discoveryengine.GetDataStoreRequest(name=self.data_store_name)
            self.client.get_data_store(request=request)
            self._is_available = True
            logger.info("✅ Google Cloud Search is available")
            return True
        except Exception as e:
            logger.warning(f"⚠️ Google Cloud Search not available: {e}")
            self._is_available = False
            return False
    
    def create_index(self, table_name: str, file_id: int) -> bool:
        """Create data store for part numbers (Discovery Engine API)"""
        if not self.client:
            logger.warning("⚠️ Google Cloud Search client not available")
            return False
            
        try:
            # Check if data store exists
            try:
                request = discoveryengine.GetDataStoreRequest(name=self.data_store_name)
                self.client.get_data_store(request=request)
                logger.info(f"Data store {self.data_store_name} already exists")
                return True
            except:
                pass  # Data store doesn't exist, create it
            
            # Create data store
            data_store = discoveryengine.DataStore(
                display_name="Parts Search Data Store",
                industry_vertical=discoveryengine.IndustryVertical.GENERIC,
                content_config=discoveryengine.DataStore.ContentConfig.CONTENT_REQUIRED,
                solution_types=[discoveryengine.SolutionType.SOLUTION_TYPE_SEARCH]
            )
            
            request = discoveryengine.CreateDataStoreRequest(
                parent=f"projects/{self.project_id}/locations/global",
                data_store=data_store,
                data_store_id=self.index_id
            )
            
            operation = self.client.create_data_store(request=request)
            operation.result()  # Wait for completion
            
            logger.info(f"✅ Created Google Cloud Search data store: {self.data_store_name}")
            return True
            
        except Exception as e:
            logger.error(f"❌ Failed to create data store: {e}")
            return False
    
    def index_data(self, data: List[Dict[str, Any]], file_id: int) -> bool:
        """Index part number data to Google Cloud Search"""
        if not self.client:
            logger.warning("⚠️ Google Cloud Search client not available")
            return False
            
        try:
            documents = []
            
            for i, row in enumerate(data):
                # Create document for Google Cloud Search
                doc = discoveryengine.Document(
                    name=f"{self.data_store_name}/documents/{file_id}_{i}",
                    struct_data={
                        "file_id": file_id,
                        "part_number": row.get("part_number", ""),
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
            
            # Batch index documents (process in chunks to avoid size limits)
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
    
    def bulk_search(self, part_numbers: List[str], file_id: int, limit_per_part: int = 20) -> Dict[str, Any]:
        """Perform ultra-fast bulk search using Google Cloud Search"""
        if not self.client:
            logger.warning("⚠️ Google Cloud Search client not available")
            raise Exception("Google Cloud Search client not available")
            
        try:
            start_time = time.perf_counter()
            results = {}
            total_matches = 0
            
            for part in part_numbers:
                # Build search query
                query = f"part_number:{part} AND file_id:{file_id}"
                
                # Execute search
                request = discoveryengine.SearchRequest(
                    serving_config=f"{self.data_store_name}/servingConfigs/default_config",
                    query=query,
                    page_size=limit_per_part,
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
                
                if companies:
                    # Calculate price summary
                    prices = [c.get('unit_price', 0) for c in companies if c.get('unit_price', 0) > 0]
                    quantities = [c.get('quantity', 0) for c in companies if c.get('quantity', 0) > 0]
                    
                    min_price = min(prices) if prices else 0.0
                    max_price = max(prices) if prices else 0.0
                    total_quantity = sum(quantities)
                    
                    results[part] = {
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
                        "latency_ms": 0,  # Will be set by caller
                        "table_name": f"ds_{file_id}",
                        "show_all": True,
                        "search_mode": "hybrid",
                        "match_type": "google_cloud_search",
                        "search_engine": "google_cloud_search"
                    }
                    total_matches += len(companies)
                else:
                    results[part] = {
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
                        "message": f"No matches found for part number '{part}'",
                        "cached": False,
                        "latency_ms": 0,
                        "table_name": f"ds_{file_id}",
                        "show_all": True,
                        "search_mode": "hybrid",
                        "match_type": "none",
                        "search_engine": "google_cloud_search"
                    }
            
            query_time = (time.perf_counter() - start_time) * 1000
            
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
                          page: int = 1, page_size: int = 50, show_all: bool = False) -> Dict[str, Any]:
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
            
            # Calculate total pages
            total_pages = 1 if show_all else int((len(companies) + page_size - 1) // page_size) if page_size > 0 else 1
            
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
                "total_pages": total_pages,
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
            logger.error(f"❌ Google Cloud Search single search failed: {e}")
            raise Exception(f"Google Cloud Search single search failed: {e}")
