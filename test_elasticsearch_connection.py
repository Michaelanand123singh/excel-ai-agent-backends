#!/usr/bin/env python3

import requests
import json

def test_elasticsearch():
    try:
        print("🔍 Testing Elasticsearch connection...")
        response = requests.get('http://localhost:9200', timeout=5)
        print('✅ Elasticsearch is running!')
        print(f'Status: {response.status_code}')
        
        data = response.json()
        print(f'Version: {data.get("version", {}).get("number", "unknown")}')
        print(f'Cluster: {data.get("cluster_name", "unknown")}')
        
        return True
    except Exception as e:
        print(f'❌ Connection failed: {e}')
        return False

if __name__ == "__main__":
    test_elasticsearch()

