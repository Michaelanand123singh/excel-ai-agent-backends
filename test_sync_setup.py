#!/usr/bin/env python3

from app.services.search_engine.data_sync_service import DataSyncService
from app.core.database import get_db

def test_elasticsearch_sync_setup():
    try:
        print("🔍 Testing Elasticsearch Sync Setup...")
        print("=" * 50)
        
        try:
            db = next(get_db())
            sync_service = DataSyncService()
            
            print("📋 Sync Service Status:")
            status = sync_service.get_sync_status()
            print(f"   - Elasticsearch Available: {status.get('elasticsearch_available', False)}")
            print(f"   - PostgreSQL Tables: {len(status.get('postgresql_tables', []))}")
            print(f"   - Sync Recommended: {status.get('sync_recommended', False)}")
            
            if status.get('elasticsearch_available', False):
                print("✅ Elasticsearch is available!")
                
                # Check if there are any tables that need syncing
                tables = status.get('postgresql_tables', [])
                if tables:
                    print(f"\n📊 Available Tables:")
                    for table in tables:
                        file_id = table.get('file_id', 'N/A')
                        table_name = table.get('table_name', 'N/A')
                        row_count = table.get('row_count', 0)
                        print(f"   - File ID {file_id}: {table_name} ({row_count:,} rows)")
                    
                    # Test sync for file_id 38
                    print(f"\n🔄 Testing Sync for File ID 38...")
                    try:
                        sync_result = sync_service.sync_file_to_elasticsearch(38)
                        print(f"   - Sync Result: {sync_result}")
                        
                        if sync_result:
                            print("✅ Sync completed successfully!")
                        else:
                            print("❌ Sync failed!")
                            
                    except Exception as e:
                        print(f"❌ Sync Error: {e}")
                else:
                    print("⚠️ No PostgreSQL tables found")
            else:
                print("❌ Elasticsearch is not available!")
                es_stats = status.get('elasticsearch_stats', {})
                if 'error' in es_stats:
                    print(f"   - Error: {es_stats['error']}")
            
            db.close()
        except Exception as e:
            print(f"❌ Error: {e}")
            import traceback
            traceback.print_exc()
        
        print()
        print("✅ Elasticsearch sync setup test completed!")
        
    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    test_elasticsearch_sync_setup()
