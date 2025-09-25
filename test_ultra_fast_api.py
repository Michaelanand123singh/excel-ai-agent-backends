#!/usr/bin/env python3
"""
Test the ultra-fast bulk search API endpoint directly
"""

import sys
from pathlib import Path

# Add the app directory to the Python path
sys.path.insert(0, str(Path(__file__).parent))

from sqlalchemy import text
from app.core.database import SessionLocal
from app.api.v1.endpoints.query_optimized import search_part_number_bulk_ultra_fast
def test_ultra_fast_api():
    """Test the ultra-fast bulk search API endpoint directly"""
    
    print("🚀 Testing Ultra-Fast Bulk Search API")
    print("=" * 50)
    
    # Create a test request as dict
    test_request = {
        'file_id': 39,
        'part_numbers': ['8065103', '8065127'],
        'search_mode': 'hybrid',
        'page': 1,
        'page_size': 50,
        'show_all': False
    }
    
    db = SessionLocal()
    try:
        # Call the function directly (bypassing FastAPI auth)
        import asyncio
        result = asyncio.run(search_part_number_bulk_ultra_fast(test_request, None, db, None))
        
        print(f"✅ API call successful!")
        print(f"Total parts: {result.get('total_parts', 0)}")
        print(f"Latency: {result.get('latency_ms', 0)}ms")
        print(f"Results count: {len(result.get('results', {}))}")
        
        # Show sample results
        results = result.get('results', {})
        if results:
            print(f"\n📊 Sample results:")
            for part_num, part_data in list(results.items())[:2]:
                print(f"  Part: {part_num}")
                companies = part_data.get('companies', [])
                print(f"    Matches: {len(companies)}")
                if companies:
                    match = companies[0]
                    print(f"    Company: {match.get('company_name', 'N/A')}")
                    print(f"    Price: {match.get('unit_price', 'N/A')}")
                    print(f"    Quantity: {match.get('quantity', 'N/A')}")
                print()
        else:
            print("ℹ️ No results found")
            
    except Exception as e:
        print(f"❌ API call failed: {e}")
        import traceback
        traceback.print_exc()
    finally:
        db.close()

if __name__ == "__main__":
    test_ultra_fast_api()
