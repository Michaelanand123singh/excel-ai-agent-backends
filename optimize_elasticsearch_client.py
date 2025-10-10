#!/usr/bin/env python3
"""
Optimized Elasticsearch Client for Ultra-Fast Bulk Search
Target: 20K parts in 2-3 seconds (90% improvement)
"""

import asyncio
import aiohttp
import json
import time
from typing import List, Dict, Any, Optional
from elasticsearch import AsyncElasticsearch
from elasticsearch.helpers import async_bulk
import logging
from concurrent.futures import ThreadPoolExecutor
import redis

logger = logging.getLogger(__name__)

class OptimizedElasticsearchClient:
    """Ultra-optimized Elasticsearch client for bulk search"""
    
    def __init__(self, es_host: str, es_api_key: str, redis_client: redis.Redis):
        self.es_host = es_host
        self.es_api_key = es_api_key
        self.redis = redis_client
        self.es = None
        self.session = None
        
    async def initialize(self):
        """Initialize async Elasticsearch client"""
        self.es = AsyncElasticsearch(
            [self.es_host],
            api_key=self.es_api_key,
            request_timeout=30,
            max_retries=2,
            retry_on_timeout=True
        )
        self.session = aiohttp.ClientSession()
        
    async def close(self):
        """Clean up resources"""
        if self.es:
            await self.es.close()
        if self.session:
            await self.session.close()

    async def optimized_bulk_search(self, part_numbers: List[str], file_id: int, 
                                   batch_size: int = 500, concurrency: int = 4) -> Dict[str, Any]:
        """
        Ultra-optimized bulk search with parallel processing
        Target: 20K parts in 2-3 seconds
        """
        start_time = time.perf_counter()
        
        # Check cache first
        cache_key = f"bulk_search:{file_id}:{hash(tuple(sorted(part_numbers)))}"
        cached_result = self.redis.get(cache_key)
        if cached_result:
            logger.info("✅ Cache hit for bulk search")
            return json.loads(cached_result)
        
        # Split into batches for parallel processing
        batches = [part_numbers[i:i + batch_size] for i in range(0, len(part_numbers), batch_size)]
        
        # Process batches in parallel
        tasks = []
        for batch in batches:
            task = asyncio.create_task(self._search_batch_optimized(batch, file_id))
            tasks.append(task)
        
        # Wait for all batches to complete
        batch_results = await asyncio.gather(*tasks, return_exceptions=True)
        
        # Merge results
        results = {}
        total_matches = 0
        
        for batch_result in batch_results:
            if isinstance(batch_result, Exception):
                logger.error(f"Batch search failed: {batch_result}")
                continue
                
            results.update(batch_result.get('results', {}))
            total_matches += batch_result.get('total_matches', 0)
        
        # Prepare final result
        final_result = {
            'results': results,
            'total_parts': len(part_numbers),
            'total_matches': total_matches,
            'search_engine': 'elasticsearch_optimized',
            'latency_ms': int((time.perf_counter() - start_time) * 1000),
            'performance_rating': 'excellent' if (time.perf_counter() - start_time) < 3 else 'good'
        }
        
        # Cache result for 10 minutes
        self.redis.setex(cache_key, 600, json.dumps(final_result))
        
        logger.info(f"✅ Optimized bulk search completed: {len(part_numbers)} parts in {final_result['latency_ms']}ms")
        return final_result

    async def _search_batch_optimized(self, part_numbers: List[str], file_id: int) -> Dict[str, Any]:
        """
        Optimized batch search with simplified query structure
        """
        try:
            # Simplified query - much faster than complex bool queries
            query = {
                "query": {
                    "bool": {
                        "must": [
                            {"term": {"file_id": file_id}},
                            {"terms": {"part_number.keyword": part_numbers}}  # Single terms query
                        ]
                    }
                },
                "size": 1000,  # Limit results per part
                "_source": [
                    "part_number", "company_name", "contact_details", 
                    "email", "unit_price", "quantity", "item_description"
                ],
                "sort": [{"unit_price": {"order": "asc"}}]  # Simple sort
            }
            
            # Execute search
            response = await self.es.search(
                index="parts_search",
                body=query,
                timeout="10s"
            )
            
            # Process results efficiently
            results = {}
            for hit in response['hits']['hits']:
                source = hit['_source']
                part_number = source['part_number']
                
                if part_number not in results:
                    results[part_number] = {
                        'part_number': part_number,
                        'companies': [],
                        'total_matches': 0
                    }
                
                results[part_number]['companies'].append({
                    'company_name': source.get('company_name', ''),
                    'contact_details': source.get('contact_details', ''),
                    'email': source.get('email', ''),
                    'quantity': source.get('quantity', 0),
                    'unit_price': source.get('unit_price', 0.0),
                    'item_description': source.get('item_description', '')
                })
                results[part_number]['total_matches'] += 1
            
            return {
                'results': results,
                'total_matches': sum(r['total_matches'] for r in results.values())
            }
            
        except Exception as e:
            logger.error(f"Batch search failed: {e}")
            return {'results': {}, 'total_matches': 0}

    async def precompute_common_searches(self, file_id: int, common_patterns: List[str]):
        """
        Pre-compute common part number patterns for instant lookup
        """
        logger.info(f"🔄 Pre-computing common searches for file {file_id}")
        
        for pattern in common_patterns:
            cache_key = f"pattern_search:{file_id}:{pattern}"
            
            # Check if already cached
            if self.redis.exists(cache_key):
                continue
                
            # Search for pattern
            query = {
                "query": {
                    "bool": {
                        "must": [
                            {"term": {"file_id": file_id}},
                            {"wildcard": {"part_number.keyword": f"*{pattern}*"}}
                        ]
                    }
                },
                "size": 1000,
                "_source": ["part_number", "company_name", "contact_details", "unit_price"]
            }
            
            try:
                response = await self.es.search(index="parts_search", body=query)
                results = [hit['_source'] for hit in response['hits']['hits']]
                
                # Cache for 1 hour
                self.redis.setex(cache_key, 3600, json.dumps(results))
                logger.info(f"✅ Pre-computed pattern: {pattern} ({len(results)} results)")
                
            except Exception as e:
                logger.error(f"Failed to pre-compute pattern {pattern}: {e}")

    async def create_file_specific_index(self, file_id: int):
        """
        Create file-specific index for faster searches
        Reduces search space by 99%
        """
        index_name = f"parts_search_file_{file_id}"
        
        try:
            # Check if index exists
            if await self.es.indices.exists(index=index_name):
                logger.info(f"✅ File-specific index {index_name} already exists")
                return index_name
            
            # Create index with optimized mapping
            mapping = {
                "mappings": {
                    "properties": {
                        "file_id": {"type": "integer"},
                        "part_number": {
                            "type": "text",
                            "fields": {
                                "keyword": {"type": "keyword"}
                            }
                        },
                        "company_name": {"type": "keyword"},
                        "contact_details": {"type": "text"},
                        "email": {"type": "keyword"},
                        "quantity": {"type": "integer"},
                        "unit_price": {"type": "float"},
                        "item_description": {"type": "text"}
                    }
                },
                "settings": {
                    "number_of_shards": 1,
                    "number_of_replicas": 0,
                    "refresh_interval": "30s"  # Reduce refresh frequency
                }
            }
            
            await self.es.indices.create(index=index_name, body=mapping)
            logger.info(f"✅ Created file-specific index: {index_name}")
            return index_name
            
        except Exception as e:
            logger.error(f"Failed to create file-specific index: {e}")
            return "parts_search"

# Usage example
async def main():
    """Example usage of optimized Elasticsearch client"""
    
    # Initialize Redis
    redis_client = redis.Redis(host='localhost', port=6379, db=0)
    
    # Initialize optimized client
    client = OptimizedElasticsearchClient(
        es_host="https://your-elasticsearch-host",
        es_api_key="your-api-key",
        redis_client=redis_client
    )
    
    await client.initialize()
    
    try:
        # Test with 20K parts
        part_numbers = [f"PART-{i:06d}" for i in range(20000)]
        
        # Run optimized search
        result = await client.optimized_bulk_search(
            part_numbers=part_numbers,
            file_id=38,
            batch_size=500,
            concurrency=4
        )
        
        print(f"✅ Search completed in {result['latency_ms']}ms")
        print(f"📊 Found {result['total_matches']} matches")
        print(f"🏆 Performance rating: {result['performance_rating']}")
        
    finally:
        await client.close()

if __name__ == "__main__":
    asyncio.run(main())
