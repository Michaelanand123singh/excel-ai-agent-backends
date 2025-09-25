#!/usr/bin/env python3
"""
Data synchronization between PostgreSQL and Elasticsearch
"""

import logging
from typing import List, Dict, Any
from sqlalchemy import text
from app.core.database import SessionLocal
from app.services.search_engine.elasticsearch_client import ElasticsearchBulkSearch

logger = logging.getLogger(__name__)

class DataSyncService:
    """Synchronize data between PostgreSQL and Elasticsearch"""
    
    def __init__(self):
        self.es_client = ElasticsearchBulkSearch()
    
    def sync_file_to_elasticsearch(self, file_id: int) -> bool:
        """Sync a file's data from PostgreSQL to Elasticsearch"""
        if not self.es_client.is_available():
            logger.warning("Elasticsearch not available, skipping sync")
            return False
        
        try:
            db = SessionLocal()
            
            # Check if file exists
            file_result = db.execute(text("""
                SELECT id FROM file 
                WHERE id = :file_id
            """), {"file_id": file_id}).fetchone()
            
            if not file_result:
                logger.error(f"File {file_id} not found")
                return False
            
            # Generate table name (ds_{file_id})
            table_name = f"ds_{file_id}"
            
            # Create Elasticsearch index
            if not self.es_client.create_index(table_name, file_id):
                logger.error("Failed to create Elasticsearch index")
                return False
            
            # Get all data from the table
            data_query = f"""
                SELECT 
                    id,
                    "part_number",
                    "Item_Description",
                    "Potential Buyer 1",
                    "Potential Buyer 1 Contact Details",
                    "Potential Buyer 1 email id",
                    "Quantity",
                    "Unit_Price",
                    "UQC",
                    "Potential Buyer 2"
                FROM {table_name}
                ORDER BY id
            """
            
            data = db.execute(text(data_query)).fetchall()
            
            # Convert to list of dictionaries
            data_list = []
            for row in data:
                data_list.append({
                    "id": row[0],
                    "part_number": row[1],
                    "Item_Description": row[2],
                    "Potential Buyer 1": row[3],
                    "Potential Buyer 1 Contact Details": row[4],
                    "Potential Buyer 1 email id": row[5],
                    "Quantity": row[6],
                    "Unit_Price": row[7],
                    "UQC": row[8],
                    "Potential Buyer 2": row[9]
                })
            
            # Index data to Elasticsearch
            success = self.es_client.index_data(data_list, file_id)
            
            if success:
                logger.info(f"✅ Successfully synced {len(data_list)} records for file {file_id}")
            else:
                logger.error(f"❌ Failed to sync data for file {file_id}")
            
            return success
            
        except Exception as e:
            logger.error(f"❌ Data sync failed for file {file_id}: {e}")
            return False
        finally:
            db.close()
    
    def sync_all_files(self) -> Dict[str, Any]:
        """Sync all files to Elasticsearch"""
        if not self.es_client.is_available():
            return {"error": "Elasticsearch not available"}
        
        try:
            db = SessionLocal()
            
            # Get all files
            files_result = db.execute(text("""
                SELECT id FROM file 
                ORDER BY id
            """)).fetchall()
            
            sync_results = {
                "total_files": len(files_result),
                "successful_syncs": 0,
                "failed_syncs": 0,
                "errors": []
            }
            
            for (file_id,) in files_result:
                try:
                    if self.sync_file_to_elasticsearch(file_id):
                        sync_results["successful_syncs"] += 1
                        logger.info(f"✅ Synced file {file_id} (ds_{file_id})")
                    else:
                        sync_results["failed_syncs"] += 1
                        sync_results["errors"].append(f"Failed to sync file {file_id}")
                        logger.error(f"❌ Failed to sync file {file_id}")
                except Exception as e:
                    sync_results["failed_syncs"] += 1
                    sync_results["errors"].append(f"Error syncing file {file_id}: {str(e)}")
                    logger.error(f"❌ Error syncing file {file_id}: {e}")
            
            return sync_results
            
        except Exception as e:
            logger.error(f"❌ Failed to sync all files: {e}")
            return {"error": str(e)}
        finally:
            db.close()
    
    def get_sync_status(self) -> Dict[str, Any]:
        """Get synchronization status"""
        if not self.es_client.is_available():
            return {"elasticsearch_available": False}
        
        try:
            db = SessionLocal()
            
            # Get PostgreSQL file count
            pg_count = db.execute(text("SELECT COUNT(*) FROM file")).fetchone()[0]
            
            # Get Elasticsearch document count
            es_stats = self.es_client.get_index_stats()
            
            return {
                "elasticsearch_available": True,
                "postgresql_files": pg_count,
                "elasticsearch_documents": es_stats.get("document_count", 0),
                "elasticsearch_index_size": es_stats.get("index_size", 0),
                "sync_status": "healthy" if es_stats.get("document_count", 0) > 0 else "empty"
            }
            
        except Exception as e:
            return {"error": str(e)}
        finally:
            db.close()
