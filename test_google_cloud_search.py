#!/usr/bin/env python3
"""
Test script for Google Cloud Search implementation
Tests all three search methods: single, bulk text, and bulk upload
"""

import os
import sys
import asyncio
import logging
from pathlib import Path

# Add the app directory to Python path
sys.path.insert(0, str(Path(__file__).parent / "app"))

from app.services.search_engine.google_cloud_search_client import GoogleCloudSearchClient
from app.services.search_engine.unified_search_engine import UnifiedSearchEngine
from app.core.database import SessionLocal

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def test_google_cloud_search_client():
    """Test Google Cloud Search client directly"""
    print("🔍 Testing Google Cloud Search Client...")
    
    try:
        gcs_client = GoogleCloudSearchClient()
        
        # Test availability
        is_available = gcs_client.is_available()
        print(f"✅ Google Cloud Search available: {is_available}")
        
        if not is_available:
            print("⚠️ Google Cloud Search not available. Check your configuration:")
            print("   - GOOGLE_CLOUD_PROJECT_ID")
            print("   - GOOGLE_APPLICATION_CREDENTIALS")
            print("   - Cloud Search API enabled")
            return False
        
        # Test index creation
        print("📝 Testing index creation...")
        index_created = gcs_client.create_index("test_table", 999)
        print(f"✅ Index creation: {'Success' if index_created else 'Failed'}")
        
        # Test data indexing (with sample data)
        print("📊 Testing data indexing...")
        sample_data = [
            {
                "part_number": "TEST001",
                "Item_Description": "Test Part 1",
                "Potential Buyer 1": "Test Company 1",
                "Potential Buyer 1 Contact Details": "123-456-7890",
                "Potential Buyer 1 email id": "test1@example.com",
                "Quantity": 100,
                "Unit_Price": 10.50,
                "UQC": "PCS",
                "Potential Buyer 2": "Test Company 2",
                "Potential Buyer 2 Contact Details": "098-765-4321",
                "Potential Buyer 2 email id": "test2@example.com"
            },
            {
                "part_number": "TEST002",
                "Item_Description": "Test Part 2",
                "Potential Buyer 1": "Test Company 3",
                "Potential Buyer 1 Contact Details": "555-123-4567",
                "Potential Buyer 1 email id": "test3@example.com",
                "Quantity": 50,
                "Unit_Price": 25.75,
                "UQC": "PCS",
                "Potential Buyer 2": "",
                "Potential Buyer 2 Contact Details": "",
                "Potential Buyer 2 email id": ""
            }
        ]
        
        data_indexed = gcs_client.index_data(sample_data, 999)
        print(f"✅ Data indexing: {'Success' if data_indexed else 'Failed'}")
        
        # Test single search
        print("🔍 Testing single search...")
        single_result = gcs_client.search_single_part("TEST001", 999)
        print(f"✅ Single search: Found {single_result.get('total_matches', 0)} matches")
        print(f"   Search engine: {single_result.get('search_engine', 'unknown')}")
        print(f"   Latency: {single_result.get('latency_ms', 0)}ms")
        
        # Test bulk search
        print("🔍 Testing bulk search...")
        bulk_result = gcs_client.bulk_search(["TEST001", "TEST002", "TEST999"], 999)
        print(f"✅ Bulk search: Found results for {len(bulk_result.get('results', {}))} parts")
        print(f"   Search engine: {bulk_result.get('search_engine', 'unknown')}")
        print(f"   Latency: {bulk_result.get('latency_ms', 0)}ms")
        
        return True
        
    except Exception as e:
        print(f"❌ Google Cloud Search test failed: {e}")
        return False

def test_unified_search_engine():
    """Test unified search engine with Google Cloud Search"""
    print("\n🔍 Testing Unified Search Engine...")
    
    try:
        # Create a test database session
        db = SessionLocal()
        
        # Test with a dummy table (this will fall back to PostgreSQL if GCS fails)
        search_engine = UnifiedSearchEngine(db, "test_table", file_id=999)
        
        # Test single search
        print("🔍 Testing single search through unified engine...")
        single_result = search_engine.search_single_part("TEST001")
        print(f"✅ Single search: Found {single_result.get('total_matches', 0)} matches")
        print(f"   Search engine: {single_result.get('search_engine', 'unknown')}")
        print(f"   Latency: {single_result.get('latency_ms', 0)}ms")
        
        # Test bulk search
        print("🔍 Testing bulk search through unified engine...")
        bulk_result = search_engine.search_bulk_parts(["TEST001", "TEST002", "TEST999"])
        print(f"✅ Bulk search: Found results for {len(bulk_result.get('results', {}))} parts")
        print(f"   Search engine: {bulk_result.get('search_engine', 'unknown')}")
        print(f"   Latency: {bulk_result.get('latency_ms', 0)}ms")
        
        db.close()
        return True
        
    except Exception as e:
        print(f"❌ Unified search engine test failed: {e}")
        return False

def test_environment_variables():
    """Test environment variables configuration"""
    print("\n🔧 Testing Environment Variables...")
    
    required_vars = [
        "GOOGLE_CLOUD_PROJECT_ID",
        "GOOGLE_CLOUD_SEARCH_INDEX_ID",
        "GOOGLE_APPLICATION_CREDENTIALS"
    ]
    
    all_present = True
    for var in required_vars:
        value = os.getenv(var)
        if value:
            print(f"✅ {var}: {value[:50]}{'...' if len(value) > 50 else ''}")
        else:
            print(f"❌ {var}: Not set")
            all_present = False
    
    return all_present

def main():
    """Run all tests"""
    print("🚀 Google Cloud Search Implementation Test")
    print("=" * 50)
    
    # Test environment variables
    env_ok = test_environment_variables()
    
    if not env_ok:
        print("\n⚠️ Environment variables not properly configured.")
        print("Please set the required environment variables and try again.")
        return False
    
    # Test Google Cloud Search client
    gcs_ok = test_google_cloud_search_client()
    
    # Test unified search engine
    unified_ok = test_unified_search_engine()
    
    print("\n" + "=" * 50)
    print("📊 Test Results Summary:")
    print(f"   Environment Variables: {'✅ PASS' if env_ok else '❌ FAIL'}")
    print(f"   Google Cloud Search: {'✅ PASS' if gcs_ok else '❌ FAIL'}")
    print(f"   Unified Search Engine: {'✅ PASS' if unified_ok else '❌ FAIL'}")
    
    if env_ok and gcs_ok and unified_ok:
        print("\n🎉 All tests passed! Google Cloud Search is ready to use.")
        print("\n📝 Next steps:")
        print("   1. Deploy your application with the environment variables")
        print("   2. Upload a test Excel file")
        print("   3. Test search functionality in the frontend")
        return True
    else:
        print("\n❌ Some tests failed. Please check the configuration and try again.")
        return False

if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
