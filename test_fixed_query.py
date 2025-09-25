#!/usr/bin/env python3
"""
Test the fixed ultra-fast bulk search query
"""

import sys
from pathlib import Path

# Add the app directory to the Python path
sys.path.insert(0, str(Path(__file__).parent))

from sqlalchemy import text
from app.core.database import SessionLocal

def test_fixed_query():
    """Test the fixed ultra-fast bulk search query"""
    
    db = SessionLocal()
    try:
        # Test the fixed query directly
        test_query = """
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
                NULL as secondary_buyer_contact,
                NULL as secondary_buyer_email,
                unnest_part as search_part_number,
                CASE 
                    WHEN LOWER("part_number") = LOWER(unnest_part) THEN 'exact_part'
                    WHEN LOWER(CAST("Item_Description" AS TEXT)) ILIKE '%' || LOWER(unnest_part) || '%' THEN 'description_match'
                    WHEN similarity(lower(CAST("Item_Description" AS TEXT)), lower(unnest_part)) >= 0.6 THEN 'fuzzy_match'
                    ELSE 'no_match'
                END as match_type,
                similarity(lower(CAST("Item_Description" AS TEXT)), lower(unnest_part)) as similarity_score
            FROM ds_39
            CROSS JOIN unnest(ARRAY['8065103', '8065127']) as unnest_part
            WHERE 
                LOWER("part_number") = LOWER(unnest_part)
                OR CAST("Item_Description" AS TEXT) ILIKE '%' || unnest_part || '%'
                OR similarity(lower(CAST("Item_Description" AS TEXT)), lower(unnest_part)) >= 0.6
        ),
        grouped_results AS (
            SELECT 
                search_part_number,
                match_type,
                similarity_score,
                company_name,
                contact_details,
                email,
                quantity,
                unit_price,
                item_description,
                part_number,
                uqc,
                secondary_buyer,
                secondary_buyer_contact,
                secondary_buyer_email,
                ROW_NUMBER() OVER (PARTITION BY search_part_number ORDER BY 
                    CASE match_type 
                        WHEN 'exact_part' THEN 1
                        WHEN 'description_match' THEN 2
                        WHEN 'fuzzy_match' THEN 3
                        ELSE 4
                    END,
                    similarity_score DESC,
                    unit_price ASC
                ) as rn
            FROM part_search
        )
        SELECT 
            search_part_number,
            match_type,
            similarity_score,
            company_name,
            contact_details,
            email,
            quantity,
            unit_price,
            item_description,
            part_number,
            uqc,
            secondary_buyer,
            secondary_buyer_contact,
            secondary_buyer_email
        FROM grouped_results
        WHERE rn <= 3
        ORDER BY search_part_number, rn
        LIMIT 10
        """
        
        result = db.execute(text(test_query)).fetchall()
        print(f'✅ Query executed successfully! Found {len(result)} results')
        
        if result:
            print('\n📊 Sample results:')
            for i, row in enumerate(result[:3]):
                print(f'  Result {i+1}:')
                row_dict = dict(row._mapping)
                for key, value in row_dict.items():
                    if value is not None:
                        print(f'    {key}: {value}')
                print()
        else:
            print('ℹ️ No results found for the test part numbers')
            
    except Exception as e:
        print(f'❌ Error: {e}')
    finally:
        db.close()

if __name__ == "__main__":
    test_fixed_query()

