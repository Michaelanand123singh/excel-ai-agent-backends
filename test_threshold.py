#!/usr/bin/env python3
"""
Test Unified Upload with Proper Large File
"""

import requests
import time
import io
import pandas as pd

def test_large_file_threshold():
    """Test with a file that actually exceeds 20MB"""
    
    print("🧪 TESTING LARGE FILE THRESHOLD (25MB)")
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
    
    # Create a file that's actually over 20MB
    print("📊 Creating large Excel file (25MB)...")
    
    test_data = []
    for i in range(50000):  # 50K rows should be around 25MB
        test_data.append({
            'Part Number': f'LARGE{i:05d}',
            'Description': f'Large test part {i} with very long description to increase file size significantly',
            'Quantity': i % 10 + 1,
            'Manufacturer': f'Manufacturer {i % 5} with long company name',
            'Category': f'Category {i % 20} with extended category description',
            'Price': f'${i % 1000}.{i % 100:02d}',
            'Notes': f'Additional notes for part {i} to make the file larger'
        })
    
    df = pd.DataFrame(test_data)
    excel_buffer = io.BytesIO()
    df.to_excel(excel_buffer, index=False, sheet_name='Parts')
    excel_buffer.seek(0)
    
    file_size = len(excel_buffer.getvalue())
    print(f"✅ Created large Excel file: {file_size / (1024*1024):.1f}MB")
    
    # Test unified upload
    files = {
        'file': ('test_large_threshold.xlsx', excel_buffer, 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
    }
    
    try:
        print("📤 Testing unified upload with large file...")
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
                print(f"📊 Response: {data}")
                return False
        else:
            print(f"❌ Large file upload failed: {response.status_code} - {response.text}")
            return False
            
    except Exception as e:
        print(f"❌ Large file upload error: {e}")
        return False

def test_small_file_direct():
    """Test with a small file that should process directly"""
    
    print("\n🧪 TESTING SMALL FILE DIRECT PROCESSING (5MB)")
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
    
    # Create a small file (5MB)
    print("📊 Creating small Excel file (5MB)...")
    
    test_data = []
    for i in range(10000):  # 10K rows should be around 5MB
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
        'file': ('test_small_direct.xlsx', excel_buffer, 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
    }
    
    try:
        print("📤 Testing unified upload with small file...")
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

def main():
    """Main test"""
    print("🧪 UNIFIED UPLOAD THRESHOLD TEST")
    print("="*60)
    print("Testing file size threshold behavior")
    print("="*60)
    
    results = {}
    
    # Test 1: Small file (should process directly)
    results['small_direct'] = test_small_file_direct()
    
    # Test 2: Large file (should require chunked upload)
    results['large_threshold'] = test_large_file_threshold()
    
    # Summary
    print("\n" + "="*60)
    print("📊 UNIFIED UPLOAD THRESHOLD TEST SUMMARY")
    print("="*60)
    
    passed_tests = sum(results.values())
    total_tests = len(results)
    
    for test_name, passed in results.items():
        status = "✅ PASS" if passed else "❌ FAIL"
        print(f"{test_name.replace('_', ' ').title()}: {status}")
    
    print(f"\nOverall: {passed_tests}/{total_tests} tests passed ({passed_tests/total_tests*100:.1f}%)")
    
    if passed_tests == total_tests:
        print("\n🚀 UNIFIED UPLOAD THRESHOLD IS WORKING PERFECTLY!")
        return True
    else:
        print(f"\n⚠️ UNIFIED UPLOAD THRESHOLD NEEDS ATTENTION ({total_tests - passed_tests} issues)")
        return False

if __name__ == "__main__":
    success = main()
    exit(0 if success else 1)
