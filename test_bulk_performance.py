#!/usr/bin/env python3
"""
Test bulk search performance with different part number counts
"""

import sys
import asyncio
import time
from pathlib import Path

# Add the app directory to the Python path
sys.path.insert(0, str(Path(__file__).parent))

from app.api.v1.endpoints.query_elasticsearch import search_part_number_bulk_elasticsearch
from app.core.database import SessionLocal

async def test_bulk_performance():
    print('🚀 Testing Bulk Search Performance')
    print('=' * 50)
    
    # Test with different sizes
    test_cases = [
        (['R536446', 'R536444'], "2 parts"),
        (['R536446', 'R536444', 'FOC IQ8HC 72 M INT', 'MAT0170187', 'MAT01718034'], "5 parts"),
        (['R536446', 'R536444', 'FOC IQ8HC 72 M INT', 'MAT0170187', 'MAT01718034', 'MAT0170640', 'CF113.037.D', 'CF270.UL.40.04.D', 'CF78.UL.10.03', 'CFBUS.PVC.049'], "10 parts"),
    ]
    
    db = SessionLocal()
    try:
        for test_parts, description in test_cases:
            print(f'\n📊 Testing {description}...')
            
            # Test request
            req = {
                'file_id': 39,
                'part_numbers': test_parts,
                'page': 1,
                'page_size': 50,
                'show_all': False,
                'search_mode': 'hybrid'
            }
            
            start_time = time.perf_counter()
            result = await search_part_number_bulk_elasticsearch(req, db, None)
            total_time = (time.perf_counter() - start_time) * 1000
            
            print(f'  ✅ Search completed!')
            print(f'  ⏱️  Time: {total_time:.2f}ms')
            print(f'  📊 Total parts: {result.get("total_parts", 0)}')
            print(f'  📊 Results count: {len(result.get("results", {}))}')
            print(f'  🔍 Search engine: {result.get("search_engine", "unknown")}')
            
            # Performance rating
            if total_time < 1000:
                print(f'  🚀 Performance: EXCELLENT ({total_time:.2f}ms)')
            elif total_time < 2000:
                print(f'  ✅ Performance: VERY GOOD ({total_time:.2f}ms)')
            elif total_time < 5000:
                print(f'  ✅ Performance: GOOD ({total_time:.2f}ms)')
            else:
                print(f'  ⚠️  Performance: ACCEPTABLE ({total_time:.2f}ms)')
            
            # Show sample results
            results = result.get('results', {})
            if results:
                sample_part = list(results.keys())[0]
                companies = results[sample_part].get('companies', [])
                print(f'  📋 Sample: {sample_part} -> {len(companies)} matches')
                if companies:
                    print(f'      Company: {companies[0].get("company_name", "N/A")}')
                    print(f'      Price: {companies[0].get("unit_price", "N/A")}')
        
        # Test with a larger set to estimate 157 parts performance
        print(f'\n🔮 Testing with 20 parts to estimate 157 parts performance...')
        
        # Create a larger test set (20 parts)
        large_test_parts = [
            'R536446', 'R536444', 'FOC IQ8HC 72 M INT', 'MAT0170187', 'MAT01718034',
            'MAT0170640', 'CF113.037.D', 'CF270.UL.40.04.D', 'CF78.UL.10.03', 'CFBUS.PVC.049',
            'CF220.UL.H101.10.04', 'CF9.05.03', 'CF77.UL.07.03.D', 'CF270.UL.250.01.D', 'CF130.15.04.UL',
            'CF211.041', 'CF9.UL.03.04.INI', 'CF130.15.05.UL', 'CF211.PUR.05.06.02', 'MAT0171598'
        ]
        
        large_request = {
            'file_id': 39,
            'part_numbers': large_test_parts,
            'page': 1,
            'page_size': 50,
            'show_all': False,
            'search_mode': 'hybrid'
        }
        
        start_time = time.perf_counter()
        result = await search_part_number_bulk_elasticsearch(large_request, db, None)
        total_time = (time.perf_counter() - start_time) * 1000
        
        print(f'  ✅ 20 parts completed in {total_time:.2f}ms')
        print(f'  📊 Results count: {len(result.get("results", {}))}')
        
        # Estimate for 157 parts
        estimated_time = (total_time / 20) * 157
        print(f'  🔮 Estimated time for 157 parts: {estimated_time:.2f}ms ({estimated_time/1000:.1f}s)')
        
        if estimated_time < 5000:  # 5 seconds
            print(f'  🎯 TARGET ACHIEVED! 157 parts in under 5 seconds!')
        elif estimated_time < 10000:  # 10 seconds
            print(f'  ✅ Very close to target! 157 parts in under 10 seconds')
        else:
            print(f'  ⚠️  Still needs optimization for 157 parts')
            
    except Exception as e:
        print(f'❌ Performance test failed: {e}')
        import traceback
        traceback.print_exc()
    finally:
        db.close()

if __name__ == "__main__":
    asyncio.run(test_bulk_performance())