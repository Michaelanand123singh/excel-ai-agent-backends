#!/usr/bin/env python3
"""
Test script to verify search engine fixes
"""

import os
import sys

# Add the app directory to the path
sys.path.append(os.path.join(os.path.dirname(__file__), 'app'))

def test_unified_search_engine():
    """Test the unified search engine initialization"""
    try:
        from app.services.search_engine.unified_search_engine import UnifiedSearchEngine
        from app.core.database import SessionLocal
        
        print("🔍 Testing Unified Search Engine...")
        print("-" * 50)
        
        # Create a mock database session
        session = SessionLocal()
        
        try:
            # Initialize search engine
            search_engine = UnifiedSearchEngine(session, "test_table", file_id=1)
            
            print(f"GCS Available: {search_engine.gcs_available}")
            print(f"ES Available: {search_engine.es_available}")
            print(f"GCS Client: {search_engine.gcs_client is not None}")
            print(f"ES Client: {search_engine.es_client is not None}")
            
            if not search_engine.gcs_available and not search_engine.es_available:
                print("⚠️ Neither GCS nor ES available - will use PostgreSQL fallback")
            else:
                print("✅ At least one search engine is available")
            
            return True
            
        finally:
            session.close()
        
    except Exception as e:
        print(f"❌ Error testing unified search engine: {e}")
        return False

def test_google_cloud_search_client():
    """Test the Google Cloud Search client initialization"""
    try:
        from app.services.search_engine.google_cloud_search_client import GoogleCloudSearchClient
        
        print("\n🔍 Testing Google Cloud Search Client...")
        print("-" * 50)
        
        # Initialize client
        client = GoogleCloudSearchClient()
        
        print(f"Project ID: {client.project_id}")
        print(f"Index ID: {client.index_id}")
        print(f"Client Initialized: {client.client is not None}")
        
        # Test availability
        is_available = client.is_available()
        print(f"Available: {is_available}")
        
        if not is_available:
            print("ℹ️ Google Cloud Search not available - this is expected if:")
            print("  1. GOOGLE_CLOUD_PROJECT_ID is not set")
            print("  2. Service account doesn't have proper permissions")
            print("  3. Discovery Engine API is not enabled")
            print("  4. Data store doesn't exist yet")
        
        return True
        
    except Exception as e:
        print(f"❌ Error testing Google Cloud Search client: {e}")
        return False

def main():
    print("🚀 Search Engine Fix Test")
    print("=" * 50)
    
    # Test Google Cloud Search client
    gcs_ok = test_google_cloud_search_client()
    
    # Test unified search engine
    unified_ok = test_unified_search_engine()
    
    print("\n" + "=" * 50)
    if gcs_ok and unified_ok:
        print("✅ All tests passed!")
        print("🎯 Search engines should now work without 500 errors")
    else:
        print("⚠️ Some tests failed - check the output above")

if __name__ == "__main__":
    main()
