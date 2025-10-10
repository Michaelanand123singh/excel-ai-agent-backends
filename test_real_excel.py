#!/usr/bin/env python3
"""
Test Real Excel File Upload
"""

import requests
import time
import io
import pandas as pd

def test_real_excel_upload():
    """Test with a real Excel file structure"""
    
    print("🧪 TESTING REAL EXCEL FILE UPLOAD")
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
    
    # Create realistic Excel file with part numbers
    print("📊 Creating realistic Excel file...")
    
    # Read real part numbers
    try:
        with open("part_number", "r") as f:
            content = f.read().strip()
            part_numbers = [p.strip() for p in content.split(",") if p.strip()]
    except FileNotFoundError:
        print("❌ part_number file not found!")
        return False
    
    # Create Excel file with first 1000 part numbers
    test_parts = part_numbers[:1000]
    df = pd.DataFrame({
        'Part Number': test_parts,
        'Description': [f'Description for part {i+1}' for i in range(len(test_parts))],
        'Quantity': [1] * len(test_parts),
        'Manufacturer': ['Test Manufacturer'] * len(test_parts)
    })
    
    excel_buffer = io.BytesIO()
    df.to_excel(excel_buffer, index=False, sheet_name='Parts')
    excel_buffer.seek(0)
    
    file_size = len(excel_buffer.getvalue())
    print(f"✅ Created Excel file: {file_size / (1024*1024):.1f}MB with {len(test_parts)} part numbers")
    
    # Test regular upload (not multipart for smaller file)
    print("\n📤 Testing regular upload...")
    
    files = {
        'file': ('test_real_excel.xlsx', excel_buffer, 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
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
            file_id = upload_data.get('file_id')
            print(f"✅ Excel file uploaded successfully (ID: {file_id})")
            
            # Wait for processing
            print("⏳ Waiting for file processing...")
            time.sleep(5)
            
            # Check file status
            status_response = requests.get(
                f"{BASE_URL}/api/v1/upload/{file_id}",
                headers=headers,
                timeout=30
            )
            
            if status_response.status_code == 200:
                status_data = status_response.json()
                print(f"📊 File status: {status_data.get('status', 'unknown')}")
                print(f"📈 Total rows: {status_data.get('total_rows', 'unknown')}")
                print(f"📋 File name: {status_data.get('filename', 'unknown')}")
                
                if status_data.get('status') == 'completed':
                    print("✅ File processing completed successfully!")
                    return True
                else:
                    print(f"⚠️ File still processing or failed: {status_data.get('status')}")
                    return False
            else:
                print(f"❌ Could not check file status: {status_response.status_code}")
                return False
        else:
            print(f"❌ Excel upload failed: {upload_response.status_code} - {upload_response.text}")
            return False
            
    except Exception as e:
        print(f"❌ Excel upload error: {e}")
        return False

if __name__ == "__main__":
    test_real_excel_upload()
