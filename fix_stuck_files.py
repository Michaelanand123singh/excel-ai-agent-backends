#!/usr/bin/env python3
"""
Script to check and fix stuck files in the database
"""

import os
import sys
from sqlalchemy.orm import Session
from sqlalchemy import text

# Add the app directory to the path
sys.path.append(os.path.join(os.path.dirname(__file__), 'app'))

from app.core.database import SessionLocal
from app.models.database.file import File as FileModel

def check_stuck_files():
    """Check for stuck files in the database"""
    session: Session = SessionLocal()
    try:
        # Find files stuck in processing state
        stuck_files = session.query(FileModel).filter(
            FileModel.status == "processing"
        ).all()
        
        print(f"🔍 Found {len(stuck_files)} stuck files:")
        print("-" * 60)
        
        for file_obj in stuck_files:
            print(f"File ID: {file_obj.id}")
            print(f"Filename: {file_obj.filename}")
            print(f"Status: {file_obj.status}")
            print(f"Size: {file_obj.size_bytes} bytes")
            print(f"Rows: {file_obj.rows_count}")
            print(f"Content Type: {file_obj.content_type}")
            print("-" * 60)
        
        return stuck_files
        
    except Exception as e:
        print(f"❌ Error checking stuck files: {e}")
        return []
    finally:
        session.close()

def fix_stuck_file(file_id: int):
    """Fix a specific stuck file"""
    session: Session = SessionLocal()
    try:
        file_obj = session.get(FileModel, file_id)
        if not file_obj:
            print(f"❌ File {file_id} not found")
            return False
        
        if file_obj.status == "processing":
            file_obj.status = "failed"
            session.add(file_obj)
            session.commit()
            print(f"✅ Reset file {file_id} status from 'processing' to 'failed'")
            return True
        else:
            print(f"ℹ️  File {file_id} is not stuck (status: {file_obj.status})")
            return False
            
    except Exception as e:
        session.rollback()
        print(f"❌ Error fixing file {file_id}: {e}")
        return False
    finally:
        session.close()

def fix_all_stuck_files():
    """Fix all stuck files"""
    stuck_files = check_stuck_files()
    
    if not stuck_files:
        print("✅ No stuck files found!")
        return
    
    print(f"\n🔧 Fixing {len(stuck_files)} stuck files...")
    
    fixed_count = 0
    for file_obj in stuck_files:
        if fix_stuck_file(file_obj.id):
            fixed_count += 1
    
    print(f"\n✅ Fixed {fixed_count} out of {len(stuck_files)} stuck files")

def main():
    print("🚀 Stuck Files Checker & Fixer")
    print("=" * 50)
    
    if len(sys.argv) > 1:
        if sys.argv[1] == "fix-all":
            fix_all_stuck_files()
        elif sys.argv[1].isdigit():
            file_id = int(sys.argv[1])
            fix_stuck_file(file_id)
        else:
            print("Usage: python fix_stuck_files.py [fix-all|file_id]")
    else:
        check_stuck_files()
        print("\n💡 To fix all stuck files: python fix_stuck_files.py fix-all")
        print("💡 To fix specific file: python fix_stuck_files.py <file_id>")

if __name__ == "__main__":
    main()
