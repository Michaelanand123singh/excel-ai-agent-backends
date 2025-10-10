#!/usr/bin/env python3
"""
Test Unified Upload with Real Large File
"""

import requests
import time
import os

def test_real_large_file():
    """Test with the actual large file provided by user"""
    
    print("🧪 TESTING UNIFIED UPLOAD WITH REAL LARGE FILE")
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
    
    # Check if the file exists
    file_path = "File For Upload.xlsx"
    if not os.path.exists(file_path):
        print(f"❌ File not found: {file_path}")
        return False
    
    file_size = os.path.getsize(file_path)
    print(f"📊 Found file: {file_path}")
    print(f"📏 File size: {file_size / (1024*1024):.1f}MB")
    
    # Test unified upload with the real file
    try:
        print("📤 Testing unified upload with real large file...")
        start_time = time.perf_counter()
        
        with open(file_path, 'rb') as f:
            files = {
                'file': ('File For Upload.xlsx', f, 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
            }
            
            response = requests.post(
                f"{BASE_URL}/api/v1/upload",
                files=files,
                headers=headers,
                timeout=120
            )
        
        upload_time = time.perf_counter() - start_time
        
        if response.status_code == 200:
            data = response.json()
            print(f"✅ File upload response in {upload_time:.2f}s!")
            
            # Check if it requires chunked upload (should for large files)
            if data.get('requires_chunked_upload'):
                print("✅ Large file correctly requires chunked upload")
                print(f"📋 Message: {data.get('message')}")
                print(f"📏 Max chunk size: {data.get('max_chunk_size', 0) / (1024*1024):.1f}MB")
                print("✅ Unified upload system working correctly!")
                return True
            else:
                print("❌ Large file should require chunked upload but doesn't")
                print(f"📊 Response: {data}")
                print("⚠️ File was processed directly instead of requiring chunked upload")
                return False
        else:
            print(f"❌ File upload failed: {response.status_code} - {response.text}")
            return False
            
    except Exception as e:
        print(f"❌ File upload error: {e}")
        return False

def test_small_file_for_comparison():
    """Test with a small file to verify direct processing works"""
    
    print("\n🧪 TESTING SMALL FILE FOR COMPARISON")
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
    
    # Create a small test file
    import io
    import pandas as pd
    
    test_data = []
    for i in range(1000):  # Small dataset
        test_data.append({
            'Part Number': f'SMALL{i:04d}',
            'Description': f'Small test part {i}',
            'Quantity': i % 5 + 1
        })
    
    df = pd.DataFrame(test_data)
    excel_buffer = io.BytesIO()
    df.to_excel(excel_buffer, index=False, sheet_name='Parts')
    excel_buffer.seek(0)
    
    file_size = len(excel_buffer.getvalue())
    print(f"📊 Created small test file: {file_size / (1024*1024):.1f}MB")
    
    # Test unified upload
    files = {
        'file': ('test_small.xlsx', excel_buffer, 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
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
            
            # Check if it requires chunked upload (should not for small files)
            if data.get('requires_chunked_upload'):
                print("❌ Small file incorrectly requires chunked upload")
                return False
            else:
                print("✅ Small file processed directly (correct)")
                print(f"📊 File ID: {data.get('id')}")
                print(f"📈 Status: {data.get('status')}")
                return True
        else:
            print(f"❌ Small file upload failed: {response.status_code} - {response.text}")
            return False
            
    except Exception as e:
        print(f"❌ Small file upload error: {e}")
        return False

def main():
    """Main test"""
    print("🧪 UNIFIED UPLOAD SYSTEM TEST WITH REAL FILES")
    print("="*60)
    print("Testing with actual large file provided by user")
    print("="*60)
    
    results = {}
    
    # Test 1: Real large file
    results['real_large_file'] = test_real_large_file()
    
    # Test 2: Small file for comparison
    results['small_file'] = test_small_file_for_comparison()
    
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
