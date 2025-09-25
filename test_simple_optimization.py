#!/usr/bin/env python3
"""
Test simple optimization approaches for bulk search
"""

import sys
from pathlib import Path
import time

# Add the app directory to the Python path
sys.path.insert(0, str(Path(__file__).parent))

from sqlalchemy import text
from app.core.database import SessionLocal

def test_simple_optimization():
    """Test simple optimization approaches"""
    
    print("🚀 Testing Simple Optimization Approaches")
    print("=" * 50)
    
    db = SessionLocal()
    try:
        test_parts = ['R536446', 'R536444', 'FOC IQ8HC 72 M INT']
        
        print(f"📊 Testing with {len(test_parts)} parts...")
        
        # Method 1: Current CROSS JOIN approach
        print("\n1️⃣ Current CROSS JOIN approach:")
        start_time = time.perf_counter()
        
        parts_array = str(test_parts).replace('[', '').replace(']', '')
        current_query = f"""
            SELECT 
                unnest_part as search_part_number,
                "Potential Buyer 1" as company_name,
                "part_number" as part_number,
                CASE 
                    WHEN LOWER("part_number") = LOWER(unnest_part) THEN 'exact_part'
                    WHEN LOWER(CAST("Item_Description" AS TEXT)) ILIKE '%' || LOWER(unnest_part) || '%' THEN 'description_match'
                    ELSE 'no_match'
                END as match_type
            FROM ds_39
            CROSS JOIN unnest(ARRAY[{parts_array}]) as unnest_part
            WHERE 
                LOWER("part_number") = LOWER(unnest_part)
                OR CAST("Item_Description" AS TEXT) ILIKE '%' || unnest_part || '%'
            LIMIT 10
        """
        
        result1 = db.execute(text(current_query)).fetchall()
        time1 = (time.perf_counter() - start_time) * 1000
        print(f"  ⏱️  Time: {time1:.2f}ms")
        print(f"  📊 Results: {len(result1)}")
        
        # Method 2: Simple UNION ALL approach
        print("\n2️⃣ UNION ALL approach:")
        start_time = time.perf_counter()
        
        union_parts = []
        for part in test_parts:
            union_parts.append(f"""
                SELECT 
                    '{part}' as search_part_number,
                    "Potential Buyer 1" as company_name,
                    "part_number" as part_number,
                    CASE 
                        WHEN LOWER("part_number") = LOWER('{part}') THEN 'exact_part'
                        WHEN LOWER(CAST("Item_Description" AS TEXT)) ILIKE '%' || LOWER('{part}') || '%' THEN 'description_match'
                        ELSE 'no_match'
                    END as match_type
                FROM ds_39
                WHERE 
                    LOWER("part_number") = LOWER('{part}')
                    OR CAST("Item_Description" AS TEXT) ILIKE '%' || '{part}' || '%'
            """)
        
        union_query = " UNION ALL ".join(union_parts)
        
        result2 = db.execute(text(union_query)).fetchall()
        time2 = (time.perf_counter() - start_time) * 1000
        print(f"  ⏱️  Time: {time2:.2f}ms")
        print(f"  📊 Results: {len(result2)}")
        
        # Method 3: Individual queries (simulated)
        print("\n3️⃣ Individual queries approach:")
        start_time = time.perf_counter()
        
        all_results = []
        for part in test_parts:
            part_query = f"""
                SELECT 
                    '{part}' as search_part_number,
                    "Potential Buyer 1" as company_name,
                    "part_number" as part_number,
                    CASE 
                        WHEN LOWER("part_number") = LOWER('{part}') THEN 'exact_part'
                        WHEN LOWER(CAST("Item_Description" AS TEXT)) ILIKE '%' || LOWER('{part}') || '%' THEN 'description_match'
                        ELSE 'no_match'
                    END as match_type
                FROM ds_39
                WHERE 
                    LOWER("part_number") = LOWER('{part}')
                    OR CAST("Item_Description" AS TEXT) ILIKE '%' || '{part}' || '%'
                LIMIT 3
            """
            
            part_result = db.execute(text(part_query)).fetchall()
            all_results.extend(part_result)
        
        time3 = (time.perf_counter() - start_time) * 1000
        print(f"  ⏱️  Time: {time3:.2f}ms")
        print(f"  📊 Results: {len(all_results)}")
        
        # Performance comparison
        print(f"\n📈 Performance Comparison:")
        print(f"  CROSS JOIN: {time1:.2f}ms")
        print(f"  UNION ALL:  {time2:.2f}ms")
        print(f"  Individual: {time3:.2f}ms")
        
        if time2 < time1:
            print(f"  ✅ UNION ALL is {time1/time2:.1f}x faster than CROSS JOIN")
        if time3 < time1:
            print(f"  ✅ Individual queries are {time1/time3:.1f}x faster than CROSS JOIN")
            
        # Test with more parts to see scaling
        print(f"\n📊 Testing scaling with 10 parts...")
        test_parts_10 = test_parts + ['MAT0170187', 'MAT01718034', 'MAT0170640', 'CF113.037.D', 'CF270.UL.40.04.D', 'CF78.UL.10.03', 'CFBUS.PVC.049']
        
        start_time = time.perf_counter()
        union_parts_10 = []
        for part in test_parts_10:
            union_parts_10.append(f"""
                SELECT 
                    '{part}' as search_part_number,
                    "Potential Buyer 1" as company_name,
                    "part_number" as part_number,
                    CASE 
                        WHEN LOWER("part_number") = LOWER('{part}') THEN 'exact_part'
                        WHEN LOWER(CAST("Item_Description" AS TEXT)) ILIKE '%' || LOWER('{part}') || '%' THEN 'description_match'
                        ELSE 'no_match'
                    END as match_type
                FROM ds_39
                WHERE 
                    LOWER("part_number") = LOWER('{part}')
                    OR CAST("Item_Description" AS TEXT) ILIKE '%' || '{part}' || '%'
            """)
        
        union_query_10 = " UNION ALL ".join(union_parts_10)
        result_10 = db.execute(text(union_query_10)).fetchall()
        time_10 = (time.perf_counter() - start_time) * 1000
        print(f"  ⏱️  Time for 10 parts: {time_10:.2f}ms")
        print(f"  📊 Results: {len(result_10)}")
        
        # Estimate for 157 parts
        estimated_time = (time_10 / 10) * 157
        print(f"  🔮 Estimated time for 157 parts: {estimated_time:.2f}ms ({estimated_time/1000:.1f}s)")
        
    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()
    finally:
        db.close()

if __name__ == "__main__":
    test_simple_optimization()

