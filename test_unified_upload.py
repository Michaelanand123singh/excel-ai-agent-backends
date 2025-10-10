#!/usr/bin/env python3
"""
Unified Upload System Test
Tests the unified upload system with both small and large files
"""

import requests
import time
import io
import pandas as pd

def test_unified_upload_small():
    """Test unified upload with small file"""
    
    print("🧪 TESTING UNIFIED UPLOAD - SMALL FILE")
    print("="*50)
    
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
    
    # Create small Excel file (5MB)
    print("📊 Creating small Excel file...")
    
    test_data = []
    for i in range(5000):  # 5K rows should be around 5MB
        test_data.append({
            'Part Number': f'SMALL{i:04d}',
            'Description': f'Small test part {i}',
            'Quantity': i % 5 + 1,
            'Manufacturer': f'Manufacturer {i % 3}'
        })
    
    df = pd.DataFrame(test_data)
    excel_buffer = io.BytesIO()
    df.to_excel(excel_buffer, index=False, sheet_name='Parts')
    excel_buffer.seek(0)
    
    file_size = len(excel_buffer.getvalue())
    print(f"✅ Created small Excel file: {file_size / (1024*1024):.1f}MB")
    
    # Test unified upload
    files = {
        'file': ('test_small_unified.xlsx', excel_buffer, 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
    }
    
    try:
        print("📤 Testing unified upload...")
        start_time = time.perf_counter()
        
        response = requests.post(
            f"{BASE_URL}/api/v1/upload",
            files=files,
            headers=headers,
            timeout=60
        )
        
        upload_time = time.perf_counter() - start_time
        
        if response.status_code == 200:
            data = response.json()
            print(f"✅ Small file upload successful in {upload_time:.2f}s!")
            print(f"📊 File ID: {data.get('id')}")
            print(f"📈 Status: {data.get('status')}")
            print(f"📏 Size: {data.get('size_bytes', 0) / (1024*1024):.1f}MB")
            
            # Check if it requires chunked upload (should not for small files)
            if data.get('requires_chunked_upload'):
                print("❌ Small file incorrectly requires chunked upload")
                return False
            else:
                print("✅ Small file processed directly (correct)")
                return True
        else:
            print(f"❌ Small file upload failed: {response.status_code} - {response.text}")
            return False
            
    except Exception as e:
        print(f"❌ Small file upload error: {e}")
        return False

def test_unified_upload_large():
    """Test unified upload with large file"""
    
    print("\n🧪 TESTING UNIFIED UPLOAD - LARGE FILE")
    print("="*50)
    
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
    
    # Create large Excel file (25MB)
    print("📊 Creating large Excel file...")
    
    test_data = []
    for i in range(25000):  # 25K rows should be around 25MB
        test_data.append({
            'Part Number': f'LARGE{i:05d}',
            'Description': f'Large test part {i} with longer description to increase file size',
            'Quantity': i % 10 + 1,
            'Manufacturer': f'Manufacturer {i % 5}',
            'Category': f'Category {i % 20}',
            'Price': f'${i % 1000}.{i % 100:02d}'
        })
    
    df = pd.DataFrame(test_data)
    excel_buffer = io.BytesIO()
    df.to_excel(excel_buffer, index=False, sheet_name='Parts')
    excel_buffer.seek(0)
    
    file_size = len(excel_buffer.getvalue())
    print(f"✅ Created large Excel file: {file_size / (1024*1024):.1f}MB")
    
    # Test unified upload
    files = {
        'file': ('test_large_unified.xlsx', excel_buffer, 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
    }
    
    try:
        print("📤 Testing unified upload...")
        start_time = time.perf_counter()
        
        response = requests.post(
            f"{BASE_URL}/api/v1/upload",
            files=files,
            headers=headers,
            timeout=60
        )
        
        upload_time = time.perf_counter() - start_time
        
        if response.status_code == 200:
            data = response.json()
            print(f"✅ Large file upload response in {upload_time:.2f}s!")
            
            # Check if it requires chunked upload (should for large files)
            if data.get('requires_chunked_upload'):
                print("✅ Large file correctly requires chunked upload")
                print(f"📋 Message: {data.get('message')}")
                print(f"📏 Max chunk size: {data.get('max_chunk_size', 0) / (1024*1024):.1f}MB")
                return True
            else:
                print("❌ Large file should require chunked upload but doesn't")
                return False
        else:
            print(f"❌ Large file upload failed: {response.status_code} - {response.text}")
            return False
            
    except Exception as e:
        print(f"❌ Large file upload error: {e}")
        return False

def test_chunked_upload_flow():
    """Test the complete chunked upload flow"""
    
    print("\n🧪 TESTING CHUNKED UPLOAD FLOW")
    print("="*50)
    
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
    
    # Create medium Excel file (30MB)
    print("📊 Creating medium Excel file...")
    
    test_data = []
    for i in range(30000):  # 30K rows should be around 30MB
        test_data.append({
            'Part Number': f'CHUNK{i:05d}',
            'Description': f'Chunked test part {i} with longer description',
            'Quantity': i % 8 + 1,
            'Manufacturer': f'Manufacturer {i % 4}',
            'Category': f'Category {i % 15}'
        })
    
    df = pd.DataFrame(test_data)
    excel_buffer = io.BytesIO()
    df.to_excel(excel_buffer, index=False, sheet_name='Parts')
    excel_buffer.seek(0)
    
    file_size = len(excel_buffer.getvalue())
    print(f"✅ Created medium Excel file: {file_size / (1024*1024):.1f}MB")
    
    # Test chunked upload flow
    try:
        # Step 1: Init
        print("📤 Step 1: Initializing chunked upload...")
        init_response = requests.post(
            f"{BASE_URL}/api/v1/upload/multipart/init",
            json={
                "filename": "test_chunked_flow.xlsx",
                "content_type": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                "total_size": file_size
            },
            headers=headers,
            timeout=30
        )
        
        if init_response.status_code != 200:
            print(f"❌ Init failed: {init_response.status_code} - {init_response.text}")
            return False
        
        init_data = init_response.json()
        upload_id = init_data["upload_id"]
        file_id = init_data["file_id"]
        print(f"✅ Init successful: upload_id={upload_id}, file_id={file_id}")
        
        # Step 2: Upload chunks
        CHUNK_SIZE = 20 * 1024 * 1024  # 20MB chunks
        total_chunks = (file_size + CHUNK_SIZE - 1) // CHUNK_SIZE
        
        print(f"📦 Step 2: Uploading {total_chunks} chunks...")
        
        for chunk_num in range(total_chunks):
            start = chunk_num * CHUNK_SIZE
            end = min(start + CHUNK_SIZE, file_size)
            chunk_data = excel_buffer.getvalue()[start:end]
            
            part_response = requests.post(
                f"{BASE_URL}/api/v1/upload/multipart/part",
                params={"upload_id": upload_id, "part_number": chunk_num + 1},
                data=chunk_data,
                headers={**headers, "Content-Type": "application/octet-stream"},
                timeout=60
            )
            
            if part_response.status_code != 200:
                print(f"❌ Part {chunk_num + 1} failed: {part_response.status_code}")
                return False
            
            print(f"✅ Part {chunk_num + 1}/{total_chunks} uploaded")
        
        # Step 3: Complete
        print(f"🔚 Step 3: Completing upload...")
        start_time = time.perf_counter()
        
        complete_response = requests.post(
            f"{BASE_URL}/api/v1/upload/multipart/complete",
            json={"upload_id": upload_id},
            headers=headers,
            timeout=30
        )
        
        complete_time = time.perf_counter() - start_time
        
        if complete_response.status_code == 200:
            complete_data = complete_response.json()
            print(f"✅ Chunked upload completed in {complete_time:.2f}s!")
            print(f"📊 File ID: {complete_data.get('file_id')}")
            print(f"📈 Status: {complete_data.get('status')}")
            print(f"📏 Size: {complete_data.get('size_bytes', 0) / (1024*1024):.1f}MB")
            return True
        else:
            print(f"❌ Complete failed: {complete_response.status_code} - {complete_response.text}")
            return False
            
    except Exception as e:
        print(f"❌ Chunked upload error: {e}")
        return False

def main():
    """Main unified upload system test"""
    print("🧪 UNIFIED UPLOAD SYSTEM TEST")
    print("="*60)
    print("Testing unified upload system with various file sizes")
    print("="*60)
    
    results = {}
    
    # Test 1: Small file (should process directly)
    results['small_file'] = test_unified_upload_small()
    
    # Test 2: Large file (should require chunked upload)
    results['large_file'] = test_unified_upload_large()
    
    # Test 3: Chunked upload flow
    results['chunked_flow'] = test_chunked_upload_flow()
    
    # Summary
    print("\n" + "="*60)
    print("📊 UNIFIED UPLOAD SYSTEM TEST SUMMARY")
    print("="*60)
    
    passed_tests = sum(results.values())
    total_tests = len(results)
    
    for test_name, passed in results.items():
        status = "✅ PASS" if passed else "❌ FAIL"
        print(f"{test_name.replace('_', ' ').title()}: {status}")
    
    print(f"\nOverall: {passed_tests}/{total_tests} tests passed ({passed_tests/total_tests*100:.1f}%)")
    
    if passed_tests == total_tests:
        print("\n🚀 UNIFIED UPLOAD SYSTEM IS WORKING PERFECTLY!")
        return True
    else:
        print(f"\n⚠️ UNIFIED UPLOAD SYSTEM NEEDS ATTENTION ({total_tests - passed_tests} issues)")
        return False

if __name__ == "__main__":
    success = main()
    exit(0 if success else 1)
