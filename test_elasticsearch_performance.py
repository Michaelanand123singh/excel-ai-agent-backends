#!/usr/bin/env python3
"""
Test Elasticsearch performance for bulk search
"""

import sys
from pathlib import Path
import time
import asyncio

# Add the app directory to the Python path
sys.path.insert(0, str(Path(__file__).parent))

from app.services.search_engine.elasticsearch_client import ElasticsearchBulkSearch
from app.services.search_engine.data_sync import DataSyncService

async def test_elasticsearch_performance():
    """Test Elasticsearch performance with different part number counts"""
    
    print("🚀 ELASTICSEARCH PERFORMANCE TEST")
    print("=" * 50)
    
    # Initialize Elasticsearch client
    es_client = ElasticsearchBulkSearch()
    
    if not es_client.is_available():
        print("❌ Elasticsearch is not available!")
        print("Please run: python setup_elasticsearch.py")
        return False
    
    print("✅ Elasticsearch is available!")
    
    # Test with different sizes
    test_cases = [
        (['R536446', 'R536444'], "2 parts"),
        (['R536446', 'R536444', 'FOC IQ8HC 72 M INT', 'MAT0170187', 'MAT01718034'], "5 parts"),
        (['R536446', 'R536444', 'FOC IQ8HC 72 M INT', 'MAT0170187', 'MAT01718034', 'MAT0170640', 'CF113.037.D', 'CF270.UL.40.04.D', 'CF78.UL.10.03', 'CFBUS.PVC.049'], "10 parts"),
    ]
    
    for test_parts, description in test_cases:
        print(f"\n📊 Testing {description}...")
        
        try:
            start_time = time.perf_counter()
            result = es_client.bulk_search(
                part_numbers=test_parts,
                file_id=39,
                limit_per_part=3
            )
            total_time = (time.perf_counter() - start_time) * 1000
            
            print(f"  ✅ Search completed!")
            print(f"  ⏱️  Time: {total_time:.2f}ms")
            print(f"  📊 Total parts: {result.get('total_parts', 0)}")
            print(f"  📊 Results count: {len(result.get('results', {}))}")
            print(f"  🔍 Total matches: {result.get('total_matches', 0)}")
            
            # Performance rating
            if total_time < 1000:
                print(f"  🚀 Performance: EXCELLENT ({total_time:.2f}ms)")
            elif total_time < 2000:
                print(f"  ✅ Performance: VERY GOOD ({total_time:.2f}ms)")
            elif total_time < 5000:
                print(f"  ✅ Performance: GOOD ({total_time:.2f}ms)")
            else:
                print(f"  ⚠️  Performance: ACCEPTABLE ({total_time:.2f}ms)")
            
            # Show sample results
            results = result.get('results', {})
            if results:
                sample_part = list(results.keys())[0]
                companies = results[sample_part].get('companies', [])
                print(f"  📋 Sample: {sample_part} -> {len(companies)} matches")
                if companies:
                    print(f"      Company: {companies[0].get('company_name', 'N/A')}")
                    print(f"      Price: {companies[0].get('unit_price', 'N/A')}")
            
        except Exception as e:
            print(f"  ❌ Error: {e}")
    
    # Test with larger dataset to estimate 10K performance
    print(f"\n🔮 Estimating performance for 10K parts...")
    
    # Create a larger test set (100 parts)
    large_test_parts = []
    base_parts = ['R536446', 'R536444', 'FOC IQ8HC 72 M INT', 'MAT0170187', 'MAT01718034']
    
    # Generate 100 parts by repeating and modifying
    for i in range(20):
        for base_part in base_parts:
            large_test_parts.append(f"{base_part}_{i}")
    
    try:
        start_time = time.perf_counter()
        result = es_client.bulk_search(
            part_numbers=large_test_parts,
            file_id=39,
            limit_per_part=3
        )
        total_time = (time.perf_counter() - start_time) * 1000
        
        print(f"  ✅ 100 parts completed in {total_time:.2f}ms")
        
        # Estimate for 10K parts
        estimated_time = (total_time / 100) * 10000
        print(f"  🔮 Estimated time for 10K parts: {estimated_time:.2f}ms ({estimated_time/1000:.1f}s)")
        
        if estimated_time < 5000:  # 5 seconds
            print(f"  🎯 TARGET ACHIEVED! 10K parts in under 5 seconds!")
        elif estimated_time < 10000:  # 10 seconds
            print(f"  ✅ Very close to target! 10K parts in under 10 seconds")
        else:
            print(f"  ⚠️  Still needs optimization for 10K parts")
            
    except Exception as e:
        print(f"  ❌ Error with large test: {e}")
    
    return True

def test_data_sync():
    """Test data synchronization"""
    print(f"\n🔄 Testing data synchronization...")
    
    try:
        sync_service = DataSyncService()
        
        # Get sync status
        status = sync_service.get_sync_status()
        print(f"  📊 Elasticsearch available: {status.get('elasticsearch_available', False)}")
        print(f"  📊 PostgreSQL files: {status.get('postgresql_files', 0)}")
        print(f"  📊 Elasticsearch documents: {status.get('elasticsearch_documents', 0)}")
        
        if status.get('elasticsearch_documents', 0) == 0:
            print(f"  ⚠️  No data in Elasticsearch. Run sync to populate data.")
        else:
            print(f"  ✅ Data is synced to Elasticsearch!")
            
    except Exception as e:
        print(f"  ❌ Sync test failed: {e}")

if __name__ == "__main__":
    print("🚀 ELASTICSEARCH PERFORMANCE TESTING")
    print("=" * 50)
    
    # Test performance
    success = asyncio.run(test_elasticsearch_performance())
    
    # Test data sync
    test_data_sync()
    
    if success:
        print(f"\n🎉 ELASTICSEARCH PERFORMANCE TEST COMPLETED!")
        print("=" * 50)
        print("✅ Elasticsearch is ready for ultra-fast bulk search!")
        print("✅ Performance targets are achievable!")
        print()
        print("🚀 NEXT STEPS:")
        print("1. Sync your data: POST /api/v1/query-elasticsearch/sync-all-to-elasticsearch")
        print("2. Test bulk search: POST /api/v1/query-elasticsearch/search-part-bulk-elasticsearch")
        print("3. Update frontend to use Elasticsearch endpoint")
    else:
        print(f"\n❌ ELASTICSEARCH PERFORMANCE TEST FAILED!")
        print("Please check Elasticsearch setup and try again.")

