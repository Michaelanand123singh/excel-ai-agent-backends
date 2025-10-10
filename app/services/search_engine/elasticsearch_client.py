#!/usr/bin/env python3
"""
Elasticsearch client for ultra-fast bulk search
"""

import json
import time
from typing import List, Dict, Any, Optional
from elasticsearch import Elasticsearch
from elasticsearch.helpers import bulk
import logging

logger = logging.getLogger(__name__)

from app.core.config import settings

class ElasticsearchBulkSearch:
    """Ultra-fast bulk search using Elasticsearch"""
    
    def __init__(self, es_host: str | None = None, es_port: int | None = None):
        # Prefer env-configured Cloud ES endpoint
        self.es_host = es_host or settings.ES_HOST or "http://localhost"
        self.es_port = es_port or (443 if self.es_host.startswith("https") else 9200)
        self.es = None
        prefix = (settings.ES_INDEX_PREFIX or "parts_search").strip()
        self.index_name = prefix
        self.connect()
    
    def connect(self):
        """Connect to Elasticsearch"""
        try:
            # Prepare auth
            api_key = settings.ES_API_KEY
            username = settings.ES_USERNAME
            password = settings.ES_PASSWORD

            client_kwargs = {"request_timeout": max(1, int(settings.ES_TIMEOUT_MS / 1000))}

            if api_key:
                self.es = Elasticsearch(self.es_host, api_key=api_key, **client_kwargs)
            elif username and password:
                self.es = Elasticsearch(self.es_host, basic_auth=(username, password), **client_kwargs)
            else:
                # Local/dev fallback
                scheme = "https" if self.es_host.startswith("https") else "http"
                host_only = self.es_host.replace("https://", "").replace("http://", "").split(":")[0]
                self.es = Elasticsearch([{"host": host_only, "port": self.es_port, "scheme": scheme}], **client_kwargs)
            if self.es.ping():
                logger.info(f"✅ Connected to Elasticsearch at {self.es_host}")
            else:
                logger.error("❌ Failed to connect to Elasticsearch")
                self.es = None
        except Exception as e:
            logger.warning(f"⚠️ Elasticsearch connection error: {e}")
            self.es = None
    
    def is_available(self) -> bool:
        """Check if Elasticsearch is available"""
        return self.es is not None and self.es.ping()
    
    def create_index(self, table_name: str, file_id: int):
        """Create Elasticsearch index for a dataset"""
        if not self.is_available():
            logger.warning("Elasticsearch not available, skipping index creation")
            return False
        
        try:
            # Check if index already exists
            if self.es.indices.exists(index=self.index_name):
                logger.info(f"Index {self.index_name} already exists")
                return True
            
            # Create index with mapping (compatible with Elastic Cloud Serverless: avoid unsupported settings)
            mapping = {
                "mappings": {
                    "properties": {
                        "file_id": {"type": "integer"},
                        "part_number": {
                            "type": "text",
                            "analyzer": "standard",
                            "fields": {
                                "keyword": {"type": "keyword"}
                            }
                        },
                        "item_description": {
                            "type": "text",
                            "analyzer": "standard"
                        },
                        "company_name": {"type": "text"},
                        "contact_details": {"type": "text"},
                        "email": {"type": "keyword"},
                        "quantity": {"type": "integer"},
                        "unit_price": {"type": "float"},
                        "uqc": {"type": "text"},
                        "secondary_buyer": {"type": "text"},
                        "secondary_buyer_contact": {"type": "text"},
                        "secondary_buyer_email": {"type": "keyword"}
                    }
                }
            }
            
            self.es.indices.create(index=self.index_name, body=mapping)
            logger.info(f"✅ Created Elasticsearch index: {self.index_name}")
            return True
            
        except Exception as e:
            logger.error(f"❌ Failed to create Elasticsearch index: {e}")
            return False
    
    def index_data(self, data: List[Dict[str, Any]], file_id: int):
        """Index data from PostgreSQL to Elasticsearch"""
        if not self.is_available():
            logger.warning("Elasticsearch not available, skipping data indexing")
            return False
        
        try:
            # Prepare documents for bulk indexing
            documents = []
            for row in data:
                doc = {
                    "_index": self.index_name,
                    "_id": f"{file_id}_{row.get('id', '')}",
                    "_source": {
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
                }
                documents.append(doc)
            
            # Bulk index documents
            success_count, failed_items = bulk(self.es, documents, chunk_size=1000)
            logger.info(f"✅ Indexed {success_count} documents to Elasticsearch")
            
            if failed_items:
                logger.warning(f"⚠️ {len(failed_items)} documents failed to index")
            
            # Refresh index to make data searchable
            self.es.indices.refresh(index=self.index_name)
            return True
            
        except Exception as e:
            logger.error(f"❌ Failed to index data to Elasticsearch: {e}")
            return False
    
    def bulk_search(self, part_numbers: List[str], file_id: int, limit_per_part: int = 100000) -> Dict[str, Any]:
        """Perform ultra-fast bulk search using Elasticsearch"""
        if not self.is_available():
            raise Exception("Elasticsearch not available")
        
        start_time = time.perf_counter()
        
        try:
            # Build multi-search query
            msearch_body = []
            
            for part in part_numbers:
                # Add index specification
                msearch_body.append({"index": self.index_name})
                
                # Optimized query for ultra-fast ES searches
                search_query = {
                    "query": {
                        "bool": {
                            "must": [
                                {"term": {"file_id": file_id}}
                            ],
                            "should": [
                                # Exact match first (fastest)
                                {
                                    "term": {
                                        "part_number.keyword": {
                                            "value": part,
                                            "boost": 10.0
                                        }
                                    }
                                },
                                # Prefix match (fast)
                                {
                                    "prefix": {
                                        "part_number.keyword": {
                                            "value": part,
                                            "boost": 5.0
                                        }
                                    }
                                },
                                # Fuzzy match only if needed (slower but more flexible)
                                {
                                    "match": {
                                        "part_number": {
                                            "query": part,
                                            "boost": 2.0,
                                            "fuzziness": 1,
                                            "operator": "and"
                                        }
                                    }
                                }
                            ],
                            "minimum_should_match": 1
                        }
                    },
                    "track_total_hits": False,
                    "_source": {
                        "includes": [
                            "company_name",
                            "contact_details", 
                            "email",
                            "quantity",
                            "unit_price",
                            "item_description",
                            "part_number",
                            "uqc",
                            "secondary_buyer",
                            "secondary_buyer_contact",
                            "secondary_buyer_email"
                        ]
                    },
                    "size": limit_per_part,  # Show ALL results from dataset
                    "sort": [
                        {"_score": {"order": "desc"}},
                        {"unit_price": {"order": "asc"}}
                    ]
                }
                
                msearch_body.append(search_query)
            
            # Execute multi-search
            response = self.es.msearch(body=msearch_body)
            
            # Process results
            results = {}
            total_matches = 0
            
            for i, part in enumerate(part_numbers):
                part_results = response['responses'][i]
                
                if 'hits' in part_results:
                    hits = part_results['hits']['hits']
                    companies = []
                    
                    for hit in hits:
                        source = hit['_source']
                        score = hit.get('_score', 0)
                        
                        # Fast confidence estimation based on ES score
                        # ES score already includes relevance, so use it directly
                        confidence = min(100, max(0, (score / 10) * 100))  # Convert ES score to 0-100%
                        
                        # Simple match type based on score
                        if score > 8:
                            match_type = "exact"
                        elif score > 4:
                            match_type = "prefix"
                        else:
                            match_type = "fuzzy"
                        
                        company_data = {
                            "company_name": source.get("company_name", "N/A"),
                            "contact_details": source.get("contact_details", "N/A"),
                            "email": source.get("email", "N/A"),
                            "quantity": source.get("quantity", 0),
                            "unit_price": source.get("unit_price", 0.0),
                            "item_description": source.get("item_description", "N/A"),
                            "part_number": source.get("part_number", "N/A"),
                            "uqc": source.get("uqc", "N/A"),
                            "secondary_buyer": source.get("secondary_buyer", "N/A"),
                            "secondary_buyer_contact": source.get("secondary_buyer_contact", "N/A"),
                            "secondary_buyer_email": source.get("secondary_buyer_email", "N/A"),
                            "confidence": confidence,
                            "match_type": match_type,
                            "match_status": "found",
                            "confidence_breakdown": {
                                "part_number": {"score": confidence, "method": "elasticsearch_score", "details": f"ES score: {score}"},
                                "description": {"score": 0, "method": "not_calculated", "details": "Skipped for speed"},
                                "manufacturer": {"score": 0, "method": "not_calculated", "details": "Skipped for speed"},
                                "length_penalty": 0
                            }
                        }
                        companies.append(company_data)
                    
                    if companies:
                        results[part] = {
                            "companies": companies,
                            "total_matches": len(companies),
                            "match_type": "elasticsearch"
                        }
                        total_matches += len(companies)
            
            query_time = (time.perf_counter() - start_time) * 1000
            
            return {
                "results": results,
                "total_parts": len(part_numbers),
                "total_matches": total_matches,
                "latency_ms": query_time,
                "search_engine": "elasticsearch"
            }
            
        except Exception as e:
            logger.error(f"❌ Elasticsearch bulk search failed: {e}")
            raise Exception(f"Elasticsearch search failed: {e}")
    
    def delete_index(self):
        """Delete the Elasticsearch index"""
        if not self.is_available():
            return False
        
        try:
            if self.es.indices.exists(index=self.index_name):
                self.es.indices.delete(index=self.index_name)
                logger.info(f"✅ Deleted Elasticsearch index: {self.index_name}")
            return True
        except Exception as e:
            logger.error(f"❌ Failed to delete Elasticsearch index: {e}")
            return False
    
    def search_bulk_parts_all_files(self, part_numbers: List[str], search_mode: str = "hybrid", page: int = 1, page_size: int = 100) -> Dict[str, Any]:
        """
        Search part numbers across ALL files in Elasticsearch (no file_id filter)
        """
        if not self.is_available():
            raise Exception("Elasticsearch not available")
        
        start_time = time.perf_counter()
        
        try:
            # Prepare multi-search body
            msearch_body = []
            limit_per_part = min(page_size, 1000)  # Reasonable limit per part
            
            for part in part_numbers:
                # Build search query for all files (no file_id filter)
                if search_mode == "exact":
                    search_query = {
                        "index": self.index_name,
                        "body": {
                            "query": {
                                "bool": {
                                    "must": [
                                        {
                                            "term": {
                                                "part_number.keyword": part
                                            }
                                        }
                                    ]
                                }
                            },
                            "track_total_hits": False,
                            "_source": {
                                "includes": [
                                    "file_id",
                                    "company_name",
                                    "contact_details", 
                                    "email",
                                    "quantity",
                                    "unit_price",
                                    "item_description",
                                    "part_number",
                                    "uqc",
                                    "secondary_buyer",
                                    "secondary_buyer_contact",
                                    "secondary_buyer_email"
                                ]
                            },
                            "size": limit_per_part,
                            "sort": [
                                {"_score": {"order": "desc"}},
                                {"unit_price": {"order": "asc"}}
                            ]
                        }
                    }
                else:  # hybrid or fuzzy
                    search_query = {
                        "index": self.index_name,
                        "body": {
                            "query": {
                                "bool": {
                                    "should": [
                                        {
                                            "term": {
                                                "part_number.keyword": {
                                                    "value": part,
                                                    "boost": 3.0
                                                }
                                            }
                                        },
                                        {
                                            "match": {
                                                "part_number": {
                                                    "query": part,
                                                    "boost": 2.0,
                                                    "fuzziness": 1 if search_mode == "fuzzy" else 0,
                                                    "operator": "and"
                                                }
                                            }
                                        }
                                    ],
                                    "minimum_should_match": 1
                                }
                            },
                            "track_total_hits": False,
                            "_source": {
                                "includes": [
                                    "file_id",
                                    "company_name",
                                    "contact_details", 
                                    "email",
                                    "quantity",
                                    "unit_price",
                                    "item_description",
                                    "part_number",
                                    "uqc",
                                    "secondary_buyer",
                                    "secondary_buyer_contact",
                                    "secondary_buyer_email"
                                ]
                            },
                            "size": limit_per_part,
                            "sort": [
                                {"_score": {"order": "desc"}},
                                {"unit_price": {"order": "asc"}}
                            ]
                        }
                    }
                
                msearch_body.append(search_query)
            
            # Execute multi-search
            response = self.es.msearch(body=msearch_body)
            
            # Process results
            results = {}
            total_matches = 0
            
            for i, part in enumerate(part_numbers):
                part_results = response['responses'][i]
                
                if 'hits' in part_results:
                    hits = part_results['hits']['hits']
                    companies = []
                    
                    for hit in hits:
                        source = hit['_source']
                        score = hit.get('_score', 0)
                        file_id = source.get('file_id', 'unknown')
                        
                        # Fast confidence estimation based on ES score
                        confidence = min(100, max(0, (score / 10) * 100))
                        
                        # Simple match type based on score
                        if score > 8:
                            match_type = "exact"
                        elif score > 4:
                            match_type = "prefix"
                        else:
                            match_type = "fuzzy"
                        
                        company_data = {
                            "file_id": file_id,
                            "company_name": source.get("company_name", "N/A"),
                            "contact_details": source.get("contact_details", "N/A"),
                            "email": source.get("email", "N/A"),
                            "quantity": source.get("quantity", 0),
                            "unit_price": source.get("unit_price", 0.0),
                            "item_description": source.get("item_description", "N/A"),
                            "part_number": source.get("part_number", "N/A"),
                            "uqc": source.get("uqc", "N/A"),
                            "secondary_buyer": source.get("secondary_buyer", "N/A"),
                            "secondary_buyer_contact": source.get("secondary_buyer_contact", "N/A"),
                            "secondary_buyer_email": source.get("secondary_buyer_email", "N/A"),
                            "confidence": confidence,
                            "match_type": match_type,
                            "match_status": "found",
                            "confidence_breakdown": {
                                "part_number": {"score": confidence, "method": "elasticsearch_score", "details": f"ES score: {score}"},
                                "description": {"score": 0, "method": "not_calculated", "details": "Skipped for speed"},
                                "manufacturer": {"score": 0, "method": "not_calculated", "details": "Skipped for speed"},
                                "length_penalty": 0
                            }
                        }
                        companies.append(company_data)
                    
                    if companies:
                        results[part] = {
                            "companies": companies,
                            "total_matches": len(companies),
                            "match_type": "elasticsearch_all_files"
                        }
                        total_matches += len(companies)
            
            query_time = (time.perf_counter() - start_time) * 1000
            
            return {
                "results": results,
                "total_parts": len(part_numbers),
                "total_matches": total_matches,
                "latency_ms": query_time,
                "search_engine": "elasticsearch_all_files"
            }
            
        except Exception as e:
            logger.error(f"❌ Elasticsearch all-files search failed: {e}")
            raise Exception(f"Elasticsearch all-files search failed: {e}")

    def get_index_stats(self) -> Dict[str, Any]:
        """Get Elasticsearch index statistics"""
        if not self.is_available():
            return {"error": "Elasticsearch not available"}
        
        try:
            stats = self.es.indices.stats(index=self.index_name)
            return {
                "index_name": self.index_name,
                "document_count": stats['indices'][self.index_name]['total']['docs']['count'],
                "index_size": stats['indices'][self.index_name]['total']['store']['size_in_bytes'],
                "status": "healthy"
            }
        except Exception as e:
            return {"error": str(e)}
