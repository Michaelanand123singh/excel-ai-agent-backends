#!/usr/bin/env python3
"""
Test optimized bulk search query structure
"""

import sys
from pathlib import Path
import time

# Add the app directory to the Python path
sys.path.insert(0, str(Path(__file__).parent))

from sqlalchemy import text
from app.core.database import SessionLocal

def test_optimized_query():
    """Test optimized bulk search query structure"""
    
    print("🚀 Testing Optimized Bulk Search Query")
    print("=" * 50)
    
    db = SessionLocal()
    try:
        test_parts = ['R536446', 'R536444', 'FOC IQ8HC 72 M INT', 'MAT0170187', 'MAT01718034']
        
        print(f"📊 Testing with {len(test_parts)} parts...")
        
        # Method 1: Current approach (CROSS JOIN unnest)
        print("\n1️⃣ Current approach (CROSS JOIN unnest):")
        start_time = time.perf_counter()
        
        parts_array = str(test_parts).replace('[', '').replace(']', '')
        current_query = f"""
            WITH part_search AS (
                SELECT 
                    "Potential Buyer 1" as company_name,
                    "Potential Buyer 1 Contact Details" as contact_details,
                    "Potential Buyer 1 email id" as email,
                    "Quantity" as quantity,
                    "Unit_Price" as unit_price,
                    "Item_Description" as item_description,
                    "part_number" as part_number,
                    "UQC" as uqc,
                    "Potential Buyer 2" as secondary_buyer,
                    unnest_part as search_part_number,
                    CASE 
                        WHEN LOWER("part_number") = LOWER(unnest_part) THEN 'exact_part'
                        WHEN LOWER(CAST("Item_Description" AS TEXT)) ILIKE '%' || LOWER(unnest_part) || '%' THEN 'description_match'
                        WHEN similarity(lower(CAST("Item_Description" AS TEXT)), lower(unnest_part)) >= 0.6 THEN 'fuzzy_match'
                        ELSE 'no_match'
                    END as match_type,
                    similarity(lower(CAST("Item_Description" AS TEXT)), lower(unnest_part)) as similarity_score
                FROM ds_39
                CROSS JOIN unnest(ARRAY[{parts_array}]) as unnest_part
                WHERE 
                    LOWER("part_number") = LOWER(unnest_part)
                    OR CAST("Item_Description" AS TEXT) ILIKE '%' || unnest_part || '%'
                    OR similarity(lower(CAST("Item_Description" AS TEXT)), lower(unnest_part)) >= 0.6
            )
            SELECT search_part_number, company_name, part_number, match_type
            FROM part_search
            ORDER BY search_part_number
        """
        
        result1 = db.execute(text(current_query)).fetchall()
        time1 = (time.perf_counter() - start_time) * 1000
        print(f"  ⏱️  Time: {time1:.2f}ms")
        print(f"  📊 Results: {len(result1)}")
        
        # Method 2: Optimized approach (separate queries for each part)
        print("\n2️⃣ Optimized approach (separate queries):")
        start_time = time.perf_counter()
        
        all_results = []
        for part in test_parts:
            part_query = """
                SELECT 
                    %s as search_part_number,
                    "Potential Buyer 1" as company_name,
                    "Potential Buyer 1 Contact Details" as contact_details,
                    "Potential Buyer 1 email id" as email,
                    "Quantity" as quantity,
                    "Unit_Price" as unit_price,
                    "Item_Description" as item_description,
                    "part_number" as part_number,
                    "UQC" as uqc,
                    "Potential Buyer 2" as secondary_buyer,
                    CASE 
                        WHEN LOWER("part_number") = LOWER(%s) THEN 'exact_part'
                        WHEN LOWER(CAST("Item_Description" AS TEXT)) ILIKE '%' || LOWER(%s) || '%' THEN 'description_match'
                        WHEN similarity(lower(CAST("Item_Description" AS TEXT)), lower(%s)) >= 0.6 THEN 'fuzzy_match'
                        ELSE 'no_match'
                    END as match_type,
                    similarity(lower(CAST("Item_Description" AS TEXT)), lower(%s)) as similarity_score
                FROM ds_39
                WHERE 
                    LOWER("part_number") = LOWER(%s)
                    OR CAST("Item_Description" AS TEXT) ILIKE '%' || %s || '%'
                    OR similarity(lower(CAST("Item_Description" AS TEXT)), lower(%s)) >= 0.6
                ORDER BY 
                    CASE match_type 
                        WHEN 'exact_part' THEN 1
                        WHEN 'description_match' THEN 2
                        WHEN 'fuzzy_match' THEN 3
                        ELSE 4
                    END,
                    similarity_score DESC,
                    "Unit_Price" ASC
                LIMIT 3
            """
            
            part_result = db.execute(text(part_query), [part, part, part, part, part, part, part, part]).fetchall()
            all_results.extend(part_result)
        
        time2 = (time.perf_counter() - start_time) * 1000
        print(f"  ⏱️  Time: {time2:.2f}ms")
        print(f"  📊 Results: {len(all_results)}")
        
        # Method 3: Batch approach with UNION ALL
        print("\n3️⃣ Batch approach (UNION ALL):")
        start_time = time.perf_counter()
        
        union_queries = []
        for part in test_parts:
            union_queries.append(f"""
                SELECT 
                    '{part}' as search_part_number,
                    "Potential Buyer 1" as company_name,
                    "Potential Buyer 1 Contact Details" as contact_details,
                    "Potential Buyer 1 email id" as email,
                    "Quantity" as quantity,
                    "Unit_Price" as unit_price,
                    "Item_Description" as item_description,
                    "part_number" as part_number,
                    "UQC" as uqc,
                    "Potential Buyer 2" as secondary_buyer,
                    CASE 
                        WHEN LOWER("part_number") = LOWER('{part}') THEN 'exact_part'
                        WHEN LOWER(CAST("Item_Description" AS TEXT)) ILIKE '%' || LOWER('{part}') || '%' THEN 'description_match'
                        WHEN similarity(lower(CAST("Item_Description" AS TEXT)), lower('{part}')) >= 0.6 THEN 'fuzzy_match'
                        ELSE 'no_match'
                    END as match_type,
                    similarity(lower(CAST("Item_Description" AS TEXT)), lower('{part}')) as similarity_score
                FROM ds_39
                WHERE 
                    LOWER("part_number") = LOWER('{part}')
                    OR CAST("Item_Description" AS TEXT) ILIKE '%' || '{part}' || '%'
                    OR similarity(lower(CAST("Item_Description" AS TEXT)), lower('{part}')) >= 0.6
            """)
        
        batch_query = " UNION ALL ".join(union_queries) + " ORDER BY search_part_number, match_type, similarity_score DESC"
        
        result3 = db.execute(text(batch_query)).fetchall()
        time3 = (time.perf_counter() - start_time) * 1000
        print(f"  ⏱️  Time: {time3:.2f}ms")
        print(f"  📊 Results: {len(result3)}")
        
        # Performance comparison
        print(f"\n📈 Performance Comparison:")
        print(f"  Current (CROSS JOIN): {time1:.2f}ms")
        print(f"  Separate queries: {time2:.2f}ms")
        print(f"  Batch (UNION ALL): {time3:.2f}ms")
        
        if time2 < time1:
            print(f"  ✅ Separate queries are {time1/time2:.1f}x faster")
        if time3 < time1:
            print(f"  ✅ Batch queries are {time1/time3:.1f}x faster")
            
    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()
    finally:
        db.close()

if __name__ == "__main__":
    test_optimized_query()

