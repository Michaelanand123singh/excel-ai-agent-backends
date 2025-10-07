#!/usr/bin/env python3

from app.services.search_engine.unified_search_engine import UnifiedSearchEngine
from app.core.database import get_db

def test_current_search_state():
    try:
        print("🔍 Testing Current Search State...")
        print("=" * 50)
        
        file_id = 38
        table_name = f"ds_{file_id}"
        test_part = "SMD"
        
        print(f"📋 Test Parameters:")
        print(f"   - File ID: {file_id}")
        print(f"   - Table Name: {table_name}")
        print(f"   - Test Part: {test_part}")
        print()
        
        try:
            db = next(get_db())
            search_engine = UnifiedSearchEngine(db, table_name, file_id=file_id)
            
            print(f"🔍 Search Engine Status:")
            print(f"   - Elasticsearch Available: {search_engine.es_available}")
            print(f"   - File ID: {search_engine.file_id}")
            print()
            
            # Test 1: Single Search
            print("1️⃣ Testing Single Search...")
            single_result = search_engine.search_single_part(
                part_number=test_part,
                search_mode="hybrid",
                page=1,
                page_size=1000,
                show_all=False
            )
            
            print(f"   ✅ Single Search Results:")
            print(f"      - Search Engine: {single_result.get('search_engine', 'unknown')}")
            print(f"      - Total Matches: {single_result.get('total_matches', 0)}")
            print(f"      - Companies: {len(single_result.get('companies', []))}")
            print(f"      - Latency: {single_result.get('latency_ms', 0)}ms")
            print(f"      - Message: {single_result.get('message', 'No message')}")
            
            if single_result.get('total_matches', 0) == 0:
                print("   ❌ Single search is FAILING!")
            else:
                print("   ✅ Single search is working!")
            
            print()
            
            # Test 2: Bulk Search
            print("2️⃣ Testing Bulk Search...")
            bulk_result = search_engine.search_bulk_parts(
                part_numbers=[test_part],
                search_mode="hybrid",
                page=1,
                page_size=1000,
                show_all=False
            )
            
            print(f"   ✅ Bulk Search Results:")
            print(f"      - Search Engine: {bulk_result.get('search_engine', 'unknown')}")
            print(f"      - Latency: {bulk_result.get('latency_ms', 0)}ms")
            
            # Check results for the test part
            results = bulk_result.get('results', {})
            if test_part in results:
                part_result = results[test_part]
                if isinstance(part_result, dict):
                    total_matches = part_result.get('total_matches', 0)
                    companies = len(part_result.get('companies', []))
                    print(f"      - {test_part}: {total_matches} matches, {companies} companies")
                    
                    if companies <= 10:
                        print("   ❌ Bulk search is LIMITED to 10 results!")
                    else:
                        print("   ✅ Bulk search is showing more than 10 results!")
                else:
                    print(f"      - {test_part}: ERROR - {part_result}")
            else:
                print(f"      - {test_part}: No results found")
            
            print()
            
            # Test 3: Compare Results
            print("3️⃣ Comparing Single vs Bulk Search...")
            single_matches = single_result.get('total_matches', 0)
            bulk_matches = results.get(test_part, {}).get('total_matches', 0) if isinstance(results.get(test_part), dict) else 0
            
            print(f"   - Single Search: {single_matches} matches")
            print(f"   - Bulk Search: {bulk_matches} matches")
            
            if single_matches == bulk_matches:
                print("   ✅ Single and Bulk search results are CONSISTENT!")
            else:
                print("   ❌ Single and Bulk search results are INCONSISTENT!")
            
            db.close()
        except Exception as e:
            print(f"❌ Error during testing: {e}")
            import traceback
            traceback.print_exc()
        
        print()
        print("✅ Current search state test completed!")
        
    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    test_current_search_state()
