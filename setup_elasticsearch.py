#!/usr/bin/env python3
"""
Elasticsearch setup script for ultra-fast bulk search
"""

import subprocess
import sys
import os
import time
import requests
from pathlib import Path

def install_elasticsearch():
    """Install Elasticsearch"""
    print("🚀 Setting up Elasticsearch for ultra-fast bulk search...")
    print("=" * 60)
    
    # Check if Elasticsearch is already running
    try:
        response = requests.get("http://localhost:9200", timeout=5)
        if response.status_code == 200:
            print("✅ Elasticsearch is already running!")
            return True
    except:
        pass
    
    print("📦 Installing Elasticsearch...")
    
    # For Windows, we'll use Docker
    if os.name == 'nt':  # Windows
        print("🪟 Windows detected - using Docker for Elasticsearch")
        
        # Check if Docker is available
        try:
            subprocess.run(["docker", "--version"], check=True, capture_output=True)
            print("✅ Docker is available")
        except:
            print("❌ Docker is not available. Please install Docker Desktop first.")
            print("   Download from: https://www.docker.com/products/docker-desktop")
            return False
        
        # Run Elasticsearch in Docker
        print("🐳 Starting Elasticsearch in Docker...")
        try:
            subprocess.run([
                "docker", "run", "-d",
                "--name", "elasticsearch-bulk-search",
                "-p", "9200:9200",
                "-p", "9300:9300",
                "-e", "discovery.type=single-node",
                "-e", "ES_JAVA_OPTS=-Xms512m -Xmx512m",
                "elasticsearch:8.11.0"
            ], check=True)
            
            print("⏳ Waiting for Elasticsearch to start...")
            time.sleep(30)
            
            # Test connection
            try:
                response = requests.get("http://localhost:9200", timeout=10)
                if response.status_code == 200:
                    print("✅ Elasticsearch is running!")
                    return True
                else:
                    print("❌ Elasticsearch failed to start properly")
                    return False
            except:
                print("❌ Elasticsearch is not responding")
                return False
                
        except subprocess.CalledProcessError as e:
            print(f"❌ Failed to start Elasticsearch: {e}")
            return False
    
    else:  # Linux/Mac
        print("🐧 Linux/Mac detected - installing Elasticsearch")
        
        # Install Elasticsearch
        try:
            # For Ubuntu/Debian
            subprocess.run([
                "wget", "-qO", "-", "https://artifacts.elastic.co/GPG-KEY-elasticsearch"
            ], check=True)
            
            subprocess.run([
                "sudo", "apt-get", "install", "elasticsearch"
            ], check=True)
            
            # Start Elasticsearch
            subprocess.run([
                "sudo", "systemctl", "start", "elasticsearch"
            ], check=True)
            
            subprocess.run([
                "sudo", "systemctl", "enable", "elasticsearch"
            ], check=True)
            
            print("✅ Elasticsearch installed and started!")
            return True
            
        except subprocess.CalledProcessError as e:
            print(f"❌ Failed to install Elasticsearch: {e}")
            return False

def install_python_dependencies():
    """Install Python dependencies for Elasticsearch"""
    print("\n📦 Installing Python dependencies...")
    
    try:
        subprocess.run([
            sys.executable, "-m", "pip", "install", "elasticsearch"
        ], check=True)
        print("✅ Elasticsearch Python client installed!")
        return True
    except subprocess.CalledProcessError as e:
        print(f"❌ Failed to install Python dependencies: {e}")
        return False

def test_elasticsearch_connection():
    """Test Elasticsearch connection"""
    print("\n🔍 Testing Elasticsearch connection...")
    
    try:
        from elasticsearch import Elasticsearch
        
        es = Elasticsearch([{"host": "localhost", "port": 9200, "scheme": "http"}])
        
        if es.ping():
            print("✅ Elasticsearch connection successful!")
            
            # Get cluster info
            info = es.info()
            print(f"📊 Cluster: {info['cluster_name']}")
            print(f"📊 Version: {info['version']['number']}")
            
            return True
        else:
            print("❌ Elasticsearch connection failed")
            return False
            
    except Exception as e:
        print(f"❌ Elasticsearch test failed: {e}")
        return False

def setup_elasticsearch_index():
    """Setup Elasticsearch index for bulk search"""
    print("\n🏗️ Setting up Elasticsearch index...")
    
    try:
        from elasticsearch import Elasticsearch
        
        es = Elasticsearch([{"host": "localhost", "port": 9200, "scheme": "http"}])
        
        # Create index
        index_name = "parts_search"
        
        if es.indices.exists(index=index_name):
            print(f"✅ Index {index_name} already exists")
            return True
        
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
            },
            "settings": {
                "number_of_shards": 1,
                "number_of_replicas": 0,
                "index": {
                    "max_result_window": 100000
                }
            }
        }
        
        es.indices.create(index=index_name, body=mapping)
        print(f"✅ Created Elasticsearch index: {index_name}")
        return True
        
    except Exception as e:
        print(f"❌ Failed to setup Elasticsearch index: {e}")
        return False

def main():
    """Main setup function"""
    print("🚀 ELASTICSEARCH SETUP FOR ULTRA-FAST BULK SEARCH")
    print("=" * 60)
    print("This will set up Elasticsearch to achieve 5-second search performance")
    print("for 10K+ part numbers.")
    print()
    
    # Step 1: Install Elasticsearch
    if not install_elasticsearch():
        print("\n❌ Elasticsearch setup failed!")
        return False
    
    # Step 2: Install Python dependencies
    if not install_python_dependencies():
        print("\n❌ Python dependencies installation failed!")
        return False
    
    # Step 3: Test connection
    if not test_elasticsearch_connection():
        print("\n❌ Elasticsearch connection test failed!")
        return False
    
    # Step 4: Setup index
    if not setup_elasticsearch_index():
        print("\n❌ Elasticsearch index setup failed!")
        return False
    
    print("\n🎉 ELASTICSEARCH SETUP COMPLETED SUCCESSFULLY!")
    print("=" * 60)
    print("✅ Elasticsearch is running on http://localhost:9200")
    print("✅ Python client is installed")
    print("✅ Index is created and ready")
    print()
    print("🚀 NEXT STEPS:")
    print("1. Start your FastAPI backend")
    print("2. Sync your data to Elasticsearch using:")
    print("   POST /api/v1/query-elasticsearch/sync-all-to-elasticsearch")
    print("3. Test bulk search with:")
    print("   POST /api/v1/query-elasticsearch/search-part-bulk-elasticsearch")
    print()
    print("🎯 EXPECTED PERFORMANCE:")
    print("• 1-10 parts: <1 second")
    print("• 100 parts: <2 seconds")
    print("• 1K parts: <3 seconds")
    print("• 10K parts: <5 seconds")
    print()
    
    return True

if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
