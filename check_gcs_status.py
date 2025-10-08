#!/usr/bin/env python3
"""
Script to check Google Cloud Search index status
"""

import os
import sys
from google.cloud import discoveryengine_v1beta as discoveryengine

def check_gcs_status():
    """Check Google Cloud Search index status"""
    
    # Get environment variables
    project_id = os.getenv("GOOGLE_CLOUD_PROJECT_ID")
    index_id = os.getenv("GOOGLE_CLOUD_SEARCH_INDEX_ID", "parts-search-index")
    
    if not project_id:
        print("❌ GOOGLE_CLOUD_PROJECT_ID not set")
        return
    
    print(f"🔍 Checking Google Cloud Search status...")
    print(f"Project ID: {project_id}")
    print(f"Index ID: {index_id}")
    print("-" * 50)
    
    try:
        # Initialize client
        client = discoveryengine.SearchServiceClient()
        
        # Check if data store exists
        data_store_name = f"projects/{project_id}/locations/global/dataStores/{index_id}"
        
        try:
            # Try to get data store info
            request = discoveryengine.GetDataStoreRequest(name=data_store_name)
            data_store = client.get_data_store(request=request)
            
            print(f"✅ Data Store Found: {data_store.display_name}")
            print(f"   Name: {data_store.name}")
            print(f"   State: {data_store.state}")
            print(f"   Created: {data_store.create_time}")
            print(f"   Updated: {data_store.update_time}")
            
            # Check documents count
            try:
                # List documents
                list_request = discoveryengine.ListDocumentsRequest(
                    parent=data_store_name,
                    page_size=10
                )
                response = client.list_documents(request=list_request)
                
                total_docs = 0
                file_ids = set()
                
                for doc in response.documents:
                    total_docs += 1
                    # Extract file_id from document name
                    doc_name = doc.name
                    if "/documents/" in doc_name:
                        file_id = doc_name.split("/documents/")[1].split("_")[0]
                        file_ids.add(file_id)
                
                print(f"📊 Documents Status:")
                print(f"   Total Documents: {total_docs}")
                print(f"   Files Indexed: {len(file_ids)}")
                print(f"   File IDs: {sorted(list(file_ids))}")
                
                if total_docs > 0:
                    print(f"\n✅ SUCCESS: {total_docs} documents indexed from {len(file_ids)} files")
                else:
                    print(f"\n⚠️  WARNING: No documents found in index")
                    
            except Exception as e:
                print(f"❌ Error listing documents: {e}")
                
        except Exception as e:
            print(f"❌ Data Store not found: {e}")
            print(f"   Expected name: {data_store_name}")
            print(f"   Make sure the data store exists and you have proper permissions")
            
    except Exception as e:
        print(f"❌ Error connecting to Google Cloud Search: {e}")
        print(f"   Check your credentials and project ID")

def test_search():
    """Test a simple search"""
    project_id = os.getenv("GOOGLE_CLOUD_PROJECT_ID")
    index_id = os.getenv("GOOGLE_CLOUD_SEARCH_INDEX_ID", "parts-search-index")
    
    if not project_id:
        print("❌ GOOGLE_CLOUD_PROJECT_ID not set")
        return
    
    try:
        client = discoveryengine.SearchServiceClient()
        
        # Test search
        request = discoveryengine.SearchRequest(
            serving_config=f"projects/{project_id}/locations/global/dataStores/{index_id}/servingConfigs/default_config",
            query="part_number:*",
            page_size=5
        )
        
        response = client.search(request=request)
        
        print(f"\n🔍 Test Search Results:")
        print(f"   Total Results: {len(response.results)}")
        
        for i, result in enumerate(response.results[:3]):
            struct_data = result.document.struct_data
            part_number = struct_data.get("part_number", "N/A")
            file_id = struct_data.get("file_id", "N/A")
            print(f"   {i+1}. Part: {part_number}, File ID: {file_id}")
            
    except Exception as e:
        print(f"❌ Search test failed: {e}")

if __name__ == "__main__":
    print("🚀 Google Cloud Search Status Checker")
    print("=" * 50)
    
    check_gcs_status()
    test_search()
    
    print("\n" + "=" * 50)
    print("✅ Check complete!")
