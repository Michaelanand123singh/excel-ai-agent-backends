#!/usr/bin/env python3
"""
Test the optimized ultra-fast bulk search
"""

import sys
from pathlib import Path
import time

# Add the app directory to the Python path
sys.path.insert(0, str(Path(__file__).parent))

from sqlalchemy import text
from app.core.database import SessionLocal
from app.api.v1.endpoints.query_optimized import search_part_number_bulk_ultra_fast
import asyncio

async def test_optimized_ultra_fast():
    """Test the optimized ultra-fast bulk search"""
    
    print("🚀 Testing Optimized Ultra-Fast Bulk Search")
    print("=" * 60)
    
    # Test with different sizes
    test_cases = [
        (['R536446', 'R536444'], "2 parts"),
        (['R536446', 'R536444', 'FOC IQ8HC 72 M INT', 'MAT0170187', 'MAT01718034'], "5 parts"),
        (['R536446', 'R536444', 'FOC IQ8HC 72 M INT', 'MAT0170187', 'MAT01718034', 'MAT0170640', 'CF113.037.D', 'CF270.UL.40.04.D', 'CF78.UL.10.03', 'CFBUS.PVC.049'], "10 parts"),
    ]
    
    for test_parts, description in test_cases:
        print(f"\n📊 Testing {description}...")
        
        # Create test request
        test_request = {
            'file_id': 39,
            'part_numbers': test_parts,
            'search_mode': 'hybrid',
            'page': 1,
            'page_size': 50,
            'show_all': False
        }
        
        db = SessionLocal()
        try:
            start_time = time.perf_counter()
            result = await search_part_number_bulk_ultra_fast(test_request, None, db, None)
            total_time = (time.perf_counter() - start_time) * 1000
            
            print(f"  ✅ API call successful!")
            print(f"  ⏱️  Total time: {total_time:.2f}ms")
            print(f"  📊 Total parts: {result.get('total_parts', 0)}")
            print(f"  📊 Results count: {len(result.get('results', {}))}")
            print(f"  🔍 Latency: {result.get('latency_ms', 0)}ms")
            
            # Show sample results
            results = result.get('results', {})
            if results:
                sample_part = list(results.keys())[0]
                companies = results[sample_part].get('companies', [])
                print(f"  📋 Sample: {sample_part} -> {len(companies)} matches")
                if companies:
                    print(f"      Company: {companies[0].get('company_name', 'N/A')}")
                    print(f"      Price: {companies[0].get('unit_price', 'N/A')}")
            
            # Check if it's fast enough
            if total_time > 5000:  # 5 seconds
                print(f"  ⚠️  WARNING: Still taking too long ({total_time:.2f}ms)")
            else:
                print(f"  ✅ Performance: EXCELLENT ({total_time:.2f}ms)")
                
        except Exception as e:
            print(f"  ❌ Error: {e}")
        finally:
            db.close()
    
    # Test with a larger set to estimate 157 parts performance
    print(f"\n🔮 Estimating performance for 157 parts...")
    
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
        'search_mode': 'hybrid',
        'page': 1,
        'page_size': 50,
        'show_all': False
    }
    
    db = SessionLocal()
    try:
        start_time = time.perf_counter()
        result = await search_part_number_bulk_ultra_fast(large_request, None, db, None)
        total_time = (time.perf_counter() - start_time) * 1000
        
        print(f"  ✅ 20 parts completed in {total_time:.2f}ms")
        
        # Estimate for 157 parts
        estimated_time = (total_time / 20) * 157
        print(f"  🔮 Estimated time for 157 parts: {estimated_time:.2f}ms ({estimated_time/1000:.1f}s)")
        
        if estimated_time < 30000:  # 30 seconds
            print(f"  ✅ Should complete within timeout!")
        else:
            print(f"  ⚠️  May still timeout, but much better than before")
            
    except Exception as e:
        print(f"  ❌ Error with large test: {e}")
    finally:
        db.close()

if __name__ == "__main__":
    asyncio.run(test_optimized_ultra_fast())

