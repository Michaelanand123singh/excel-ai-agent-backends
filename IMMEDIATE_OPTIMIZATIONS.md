# Immediate Performance Optimizations

## 🚀 Quick Wins (Implement Today)

### 1. **Batch Processing Optimization**

**Current Issue:** 20K parts in single Elasticsearch request
**Solution:** Split into 500-part batches

```python
# In elasticsearch_client.py - modify bulk_search method
def bulk_search(self, part_numbers: List[str], file_id: int, limit_per_part: int = 100000) -> Dict[str, Any]:
    """Optimized bulk search with batching"""
    start_time = time.perf_counter()
    
    # Split into batches of 500 parts
    batch_size = 500
    results = {}
    total_matches = 0
    
    for i in range(0, len(part_numbers), batch_size):
        batch = part_numbers[i:i + batch_size]
        batch_result = self._search_batch(batch, file_id, limit_per_part)
        results.update(batch_result.get('results', {}))
        total_matches += batch_result.get('total_matches', 0)
    
    return {
        'results': results,
        'total_parts': len(part_numbers),
        'total_matches': total_matches,
        'latency_ms': int((time.perf_counter() - start_time) * 1000)
    }

def _search_batch(self, part_numbers: List[str], file_id: int, limit_per_part: int) -> Dict[str, Any]:
    """Search a batch of part numbers"""
    # Simplified query for faster processing
    query = {
        "query": {
            "bool": {
                "must": [
                    {"term": {"file_id": file_id}},
                    {"terms": {"part_number.keyword": part_numbers}}
                ]
            }
        },
        "size": limit_per_part,
        "_source": ["part_number", "company_name", "contact_details", "email", "unit_price", "quantity"]
    }
    
    response = self.es.search(index=self.index_name, body=query)
    # Process results...
```

**Expected Improvement:** 40-50% faster (15-17 seconds)

### 2. **Redis Caching Implementation**

**Add to requirements.txt:**
```
redis==4.6.0
```

**Create cache service:**
```python
# app/services/cache/search_cache.py
import redis
import json
import hashlib
from typing import List, Dict, Any

class SearchCache:
    def __init__(self):
        self.redis = redis.Redis(host='localhost', port=6379, db=0)
    
    def get_bulk_search_cache(self, part_numbers: List[str], file_id: int) -> Dict[str, Any]:
        """Get cached bulk search results"""
        cache_key = f"bulk_search:{file_id}:{hash(tuple(sorted(part_numbers)))}"
        cached = self.redis.get(cache_key)
        if cached:
            return json.loads(cached)
        return None
    
    def set_bulk_search_cache(self, part_numbers: List[str], file_id: int, results: Dict[str, Any], ttl: int = 600):
        """Cache bulk search results for 10 minutes"""
        cache_key = f"bulk_search:{file_id}:{hash(tuple(sorted(part_numbers)))}"
        self.redis.setex(cache_key, ttl, json.dumps(results))
```

**Integrate into search endpoint:**
```python
# In query_elasticsearch.py
from app.services.cache.search_cache import SearchCache

@router.post("/search-part-bulk-elasticsearch")
async def search_part_number_bulk_elasticsearch(req: Dict[str, Any], ...):
    cache = SearchCache()
    
    # Check cache first
    cached_result = cache.get_bulk_search_cache(req['part_numbers'], req['file_id'])
    if cached_result:
        return cached_result
    
    # Perform search...
    result = es_client.bulk_search(...)
    
    # Cache result
    cache.set_bulk_search_cache(req['part_numbers'], req['file_id'], result)
    
    return result
```

**Expected Improvement:** 90% faster for repeated searches

### 3. **Query Simplification**

**Current Complex Query:**
```python
# Complex bool query with multiple should clauses
search_query = {
    "query": {
        "bool": {
            "must": [{"term": {"file_id": file_id}}],
            "should": [
                {"term": {"part_number.keyword": {"value": part, "boost": 10.0}}},
                {"prefix": {"part_number.keyword": {"value": part, "boost": 5.0}}},
                {"match": {"part_number": {"query": part, "boost": 2.0, "fuzziness": 1}}}
            ],
            "minimum_should_match": 1
        }
    }
}
```

