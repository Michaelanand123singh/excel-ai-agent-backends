"""
Ultra-Fast Cache Manager for Bulk Search Optimization
Leverages Redis for maximum performance with intelligent caching strategies
"""

import json
import time
import hashlib
import logging
from typing import Dict, Any, List, Optional, Union
import redis
from redis import Redis

from app.core.cache import get_redis_client
from app.core.config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()


class UltraFastCacheManager:
    """
    Advanced cache manager for ultra-fast bulk search operations
    Implements multi-tier caching with intelligent invalidation
    """
    
    def __init__(self):
        self.redis_client = get_redis_client()
        self.cache_prefix = "ultra_fast"
        self.default_ttl = 3600  # 1 hour
        self.column_cache_ttl = 7200  # 2 hours
        self.result_cache_ttl = 1800  # 30 minutes
        
    def get_cache_key(self, operation: str, **kwargs) -> str:
        """Generate consistent cache keys"""
        # Sort kwargs for consistent key generation
        sorted_kwargs = sorted(kwargs.items())
        key_data = f"{operation}:{':'.join(f'{k}={v}' for k, v in sorted_kwargs)}"
        key_hash = hashlib.md5(key_data.encode()).hexdigest()
        return f"{self.cache_prefix}:{operation}:{key_hash}"
    
    def cache_column_mappings(self, table_name: str, mappings: Dict[str, str]) -> bool:
        """Cache column mappings for a table"""
        try:
            cache_key = self.get_cache_key("column_mappings", table=table_name)
            self.redis_client.setex(
                cache_key, 
                self.column_cache_ttl, 
                json.dumps(mappings)
            )
            logger.info(f"Cached column mappings for {table_name}")
            return True
        except Exception as e:
            logger.error(f"Failed to cache column mappings: {e}")
            return False
    
    def get_cached_column_mappings(self, table_name: str) -> Optional[Dict[str, str]]:
        """Retrieve cached column mappings"""
        try:
            cache_key = self.get_cache_key("column_mappings", table=table_name)
            cached_data = self.redis_client.get(cache_key)
            if cached_data:
                return json.loads(cached_data)
            return None
        except Exception as e:
            logger.error(f"Failed to get cached column mappings: {e}")
            return None
    
    def cache_bulk_search_result(self, 
                                file_id: int, 
                                part_numbers: List[str], 
                                search_mode: str,
                                result: Dict[str, Any]) -> bool:
        """Cache bulk search results"""
        try:
            # Create a hash of the part numbers for the cache key
            part_numbers_hash = hashlib.md5(
                json.dumps(sorted(part_numbers)).encode()
            ).hexdigest()
            
            cache_key = self.get_cache_key(
                "bulk_search_result",
                file_id=file_id,
                parts_hash=part_numbers_hash,
                search_mode=search_mode
            )
            
            # Compress large results
            if len(json.dumps(result)) > 1024 * 1024:  # 1MB
                result["compressed"] = True
                # Store only essential data for large results
                compressed_result = {
                    "total_parts": result.get("total_parts", 0),
                    "latency_ms": result.get("latency_ms", 0),
                    "summary": {
                        "found_matches": sum(1 for r in result.get("results", {}).values() 
                                           if r.get("total_matches", 0) > 0),
                        "no_matches": sum(1 for r in result.get("results", {}).values() 
                                        if r.get("total_matches", 0) == 0)
                    },
                    "compressed": True
                }
                self.redis_client.setex(
                    cache_key, 
                    self.result_cache_ttl, 
                    json.dumps(compressed_result)
                )
            else:
                self.redis_client.setex(
                    cache_key, 
                    self.result_cache_ttl, 
                    json.dumps(result)
                )
            
            logger.info(f"Cached bulk search result for {len(part_numbers)} parts")
            return True
            
        except Exception as e:
            logger.error(f"Failed to cache bulk search result: {e}")
            return False
    
    def get_cached_bulk_search_result(self, 
                                     file_id: int, 
                                     part_numbers: List[str], 
                                     search_mode: str) -> Optional[Dict[str, Any]]:
        """Retrieve cached bulk search results"""
        try:
            part_numbers_hash = hashlib.md5(
                json.dumps(sorted(part_numbers)).encode()
            ).hexdigest()
            
            cache_key = self.get_cache_key(
                "bulk_search_result",
                file_id=file_id,
                parts_hash=part_numbers_hash,
                search_mode=search_mode
            )
            
            cached_data = self.redis_client.get(cache_key)
            if cached_data:
                result = json.loads(cached_data)
                result["cached"] = True
                return result
            return None
            
        except Exception as e:
            logger.error(f"Failed to get cached bulk search result: {e}")
            return None
    
    def cache_single_search_result(self, 
                                  file_id: int, 
                                  part_number: str, 
                                  search_mode: str,
                                  result: Dict[str, Any]) -> bool:
        """Cache single search results"""
        try:
            cache_key = self.get_cache_key(
                "single_search_result",
                file_id=file_id,
                part_number=part_number,
                search_mode=search_mode
            )
            
            self.redis_client.setex(
                cache_key, 
                self.result_cache_ttl, 
                json.dumps(result)
            )
            return True
            
        except Exception as e:
            logger.error(f"Failed to cache single search result: {e}")
            return False
    
    def get_cached_single_search_result(self, 
                                       file_id: int, 
                                       part_number: str, 
                                       search_mode: str) -> Optional[Dict[str, Any]]:
        """Retrieve cached single search results"""
        try:
            cache_key = self.get_cache_key(
                "single_search_result",
                file_id=file_id,
                part_number=part_number,
                search_mode=search_mode
            )
            
            cached_data = self.redis_client.get(cache_key)
            if cached_data:
                result = json.loads(cached_data)
                result["cached"] = True
                return result
            return None
            
        except Exception as e:
            logger.error(f"Failed to get cached single search result: {e}")
            return None
    
    def cache_table_metadata(self, table_name: str, metadata: Dict[str, Any]) -> bool:
        """Cache table metadata"""
        try:
            cache_key = self.get_cache_key("table_metadata", table=table_name)
            self.redis_client.setex(
                cache_key, 
                self.column_cache_ttl, 
                json.dumps(metadata)
            )
            return True
        except Exception as e:
            logger.error(f"Failed to cache table metadata: {e}")
            return False
    
    def get_cached_table_metadata(self, table_name: str) -> Optional[Dict[str, Any]]:
        """Retrieve cached table metadata"""
        try:
            cache_key = self.get_cache_key("table_metadata", table=table_name)
            cached_data = self.redis_client.get(cache_key)
            if cached_data:
                return json.loads(cached_data)
            return None
        except Exception as e:
            logger.error(f"Failed to get cached table metadata: {e}")
            return None
    
    def invalidate_table_cache(self, table_name: str) -> bool:
        """Invalidate all cache entries for a table"""
        try:
            # Get all keys for this table
            pattern = f"{self.cache_prefix}:*:{table_name}*"
            keys = self.redis_client.keys(pattern)
            
            if keys:
                self.redis_client.delete(*keys)
                logger.info(f"Invalidated {len(keys)} cache entries for {table_name}")
            
            return True
        except Exception as e:
            logger.error(f"Failed to invalidate table cache: {e}")
            return False
    
    def get_cache_stats(self) -> Dict[str, Any]:
        """Get cache performance statistics"""
        try:
            info = self.redis_client.info()
            
            # Get cache hit rate
            hits = info.get("keyspace_hits", 0)
            misses = info.get("keyspace_misses", 0)
            total_requests = hits + misses
            hit_rate = hits / total_requests if total_requests > 0 else 0
            
            # Get memory usage
            used_memory = info.get("used_memory", 0)
            used_memory_human = info.get("used_memory_human", "0B")
            
            # Get key count
            key_count = self.redis_client.dbsize()
            
            return {
                "hit_rate": round(hit_rate * 100, 2),
                "total_requests": total_requests,
                "cache_hits": hits,
                "cache_misses": misses,
                "key_count": key_count,
                "memory_used": used_memory,
                "memory_used_human": used_memory_human,
                "status": "healthy" if hit_rate > 0.8 else "degraded"
            }
            
        except Exception as e:
            logger.error(f"Failed to get cache stats: {e}")
            return {"error": str(e), "status": "error"}
    
    def warm_up_cache(self, table_name: str, common_part_numbers: List[str]) -> bool:
        """Warm up cache with common searches"""
        try:
            logger.info(f"Warming up cache for {table_name} with {len(common_part_numbers)} common parts")
            
            # This would typically involve pre-loading common search results
            # For now, we'll just log the operation
            for part_number in common_part_numbers[:100]:  # Limit to 100 for warming
                cache_key = self.get_cache_key(
                    "warm_up",
                    table=table_name,
                    part_number=part_number
                )
                self.redis_client.setex(cache_key, 300, "warmed")  # 5 minute TTL
            
            return True
        except Exception as e:
            logger.error(f"Failed to warm up cache: {e}")
            return False
    
    def clear_all_cache(self) -> bool:
        """Clear all cache entries"""
        try:
            self.redis_client.flushdb()
            logger.info("Cleared all cache entries")
            return True
        except Exception as e:
            logger.error(f"Failed to clear cache: {e}")
            return False
    
    def get_cache_size(self) -> Dict[str, Any]:
        """Get cache size information"""
        try:
            info = self.redis_client.info()
            return {
                "total_keys": self.redis_client.dbsize(),
                "memory_used": info.get("used_memory", 0),
                "memory_used_human": info.get("used_memory_human", "0B"),
                "max_memory": info.get("maxmemory", 0),
                "max_memory_human": info.get("maxmemory_human", "0B"),
                "eviction_policy": info.get("maxmemory_policy", "noeviction")
            }
        except Exception as e:
            logger.error(f"Failed to get cache size: {e}")
            return {"error": str(e)}


# Global cache manager instance
ultra_fast_cache = UltraFastCacheManager()

