#!/usr/bin/env python3

import sys
sys.path.insert(0, '.')
from app.core.database import SessionLocal
from sqlalchemy import text

def check_file_table():
    db = SessionLocal()
    try:
        # Check the structure of the file table
        result = db.execute(text("SELECT column_name, data_type FROM information_schema.columns WHERE table_name = 'file' AND table_schema = 'public'"))
        columns = [(row[0], row[1]) for row in result.fetchall()]
        print(f'File table columns: {columns}')
        
        # Check what data is in the file table
        result = db.execute(text('SELECT * FROM file LIMIT 5'))
        rows = result.fetchall()
        print(f'Sample data from file table: {rows}')
        
    finally:
        db.close()

if __name__ == "__main__":
    check_file_table()