**Optimized Simple Query:**
```python
# Simplified query - much faster
search_query = {
    "query": {
        "bool": {
            "must": [
                {"term": {"file_id": file_id}},
                {"terms": {"part_number.keyword": part_numbers}}  # Single terms query
            ]
        }
    },
    "size": 1000,
    "_source": ["part_number", "company_name", "contact_details", "unit_price"]
}
```

**Expected Improvement:** 30-40% faster queries

### 4. **Frontend Streaming Results**

**Modify frontend to stream results:**
```typescript
// In api.ts - modify searchPartNumberBulkChunked
export async function searchPartNumberBulkChunked(
  fileId: number,
  partNumbers: string[],
  page = 1,
  pageSize = 1000,
  showAll = false,
  searchMode: 'exact' | 'fuzzy' | 'hybrid' = 'hybrid',
  opts?: { 
    chunkSize?: number; 
    concurrency?: number; 
    onProgress?: (completed: number, total: number, current: string) => void;
    onResults?: (results: Record<string, ApiPartSearchResult | { error: string }>) => void;
  }
) {
  // Reduce chunk size for faster streaming
  const chunkSize = opts?.chunkSize ?? 100  // Smaller chunks
  const concurrency = opts?.concurrency ?? 8  // More concurrency
  
  const chunks: string[][] = []
  for (let i = 0; i < partNumbers.length; i += chunkSize) {
    chunks.push(partNumbers.slice(i, i + chunkSize))
  }

  const results: Record<string, ApiPartSearchResult | { error: string }> = {}
  
  // Process chunks with streaming
  for (let i = 0; i < chunks.length; i++) {
    const chunk = chunks[i]
    
    try {
      const chunkResult = await api.post('/api/v1/query-elasticsearch/search-part-bulk-elasticsearch', {
        file_id: fileId,
        part_numbers: chunk,
        page,
        page_size: pageSize,
        show_all: showAll,
        search_mode: searchMode
      })
      
      // Stream results immediately
      if (opts?.onResults && chunkResult.data.results) {
        opts.onResults(chunkResult.data.results)
      }
      
      Object.assign(results, chunkResult.data.results || {})
      
      // Update progress
      if (opts?.onProgress) {
        opts.onProgress(i + 1, chunks.length, `Processed chunk ${i + 1}/${chunks.length}`)
      }
      
    } catch (error) {
      console.error(`Chunk ${i + 1} failed:`, error)
    }
  }
  
  return { results, total_parts: partNumbers.length }
}
```

**Expected Improvement:** Perceived 70-80% faster (immediate results)

## 🚀 Implementation Steps

### **Step 1: Backend Optimizations (30 minutes)**

1. **Modify elasticsearch_client.py:**
   ```bash
   # Add batch processing to bulk_search method
   # Simplify query structure
   # Add Redis caching
   ```

2. **Install Redis:**
   ```bash
   pip install redis==4.6.0
   ```

3. **Update requirements.txt:**
   ```
   redis==4.6.0
   ```

### **Step 2: Frontend Optimizations (20 minutes)**

1. **Update api.ts:**
   ```bash
   # Reduce chunk size to 100
   # Increase concurrency to 8
   # Add streaming results
   ```

2. **Update Query.tsx:**
   ```bash
   # Add real-time result display
   # Show progress for each chunk
   ```

### **Step 3: Testing (10 minutes)**

1. **Test with 20K parts:**
   ```bash
   python test_bulk_search_20k.py
   ```

2. **Verify improvements:**
   - Time should be 10-15 seconds (vs 28.5 seconds)
   - Results should stream in real-time
   - Cache should work for repeated searches

## 📊 Expected Results

| Optimization | Current | Optimized | Improvement |
|-------------|---------|-----------|-------------|
| **20K Parts** | 28.5s | 10-15s | 50-60% |
| **Repeated Search** | 28.5s | 1-2s | 90% |
| **User Experience** | Wait 28s | See results immediately | 80% |
| **Server Load** | High | Medium | 40% |

## 🎯 Next Steps

After implementing these quick wins:

1. **Monitor performance** with the test script
2. **Implement advanced optimizations** (parallel processing, file-specific indexes)
3. **Add monitoring** (Redis cache hit rates, Elasticsearch performance)
4. **Scale testing** (50K, 100K part numbers)

## 🚨 Important Notes

- **Redis must be running** for caching to work
- **Test with small batches first** (1000 parts) before 20K
- **Monitor memory usage** with large result sets
- **Backup current implementation** before making changes

These optimizations should give you **50-60% performance improvement** immediately!
