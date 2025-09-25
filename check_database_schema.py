#!/usr/bin/env python3

import sys
sys.path.insert(0, '.')
from app.core.database import SessionLocal
from sqlalchemy import text

def check_database_schema():
    db = SessionLocal()
    try:
        # Check what tables exist
        result = db.execute(text("SELECT table_name FROM information_schema.tables WHERE table_schema = 'public' AND table_name LIKE '%file%'"))
        file_tables = [row[0] for row in result.fetchall()]
        print(f'File-related tables: {file_tables}')
        
        # Check for any table with 'file' in the name
        result = db.execute(text("SELECT table_name FROM information_schema.tables WHERE table_schema = 'public'"))
        all_tables = [row[0] for row in result.fetchall()]
        print(f'All tables: {all_tables}')
        
        # Check for dataset tables
        result = db.execute(text("SELECT table_name FROM information_schema.tables WHERE table_schema = 'public' AND table_name LIKE 'ds_%'"))
        dataset_tables = [row[0] for row in result.fetchall()]
        print(f'Dataset tables: {dataset_tables}')
        
    finally:
        db.close()

if __name__ == "__main__":
    check_database_schema()

