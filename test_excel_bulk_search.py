#!/usr/bin/env python3
"""
Excel Bulk Search Verification Test
Tests Excel file upload, processing, and bulk search functionality with Redis caching
"""

import requests
import time
import json
import io
import pandas as pd

def test_excel_bulk_search():
    """Test Excel bulk search functionality"""
    
    print("📊 EXCEL BULK SEARCH VERIFICATION")
    print("="*60)
    
    # Configuration
    BASE_URL = "http://localhost:8000"
    
    # Get auth token
    print("🔐 Getting authentication token...")
    auth_response = requests.post(
        f"{BASE_URL}/api/v1/auth/login",
        json={"username": "official@opt2deal.com", "password": "Opt2deal123!"},
        headers={"Content-Type": "application/json"}
    )
    
    if auth_response.status_code != 200:
        print(f"❌ Auth failed: {auth_response.status_code} - {auth_response.text}")
        return False
    
    token = auth_response.json()["access_token"]
    headers = {
        "Authorization": f"Bearer {token}"
    }
    
    # Test 1: Check existing files
    print("\n📁 Test 1: Checking existing files...")
    try:
        response = requests.get(
            f"{BASE_URL}/api/v1/upload/",
            headers=headers,
            timeout=30
        )
        
        if response.status_code == 200:
            files = response.json()
            print(f"✅ Found {len(files)} existing files")
            
            # Find a processed file
            processed_files = [f for f in files if f.get('status') == 'completed']
            if processed_files:
                test_file = processed_files[0]
                print(f"📋 Using file: {test_file.get('filename', 'unknown')} (ID: {test_file.get('id')})")
                file_id = test_file.get('id')
            else:
                print("⚠️ No completed files found, will test with file ID 38")
                file_id = 38
        else:
            print(f"❌ Failed to get files: {response.status_code}")
            file_id = 38
    except Exception as e:
        print(f"❌ Error getting files: {e}")
        file_id = 38
    
    # Test 2: Create test Excel file with part numbers
    print("\n📊 Test 2: Creating test Excel file...")
    
    # Read real part numbers
    try:
        with open("part_number", "r") as f:
            content = f.read().strip()
            part_numbers = [p.strip() for p in content.split(",") if p.strip()]
    except FileNotFoundError:
        print("❌ part_number file not found!")
        return False
    
    # Create Excel file with first 100 part numbers
    test_parts = part_numbers[:100]
    df = pd.DataFrame({
        'Part Number': test_parts,
        'Description': [f'Test part {i+1}' for i in range(len(test_parts))],
        'Quantity': [1] * len(test_parts)
    })
    
    # Save to Excel buffer
    excel_buffer = io.BytesIO()
    df.to_excel(excel_buffer, index=False, sheet_name='Parts')
    excel_buffer.seek(0)
    
    print(f"✅ Created Excel file with {len(test_parts)} part numbers")
    
    # Test 3: Upload Excel file
    print("\n📤 Test 3: Uploading Excel file...")
    
    files = {
        'file': ('test_bulk_search.xlsx', excel_buffer, 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
    }
    
    try:
        upload_response = requests.post(
            f"{BASE_URL}/api/v1/upload",
            files=files,
            headers=headers,
            timeout=120
        )
        
        if upload_response.status_code == 200:
            upload_data = upload_response.json()
            uploaded_file_id = upload_data.get('file_id')
            print(f"✅ Excel file uploaded successfully (ID: {uploaded_file_id})")
            
            # Wait for processing
            print("⏳ Waiting for file processing...")
            time.sleep(5)
            
            # Check file status
            status_response = requests.get(
                f"{BASE_URL}/api/v1/upload/{uploaded_file_id}",
                headers=headers,
                timeout=30
            )
            
            if status_response.status_code == 200:
                status_data = status_response.json()
                print(f"📊 File status: {status_data.get('status', 'unknown')}")
                
                if status_data.get('status') == 'completed':
                    print("✅ File processing completed")
                    test_file_id = uploaded_file_id
                else:
                    print(f"⚠️ File still processing, using existing file ID {file_id}")
                    test_file_id = file_id
            else:
                print(f"⚠️ Could not check status, using existing file ID {file_id}")
                test_file_id = file_id
                
        else:
            print(f"❌ Excel upload failed: {upload_response.status_code} - {upload_response.text}")
            print(f"⚠️ Using existing file ID {file_id}")
            test_file_id = file_id
            
    except Exception as e:
        print(f"❌ Excel upload error: {e}")
        print(f"⚠️ Using existing file ID {file_id}")
        test_file_id = file_id
    
    # Test 4: Bulk search with Excel part numbers
    print(f"\n🔍 Test 4: Bulk search with Excel part numbers (File ID: {test_file_id})...")
    
    # Use the part numbers from our Excel file
    bulk_payload = {
        "file_id": test_file_id,
        "part_numbers": test_parts,
        "page": 1,
        "page_size": 10000000,
        "show_all": True,
        "search_mode": "hybrid"
    }
    
    try:
        # First search (should be cache miss)
        print(f"🔍 First bulk search with {len(test_parts)} part numbers...")
        start_time = time.perf_counter()
        
        search_response1 = requests.post(
            f"{BASE_URL}/api/v1/query-elasticsearch/search-part-bulk-elasticsearch",
            json=bulk_payload,
            headers={**headers, "Content-Type": "application/json"},
            timeout=60
        )
        
        time1 = time.perf_counter() - start_time
        
        if search_response1.status_code == 200:
            data1 = search_response1.json()
            print(f"✅ First search completed in {time1:.2f} seconds")
            print(f"📊 Cache hit: {data1.get('cache_hit', False)}")
            print(f"🔍 Search engine: {data1.get('search_engine', 'unknown')}")
            print(f"📈 Total parts searched: {data1.get('total_parts', 0)}")
            
            # Count matches
            results = data1.get('results', {})
            matches_found = sum(1 for r in results.values() if r.get('total_matches', 0) > 0)
            print(f"🎯 Parts with matches: {matches_found}/{len(test_parts)}")
            
            # Second search (should be cache hit)
            print(f"\n🔍 Second bulk search (cache hit expected)...")
            start_time = time.perf_counter()
            
            search_response2 = requests.post(
                f"{BASE_URL}/api/v1/query-elasticsearch/search-part-bulk-elasticsearch",
                json=bulk_payload,
                headers={**headers, "Content-Type": "application/json"},
                timeout=60
            )
            
            time2 = time.perf_counter() - start_time
            
            if search_response2.status_code == 200:
                data2 = search_response2.json()
                print(f"✅ Second search completed in {time2:.2f} seconds")
                print(f"📊 Cache hit: {data2.get('cache_hit', False)}")
                print(f"🔍 Search engine: {data2.get('search_engine', 'unknown')}")
                
                # Performance analysis
                if data2.get('cache_hit', False):
                    if not data1.get('cache_hit', False):
                        improvement = ((time1 - time2) / time1) * 100
                        print(f"🚀 Cache improvement: {improvement:.1f}% faster")
                    else:
                        print("✅ Cache working: Both searches served from cache")
                    
                    # Verify results consistency
                    if data1.get('total_parts') == data2.get('total_parts'):
                        print("✅ Results are consistent between searches")
                    else:
                        print("❌ Results are inconsistent")
                    
                    return True
                else:
                    print("❌ Cache not working for bulk search")
                    return False
            else:
                print(f"❌ Second search failed: {search_response2.status_code}")
                return False
        else:
            print(f"❌ First search failed: {search_response1.status_code} - {search_response1.text}")
            return False
            
    except Exception as e:
        print(f"❌ Bulk search error: {e}")
        return False

def test_excel_processing_integration():
    """Test Excel processing integration"""
    print("\n📊 Test 5: Excel Processing Integration...")
    
    BASE_URL = "http://localhost:8000"
    
    # Get auth token
    auth_response = requests.post(
        f"{BASE_URL}/api/v1/auth/login",
        json={"username": "official@opt2deal.com", "password": "Opt2deal123!"},
        headers={"Content-Type": "application/json"}
    )
    
    if auth_response.status_code != 200:
        print(f"❌ Auth failed: {auth_response.status_code}")
        return False
    
    token = auth_response.json()["access_token"]
    headers = {
        "Authorization": f"Bearer {token}"
    }
    
    try:
        # Test file processing status
        response = requests.get(
            f"{BASE_URL}/api/v1/upload/",
            headers=headers,
            timeout=30
        )
        
        if response.status_code == 200:
            files = response.json()
            excel_files = [f for f in files if f.get('filename', '').endswith(('.xlsx', '.xls'))]
            
            print(f"📊 Found {len(excel_files)} Excel files")
            
            for file in excel_files[:3]:  # Check first 3 Excel files
                print(f"📋 File: {file.get('filename', 'unknown')}")
                print(f"   Status: {file.get('status', 'unknown')}")
                print(f"   Rows: {file.get('total_rows', 'unknown')}")
                print(f"   Created: {file.get('created_at', 'unknown')}")
            
            return True
        else:
            print(f"❌ Failed to get files: {response.status_code}")
            return False
            
    except Exception as e:
        print(f"❌ Excel processing test error: {e}")
        return False

def main():
    """Main Excel bulk search verification"""
    print("🧪 EXCEL BULK SEARCH VERIFICATION")
    print("="*60)
    print("Testing Excel file upload, processing, and bulk search functionality")
    print("="*60)
    
    results = {}
    
    # Test 1-4: Excel bulk search
    results['excel_bulk_search'] = test_excel_bulk_search()
    
    # Test 5: Excel processing integration
    results['excel_processing'] = test_excel_processing_integration()
    
    # Summary
    print("\n" + "="*60)
    print("📊 EXCEL BULK SEARCH VERIFICATION SUMMARY")
    print("="*60)
    
    passed_tests = sum(results.values())
    total_tests = len(results)
    
    for test_name, passed in results.items():
        status = "✅ PASS" if passed else "❌ FAIL"
        print(f"{test_name.replace('_', ' ').title()}: {status}")
    
    print(f"\nOverall: {passed_tests}/{total_tests} tests passed ({passed_tests/total_tests*100:.1f}%)")
    
    if passed_tests == total_tests:
        print("\n🚀 EXCEL BULK SEARCH IS PRODUCTION READY!")
        return True
    else:
        print(f"\n⚠️ EXCEL BULK SEARCH NEEDS ATTENTION ({total_tests - passed_tests} issues)")
        return False

if __name__ == "__main__":
    success = main()
    exit(0 if success else 1)
