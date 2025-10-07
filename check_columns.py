#!/usr/bin/env python3

from app.core.database import get_db
from sqlalchemy import text

def check_columns():
    try:
        print("🔍 Checking column names in ds_38...")
        
        # Get database connection
        db = next(get_db())
        print("✅ Database connection successful")
        
        # Get column names
        columns_sql = """
            SELECT column_name 
            FROM information_schema.columns 
            WHERE table_name = 'ds_38' 
            AND table_schema = 'public'
            ORDER BY ordinal_position
        """
        
        columns = db.execute(text(columns_sql)).fetchall()
        print(f"✅ Found {len(columns)} columns:")
        for i, col in enumerate(columns):
            print(f"   {i+1:2d}. {col[0]}")
        
        # Check for secondary buyer columns specifically
        secondary_cols = [col[0] for col in columns if 'secondary' in col[0].lower() or 'buyer 2' in col[0].lower()]
        print(f"\n✅ Secondary buyer related columns:")
        for col in secondary_cols:
            print(f"   - {col}")
        
        db.close()
        print("\n✅ Column check completed")
        
    except Exception as e:
        print(f"❌ Error during column check: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    check_columns()

