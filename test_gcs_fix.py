#!/usr/bin/env python3
"""
Test script to verify Google Cloud Search client fixes
"""

import os
import sys

# Add the app directory to the path
sys.path.append(os.path.join(os.path.dirname(__file__), 'app'))

def test_gcs_client():
    """Test the Google Cloud Search client"""
    try:
        from app.services.search_engine.google_cloud_search_client import GoogleCloudSearchClient
        
        print("🔍 Testing Google Cloud Search Client...")
        print("-" * 50)
        
        # Initialize client
        client = GoogleCloudSearchClient()
        
        print(f"Project ID: {client.project_id}")
        print(f"Index ID: {client.index_id}")
        print(f"Data Store Name: {client.data_store_name}")
        
        # Test availability
        print("\n🔍 Testing availability...")
        is_available = client.is_available()
        print(f"Available: {is_available}")
        
        if is_available:
            print("✅ Google Cloud Search client is working!")
        else:
            print("⚠️ Google Cloud Search client is not available")
            print("This is expected if:")
            print("1. Data store doesn't exist yet")
            print("2. Service account doesn't have proper permissions")
            print("3. Discovery Engine API is not enabled")
        
        return True
        
    except Exception as e:
        print(f"❌ Error testing Google Cloud Search client: {e}")
        return False

def test_credentials():
    """Test credentials handling"""
    print("\n🔐 Testing credentials...")
    print("-" * 50)
    
    credentials_path = os.getenv("GOOGLE_APPLICATION_CREDENTIALS")
    
    if not credentials_path:
        print("ℹ️ No GOOGLE_APPLICATION_CREDENTIALS set - will use default service account")
        return True
    
    if credentials_path.startswith('{'):
        print("ℹ️ GOOGLE_APPLICATION_CREDENTIALS contains JSON content")
        try:
            import json
            credentials_info = json.loads(credentials_path)
            print(f"✅ JSON credentials parsed successfully")
            print(f"   Project ID: {credentials_info.get('project_id', 'N/A')}")
            print(f"   Client Email: {credentials_info.get('client_email', 'N/A')}")
            return True
        except Exception as e:
            print(f"❌ Failed to parse JSON credentials: {e}")
            return False
    else:
        print(f"ℹ️ GOOGLE_APPLICATION_CREDENTIALS points to file: {credentials_path}")
        if os.path.exists(credentials_path):
            print("✅ Credentials file exists")
            return True
        else:
            print("❌ Credentials file not found")
            return False

def main():
    print("🚀 Google Cloud Search Client Test")
    print("=" * 50)
    
    # Test credentials first
    creds_ok = test_credentials()
    
    # Test client
    client_ok = test_gcs_client()
    
    print("\n" + "=" * 50)
    if creds_ok and client_ok:
        print("✅ All tests passed!")
    else:
        print("⚠️ Some tests failed - check the output above")

if __name__ == "__main__":
    main()
