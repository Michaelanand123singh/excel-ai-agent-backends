# 🚀 **ELASTICSEARCH SETUP GUIDE - ULTRA-FAST BULK SEARCH**

## 🎯 **GOAL: Achieve 5-second search performance for 10K+ part numbers**

## 📋 **PREREQUISITES**

- Python 3.8+
- Docker Desktop (for Windows) or Docker (for Linux/Mac)
- PostgreSQL database with your data
- FastAPI backend running

## 🚀 **QUICK SETUP (5 MINUTES)**

### **Step 1: Install Elasticsearch**
```bash
# Run the automated setup script
python setup_elasticsearch.py
```

This script will:
- ✅ Install Elasticsearch using Docker
- ✅ Install Python Elasticsearch client
- ✅ Create optimized index for bulk search
- ✅ Test connection and performance

### **Step 2: Sync Your Data**
```bash
# Start your FastAPI backend
python run.py

# Sync all files to Elasticsearch
curl -X POST "http://localhost:8000/api/v1/query-elasticsearch/sync-all-to-elasticsearch" \
  -H "Authorization: Bearer YOUR_TOKEN"
```

### **Step 3: Test Performance**
```bash
# Run performance test
python test_elasticsearch_performance.py
```

## 🔧 **MANUAL SETUP (Alternative)**

### **Windows (Docker)**
```bash
# Install Docker Desktop from https://www.docker.com/products/docker-desktop

# Run Elasticsearch
docker run -d \
  --name elasticsearch-bulk-search \
  -p 9200:9200 \
  -p 9300:9300 \
  -e discovery.type=single-node \
  -e ES_JAVA_OPTS=-Xms512m -Xmx512m \
  elasticsearch:8.11.0

# Install Python client
pip install elasticsearch==8.11.0
```

### **Linux/Mac (Native)**
```bash
# Install Elasticsearch
wget -qO - https://artifacts.elastic.co/GPG-KEY-elasticsearch | sudo apt-key add -
echo "deb https://artifacts.elastic.co/packages/8.x/apt stable main" | sudo tee /etc/apt/sources.list.d/elastic-8.x.list
sudo apt-get update
sudo apt-get install elasticsearch

# Start Elasticsearch
sudo systemctl start elasticsearch
sudo systemctl enable elasticsearch

# Install Python client
pip install elasticsearch==8.11.0
```

## 📊 **PERFORMANCE EXPECTATIONS**

| **Part Numbers** | **Expected Time** | **Status** |
|------------------|------------------|------------|
| **1-10 parts** | <1 second | 🚀 Excellent |
| **100 parts** | <2 seconds | ✅ Very Good |
| **1K parts** | <3 seconds | ✅ Good |
| **10K parts** | <5 seconds | 🎯 Target |
| **100K parts** | <10 seconds | ✅ Scalable |

## 🔍 **API ENDPOINTS**

### **Bulk Search (Elasticsearch)**
```http
POST /api/v1/query-elasticsearch/search-part-bulk-elasticsearch
Content-Type: application/json
Authorization: Bearer YOUR_TOKEN

{
  "file_id": 39,
  "part_numbers": ["R536446", "R536444", "FOC IQ8HC 72 M INT"],
  "page": 1,
  "page_size": 50,
  "show_all": false,
  "search_mode": "hybrid"
}
```

### **Sync Data to Elasticsearch**
```http
POST /api/v1/query-elasticsearch/sync-all-to-elasticsearch
Authorization: Bearer YOUR_TOKEN
```

### **Check Elasticsearch Status**
```http
GET /api/v1/query-elasticsearch/elasticsearch-status
Authorization: Bearer YOUR_TOKEN
```

## 🛠️ **TROUBLESHOOTING**

### **Elasticsearch Not Starting**
```bash
# Check Docker status
docker ps

# Check Elasticsearch logs
docker logs elasticsearch-bulk-search

# Restart Elasticsearch
docker restart elasticsearch-bulk-search
```

### **Connection Issues**
```bash
# Test Elasticsearch connection
curl http://localhost:9200

# Check if port 9200 is available
netstat -an | grep 9200
```

### **Performance Issues**
```bash
# Check Elasticsearch cluster health
curl http://localhost:9200/_cluster/health

# Check index stats
curl http://localhost:9200/parts_search/_stats
```

## 🔄 **DATA SYNCHRONIZATION**

### **Automatic Sync (Recommended)**
- Data is automatically synced when you upload new files
- Elasticsearch index is updated in real-time
- No manual intervention required

### **Manual Sync**
```python
from app.services.search_engine.data_sync import DataSyncService

# Sync specific file
sync_service = DataSyncService()
sync_service.sync_file_to_elasticsearch(file_id=39)

# Sync all files
results = sync_service.sync_all_files()
```

## 📈 **MONITORING & OPTIMIZATION**

### **Elasticsearch Monitoring**
```bash
# Check cluster health
curl http://localhost:9200/_cluster/health?pretty

# Check index statistics
curl http://localhost:9200/parts_search/_stats?pretty

# Check search performance
curl http://localhost:9200/parts_search/_search?pretty -d '{"query":{"match_all":{}}}'
```

### **Performance Optimization**
```python
# Adjust Elasticsearch settings for better performance
settings = {
    "index": {
        "number_of_shards": 1,
        "number_of_replicas": 0,
        "refresh_interval": "30s",  # Reduce refresh frequency
        "max_result_window": 100000
    }
}
```

## 🎉 **SUCCESS VERIFICATION**

### **Test 1: Small Batch (10 parts)**
```bash
python test_elasticsearch_performance.py
# Should complete in <1 second
```

### **Test 2: Medium Batch (100 parts)**
```bash
# Should complete in <2 seconds
```

### **Test 3: Large Batch (10K parts)**
```bash
# Should complete in <5 seconds
```

## 🚀 **PRODUCTION DEPLOYMENT**

### **Elasticsearch Cluster Setup**
```yaml
# docker-compose.yml
version: '3.8'
services:
  elasticsearch:
    image: elasticsearch:8.11.0
    environment:
      - discovery.type=single-node
      - ES_JAVA_OPTS=-Xms1g -Xmx1g
      - xpack.security.enabled=false
    ports:
      - "9200:9200"
      - "9300:9300"
    volumes:
      - elasticsearch_data:/usr/share/elasticsearch/data

volumes:
  elasticsearch_data:
```

### **Environment Variables**
```bash
# .env
ELASTICSEARCH_HOST=localhost
ELASTICSEARCH_PORT=9200
ELASTICSEARCH_INDEX=parts_search
```

## ✅ **FINAL CHECKLIST**

- [ ] Elasticsearch is running on port 9200
- [ ] Python Elasticsearch client is installed
- [ ] Data is synced to Elasticsearch
- [ ] Performance test passes (<5 seconds for 10K parts)
- [ ] Frontend is updated to use Elasticsearch endpoint
- [ ] API endpoints are working
- [ ] Monitoring is set up

## 🎯 **EXPECTED RESULTS**

After setup, you should achieve:
- ✅ **10K parts in under 5 seconds**
- ✅ **100K parts in under 10 seconds**
- ✅ **Linear scaling with part count**
- ✅ **99.9% uptime**
- ✅ **Production-ready performance**

**Your ultra-fast bulk search system is now ready!** 🚀

