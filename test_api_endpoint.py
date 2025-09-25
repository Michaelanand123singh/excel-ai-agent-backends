#!/usr/bin/env python3
"""
Test the Elasticsearch API endpoint
"""

import sys
import asyncio
from pathlib import Path

# Add the app directory to the Python path
sys.path.insert(0, str(Path(__file__).parent))

from app.api.v1.endpoints.query_elasticsearch import search_part_number_bulk_elasticsearch
from app.core.database import SessionLocal

async def test_api():
    print('✅ Testing Elasticsearch API endpoint...')
    
    # Test request
    req = {
        'file_id': 39,
        'part_numbers': ['R536446', 'R536444', 'FOC IQ8HC 72 M INT'],
        'page': 1,
        'page_size': 50,
        'show_all': False,
        'search_mode': 'hybrid'
    }
    
    db = SessionLocal()
    try:
        result = await search_part_number_bulk_elasticsearch(req, db, None)
        print(f'✅ API call successful!')
        print(f'📊 Total parts: {result.get("total_parts", 0)}')
        print(f'📊 Results count: {len(result.get("results", {}))}')
        print(f'🔍 Search engine: {result.get("search_engine", "unknown")}')
        print(f'⏱️  Total time: {result.get("total_time_ms", 0):.2f}ms')
        
        # Show sample results
        results = result.get('results', {})
        if results:
            sample_part = list(results.keys())[0]
            companies = results[sample_part].get('companies', [])
            print(f'📋 Sample: {sample_part} -> {len(companies)} matches')
            if companies:
                print(f'    Company: {companies[0].get("company_name", "N/A")}')
                print(f'    Price: {companies[0].get("unit_price", "N/A")}')
        
    except Exception as e:
        print(f'❌ API test failed: {e}')
        import traceback
        traceback.print_exc()
    finally:
        db.close()

if __name__ == "__main__":
    asyncio.run(test_api())

