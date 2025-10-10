#!/usr/bin/env python3
"""
Check All Files Status
"""

import requests

def check_all_files():
    """Check status of all uploaded files"""
    
    print("📊 CHECKING ALL FILES STATUS")
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
    
    # Get all files
    try:
        response = requests.get(
            f"{BASE_URL}/api/v1/upload/",
            headers=headers,
            timeout=30
        )
        
        if response.status_code == 200:
            files = response.json()
            print(f"📁 Found {len(files)} files")
            print("\n📋 FILE STATUS SUMMARY:")
            print("-" * 50)
            
            completed_files = []
            processing_files = []
            failed_files = []
            
            for file in files[-10:]:  # Show last 10 files
                file_id = file.get('id', 'unknown')
                filename = file.get('filename', 'unknown')
                status = file.get('status', 'unknown')
                total_rows = file.get('rows_count', 0)
                size_mb = file.get('size_bytes', 0) / (1024*1024)
                
                print(f"📄 File {file_id}: {filename}")
                print(f"   Status: {status}")
                print(f"   Rows: {total_rows:,}")
                print(f"   Size: {size_mb:.1f}MB")
                print()
                
                if status == 'completed':
                    completed_files.append((file_id, total_rows))
                elif status == 'processing':
                    processing_files.append(file_id)
                elif status == 'failed':
                    failed_files.append(file_id)
            
            print("📊 SUMMARY:")
            print(f"✅ Completed: {len(completed_files)}")
            print(f"⏳ Processing: {len(processing_files)}")
            print(f"❌ Failed: {len(failed_files)}")
            
            if completed_files:
                print("\n🎯 COMPLETED FILES ANALYSIS:")
                for file_id, rows in completed_files:
                    if rows > 100000:
                        print(f"✅ File {file_id}: {rows:,} rows - EXCELLENT!")
                    elif rows > 10000:
                        print(f"✅ File {file_id}: {rows:,} rows - GOOD!")
                    elif rows > 1000:
                        print(f"⚠️ File {file_id}: {rows:,} rows - LIMITED")
                    else:
                        print(f"❌ File {file_id}: {rows:,} rows - TOO FEW")
            
            return True
        else:
            print(f"❌ Failed to get files: {response.status_code}")
            return False
            
    except Exception as e:
        print(f"❌ Error getting files: {e}")
        return False

def main():
    """Main check"""
    print("🧪 ALL FILES STATUS CHECK")
    print("="*50)
    print("Checking status of all uploaded files")
    print("="*50)
    
    success = check_all_files()
    
    print("\n" + "="*50)
    print("📊 ANALYSIS COMPLETE")
    print("="*50)
    
    if success:
        print("🚀 FILE STATUS CHECK SUCCESSFUL!")
        print("\n📋 KEY INSIGHTS:")
        print("   • Check completed files for row counts")
        print("   • Monitor processing files")
        print("   • Identify any failed files")
        print("\n🎯 This helps verify the parser improvements")
    else:
        print("⚠️ FILE STATUS CHECK FAILED")
    
    return success

if __name__ == "__main__":
    success = main()
    exit(0 if success else 1)
