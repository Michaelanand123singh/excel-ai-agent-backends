"""
Data Sync Service to keep Elasticsearch in sync with PostgreSQL
Ensures Elasticsearch has the latest data for optimal search performance
"""

import logging
from typing import Dict, Any, List, Optional
from sqlalchemy.orm import Session
from sqlalchemy import text

from app.services.search_engine.elasticsearch_client import ElasticsearchBulkSearch
from app.core.database import get_db

logger = logging.getLogger(__name__)


class DataSyncService:
    """Service to sync data between PostgreSQL and Elasticsearch"""
    
    def __init__(self):
        self.es_client = ElasticsearchBulkSearch()
    
    def sync_file_to_elasticsearch(self, file_id: int) -> bool:
        """
        Sync a specific file's data from PostgreSQL to Elasticsearch
        """
        try:
            if not self.es_client.is_available():
                logger.warning("Elasticsearch not available for sync")
                return False
            
            # Get database session
            db = next(get_db())
            
            try:
                table_name = f"ds_{file_id}"
                
                # Check if table exists
                exists = db.execute(text(f"""
                    SELECT EXISTS (
                        SELECT FROM information_schema.tables 
                        WHERE table_name = '{table_name}'
                    );
                """)).scalar()
                
                if not exists:
                    logger.error(f"Table {table_name} does not exist")
                    return False
                
                # Get all data from PostgreSQL
                logger.info(f"🔄 Syncing data from {table_name} to Elasticsearch...")
                
                # Get row count first
                count_result = db.execute(text(f"SELECT COUNT(*) FROM {table_name}")).scalar()
                total_rows = count_result or 0
                
                if total_rows == 0:
                    logger.warning(f"No data found in {table_name}")
                    return True
                
                logger.info(f"📊 Found {total_rows} rows to sync")
                
                # Create Elasticsearch index if it doesn't exist
                self.es_client.create_index(table_name, file_id)
                
                # Fetch data in batches to avoid memory issues
                batch_size = 1000
                offset = 0
                synced_rows = 0
                
                while offset < total_rows:
                    # Fetch batch of data
                    batch_data = db.execute(text(f"""
                        SELECT
                            "Potential Buyer 1",
                            "Potential Buyer 1 Contact Details",
                            "Potential Buyer 1 email id",
                            "Quantity",
                            "Unit_Price",
                            "Item_Description",
                            "part_number",
                            "UQC",
                            "Potential Buyer 2",
                            NULL as "Potential Buyer 2 Contact Details",
                            NULL as "Potential Buyer 2 email id"
                        FROM {table_name}
                        ORDER BY "part_number"
                        LIMIT {batch_size} OFFSET {offset}
                    """)).fetchall()
                    
                    if not batch_data:
                        break
                    
                    # Convert to list of dictionaries
                    batch_records = []
                    for row in batch_data:
                        record = {
                            "id": f"{file_id}_{offset + len(batch_records)}",
                            "part_number": row[6] or "",
                            "Item_Description": row[5] or "",
                            "Potential Buyer 1": row[0] or "",
                            "Potential Buyer 1 Contact Details": row[1] or "",
                            "Potential Buyer 1 email id": row[2] or "",
                            "Quantity": row[3] or 0,
                            "Unit_Price": row[4] or 0.0,
                            "UQC": row[7] or "",
                            "Potential Buyer 2": row[8] or "",
                            "Potential Buyer 2 Contact Details": row[9] or "",
                            "Potential Buyer 2 email id": row[10] or ""
                        }
                        batch_records.append(record)
                    
                    # Index batch to Elasticsearch
                    success = self.es_client.index_data(batch_records, file_id)
                    if not success:
                        logger.error(f"Failed to index batch starting at offset {offset}")
                        return False
                    
                    synced_rows += len(batch_records)
                    offset += batch_size
                    
                    logger.info(f"📈 Synced {synced_rows}/{total_rows} rows ({synced_rows/total_rows*100:.1f}%)")
                
                logger.info(f"✅ Successfully synced {synced_rows} rows from {table_name} to Elasticsearch")
                return True
                
            finally:
                db.close()
                
        except Exception as e:
            logger.error(f"❌ Failed to sync file {file_id} to Elasticsearch: {e}")
            return False
    
    def sync_all_files(self) -> Dict[str, Any]:
        """
        Sync all files from PostgreSQL to Elasticsearch
        """
        try:
            if not self.es_client.is_available():
                return {"error": "Elasticsearch not available"}
            
            # Get database session
            db = next(get_db())
            
            try:
                # Get all dataset tables
                tables_result = db.execute(text("""
                    SELECT table_name 
                    FROM information_schema.tables 
                    WHERE table_name LIKE 'ds_%'
                    ORDER BY table_name
                """)).fetchall()
                
                results = {
                    "total_files": len(tables_result),
                    "synced_files": 0,
                    "failed_files": 0,
                    "details": []
                }
                
                for (table_name,) in tables_result:
                    file_id = int(table_name.replace('ds_', ''))
                    
                    try:
                        logger.info(f"🔄 Syncing file {file_id}...")
                        success = self.sync_file_to_elasticsearch(file_id)
                        
                        if success:
                            results["synced_files"] += 1
                            results["details"].append({
                                "file_id": file_id,
                                "table_name": table_name,
                                "status": "success"
                            })
                        else:
                            results["failed_files"] += 1
                            results["details"].append({
                                "file_id": file_id,
                                "table_name": table_name,
                                "status": "failed"
                            })
                            
                    except Exception as e:
                        results["failed_files"] += 1
                        results["details"].append({
                            "file_id": file_id,
                            "table_name": table_name,
                            "status": "error",
                            "error": str(e)
                        })
                        logger.error(f"❌ Failed to sync file {file_id}: {e}")
                
                logger.info(f"🎉 Sync completed: {results['synced_files']} successful, {results['failed_files']} failed")
                return results
                
            finally:
                db.close()
                
        except Exception as e:
            logger.error(f"❌ Failed to sync all files: {e}")
            return {"error": str(e)}
    
    def get_sync_status(self) -> Dict[str, Any]:
        """
        Get the current sync status between PostgreSQL and Elasticsearch
        """
        try:
            if not self.es_client.is_available():
                return {
                    "elasticsearch_available": False,
                    "message": "Elasticsearch not available"
                }
            
            # Get Elasticsearch index stats
            es_stats = self.es_client.get_index_stats()
            
            # Get PostgreSQL table counts
            db = next(get_db())
            try:
                tables_result = db.execute(text("""
                    SELECT 
                        table_name,
                        (SELECT COUNT(*) FROM information_schema.tables t2 WHERE t2.table_name = t1.table_name) as exists
                    FROM information_schema.tables t1
                    WHERE table_name LIKE 'ds_%'
                    ORDER BY table_name
                """)).fetchall()
                
                pg_tables = []
                total_pg_rows = 0
                
                for (table_name, exists) in tables_result:
                    if exists:
                        file_id = int(table_name.replace('ds_', ''))
                        count_result = db.execute(text(f"SELECT COUNT(*) FROM {table_name}")).scalar()
                        row_count = count_result or 0
                        total_pg_rows += row_count
                        
                        pg_tables.append({
                            "file_id": file_id,
                            "table_name": table_name,
                            "row_count": row_count
                        })
                
                return {
                    "elasticsearch_available": True,
                    "elasticsearch_stats": es_stats,
                    "postgresql_tables": pg_tables,
                    "total_postgresql_rows": total_pg_rows,
                    "sync_recommended": es_stats.get("document_count", 0) < total_pg_rows
                }
                
            finally:
                db.close()
                
        except Exception as e:
            logger.error(f"❌ Failed to get sync status: {e}")
            return {
                "elasticsearch_available": False,
                "error": str(e)
            }
