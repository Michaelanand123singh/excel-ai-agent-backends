#!/usr/bin/env python3
"""
Test Multipart Complete Fix - Large File
"""

import requests
import time
import io
import pandas as pd

def test_multipart_complete_large():
    """Test multipart complete endpoint with large file"""
    
    print("🧪 TESTING MULTIPART COMPLETE FIX - LARGE FILE")
    print("="*60)
    
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
    
    # Create test Excel file (60MB to test the 50MB threshold)
    print("📊 Creating large test Excel file...")
    
    # Create a large DataFrame to simulate 60MB file
    test_data = []
    for i in range(100000):  # 100K rows should be around 60MB
        test_data.append({
            'Part Number': f'TEST{i:06d}',
            'Description': f'Test part number {i} with longer description to increase file size',
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
    print(f"✅ Created Excel file: {file_size / (1024*1024):.1f}MB")
    
    # Test multipart upload
    print("\n📤 Testing multipart upload...")
    
    # Step 1: Init
    init_response = requests.post(
        f"{BASE_URL}/api/v1/upload/multipart/init",
        json={
            "filename": "test_large_multipart.xlsx",
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
    
    print(f"📦 Uploading {total_chunks} chunks...")
    
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
            print(f"❌ Part {chunk_num + 1} failed: {part_response.status_code} - {part_response.text}")
            return False
        
        print(f"✅ Part {chunk_num + 1}/{total_chunks} uploaded")
    
    # Step 3: Complete
    print(f"\n🔚 Completing upload...")
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
        print(f"✅ Complete successful in {complete_time:.2f}s!")
        print(f"📊 File ID: {complete_data.get('file_id')}")
        print(f"📈 Status: {complete_data.get('status')}")
        print(f"📏 Size: {complete_data.get('size_bytes', 0) / (1024*1024):.1f}MB")
        
        # Check file status
        time.sleep(2)
        status_response = requests.get(
            f"{BASE_URL}/api/v1/upload/{file_id}",
            headers=headers,
            timeout=30
        )
        
        if status_response.status_code == 200:
            status_data = status_response.json()
            print(f"📋 File status: {status_data.get('status', 'unknown')}")
            print(f"📈 Total rows: {status_data.get('total_rows', 'unknown')}")
        
        return True
    else:
        print(f"❌ Complete failed: {complete_response.status_code} - {complete_response.text}")
        return False

if __name__ == "__main__":
    test_multipart_complete_large()
