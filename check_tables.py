#!/usr/bin/env python3

from app.core.database import get_db
from sqlalchemy import text

def check_tables():
    try:
        print("🔍 Checking available tables...")
        
        # Get database connection
        db = next(get_db())
        print("✅ Database connection successful")
        
        # List all tables
        tables = db.execute(text("""
            SELECT table_name 
            FROM information_schema.tables 
            WHERE table_schema = 'public' 
            AND table_name LIKE 'ds_%'
            ORDER BY table_name
        """)).fetchall()
        
        print(f"✅ Found {len(tables)} dataset tables:")
        for table in tables:
            table_name = table[0]
            # Get row count for each table
            count = db.execute(text(f"SELECT COUNT(*) FROM {table_name}")).scalar()
            print(f"   - {table_name}: {count:,} rows")
            
            # Check for SMD in first few tables
            if count > 0:
                smd_count = db.execute(text(f"""
                    SELECT COUNT(*) FROM {table_name} 
                    WHERE LOWER("part_number") = LOWER('SMD') 
                    OR CAST("Item_Description" AS TEXT) ILIKE '%SMD%'
                """)).scalar()
                print(f"     └─ SMD matches: {smd_count}")
        
        db.close()
        print("\n✅ Table check completed")
        
    except Exception as e:
        print(f"❌ Error during table check: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    check_tables()

