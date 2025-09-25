#!/usr/bin/env python3

import sys
sys.path.insert(0, '.')
from app.core.database import SessionLocal
from sqlalchemy import text

def check_dataset_columns():
    db = SessionLocal()
    try:
        # Check the structure of ds_39 table
        result = db.execute(text("SELECT column_name FROM information_schema.columns WHERE table_name = 'ds_39' AND table_schema = 'public' ORDER BY ordinal_position"))
        columns = [row[0] for row in result.fetchall()]
        print(f'ds_39 table columns: {columns}')
        
        # Check the structure of ds_38 table
        result = db.execute(text("SELECT column_name FROM information_schema.columns WHERE table_name = 'ds_38' AND table_schema = 'public' ORDER BY ordinal_position"))
        columns = [row[0] for row in result.fetchall()]
        print(f'ds_38 table columns: {columns}')
        
    finally:
        db.close()

if __name__ == "__main__":
    check_dataset_columns()

