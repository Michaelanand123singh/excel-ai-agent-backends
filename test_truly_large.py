#!/usr/bin/env python3
"""
Test with Truly Large File
"""

import requests
import time
import io
import pandas as pd

def test_truly_large_file():
    """Test with a file that's actually over 20MB"""
    
    print("🧪 TESTING TRULY LARGE FILE (30MB)")
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
    
    # Create a file that's actually over 20MB by creating a much larger dataset
    print("📊 Creating truly large Excel file (30MB)...")
    
    test_data = []
    for i in range(200000):  # 200K rows with lots of data
        test_data.append({
            'Part Number': f'LARGE{i:06d}',
            'Description': f'Large test part {i} with very long description to increase file size significantly and make it exceed the 20MB threshold',
            'Quantity': i % 10 + 1,
            'Manufacturer': f'Manufacturer {i % 5} with very long company name and additional details',
            'Category': f'Category {i % 20} with extended category description and more information',
            'Price': f'${i % 1000}.{i % 100:02d}',
            'Notes': f'Additional notes for part {i} to make the file larger with more detailed information',
            'Specifications': f'Detailed specifications for part {i} including dimensions, weight, and other technical details',
            'Applications': f'Various applications and use cases for part {i} in different industries and sectors'
        })
    
    df = pd.DataFrame(test_data)
    excel_buffer = io.BytesIO()
    df.to_excel(excel_buffer, index=False, sheet_name='Parts')
    excel_buffer.seek(0)
    
    file_size = len(excel_buffer.getvalue())
    print(f"✅ Created large Excel file: {file_size / (1024*1024):.1f}MB")
    
    # Test unified upload
    files = {
        'file': ('test_truly_large.xlsx', excel_buffer, 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
    }
    
    try:
        print("📤 Testing unified upload with truly large file...")
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
                print(f"📊 Response keys: {list(data.keys())}")
                return False
        else:
            print(f"❌ Large file upload failed: {response.status_code} - {response.text}")
            return False
            
    except Exception as e:
        print(f"❌ Large file upload error: {e}")
        return False

if __name__ == "__main__":
    test_truly_large_file()
