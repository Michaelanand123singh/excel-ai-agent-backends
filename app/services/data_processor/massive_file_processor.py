"""
Massive File Processor for handling 100MB+ files with 20M+ rows
Optimized for memory efficiency and streaming processing
"""

import logging
import asyncio
from typing import Iterator, List, Dict, Any, Optional, Callable
from sqlalchemy.orm import Session
from sqlalchemy import text, MetaData
import gc
import time

from app.services.data_processor.excel_parser import iter_rows
from app.services.data_processor.schema_generator import build_table
from app.services.data_processor.data_cleaner import clean_row
from app.services.data_processor.data_validator import validate_row
from app.core.config import settings

logger = logging.getLogger(__name__)


class MassiveFileProcessor:
    """Specialized processor for massive files (100MB+, 20M+ rows)"""
    
    def __init__(self):
        self.processed_rows = 0
        self.start_time = None
        self.last_progress_time = 0
        
    def process_massive_file(self, db: Session, file_bytes: bytes, filename: str, 
                           dataset_name: str, file_id: int = None, 
                           cancel_check: Optional[Callable[[], bool]] = None) -> tuple[int, str]:
        """
        Process massive files with streaming and memory optimization
        """
        self.start_time = time.time()
        self.processed_rows = 0
        
        metadata = MetaData()
        engine = db.get_bind()
        table_name = f"ds_{dataset_name}"
        table = None
        batch_count = 0
        
        # Use streaming batch size for massive files
        batch_size = settings.STREAMING_BATCH_SIZE  # 100K rows per batch
        
        logger.info(f"🚀 Starting massive file processing: {filename}")
        logger.info(f"📊 File size: {len(file_bytes) / (1024 * 1024):.1f}MB")
        logger.info(f"📦 Batch size: {batch_size:,} rows")
        
        # Resumable processing
        already = 0
        try:
            res = db.execute(text(f"SELECT COUNT(*) FROM {table_name}"))
            already = int(res.scalar() or 0)
            if already > 0:
                logger.info(f"🔄 Resuming from row {already:,}")
        except Exception:
            already = 0
        
        def _safe_insert(rows: List[Dict]) -> List[str]:
            """Safe batch insert with retry logic for massive datasets"""
            if not rows:
                return []
            
            try:
                # Use correct bulk insert syntax (same as regular batch processor)
                if settings.DEFER_EMBEDDINGS:
                    # Faster path: no RETURNING to reduce server-side overhead
                    db.execute(table.insert(), rows)
                    inserted = []
                else:
                    result = db.execute(table.insert().returning(table.c.id), rows)
                    inserted = [str(row_id[0]) for row_id in result.fetchall()]
                
                db.commit()
                logger.info(f"✅ Inserted {len(rows)} rows successfully")
                return inserted
                    
            except Exception as e:
                logger.error(f"❌ Batch insert failed: {e}")
                db.rollback()
                
                # Try smaller batches if large batch fails
                if len(rows) > 1000:
                    logger.info("🔄 Retrying with smaller batch size...")
                    mid = len(rows) // 2
                    left_ids = _safe_insert(rows[:mid])
                    right_ids = _safe_insert(rows[mid:])
                    return left_ids + right_ids
                else:
                    raise e
        
        # Process file in streaming chunks
        logger.info(f"🔄 Starting to process {filename} with batch size {batch_size:,}")
        
        for batch in iter_rows(file_bytes, filename, chunk_size=batch_size, skip_rows=already):
            # Check for cancellation
            if cancel_check and cancel_check():
                logger.info("🛑 Processing cancelled by user")
                break
            
            # Clean and validate batch
            cleaned = [clean_row(r) for r in batch]
            valid = [r for r in cleaned if validate_row(r)]
            invalid_count = len(cleaned) - len(valid)
            
            if invalid_count > 0:
                logger.warning(f"⚠️ Skipped {invalid_count} invalid rows in batch {batch_count}")
            
            batch = valid
            
            # Create table schema on first batch
            if table is None:
                table = build_table(metadata, table_name, batch[:10])
                metadata.create_all(bind=engine)
                logger.info(f"📋 Created table schema: {table_name}")
            
            if not batch:
                logger.warning(f"⚠️ Empty batch {batch_count}, skipping")
                continue
            
            batch_count += 1
            logger.info(f"📦 Processing batch {batch_count} with {len(batch)} rows")
            
            # Insert batch
            try:
                inserted_ids = _safe_insert(batch)
                
                # Count rows correctly (same logic as regular batch processor)
                if settings.DEFER_EMBEDDINGS:
                    self.processed_rows += len(batch)
                else:
                    self.processed_rows += len(inserted_ids)
                
                # Progress logging for massive files
                self._log_progress(batch_count, file_id)
                
                # Memory cleanup every 10 batches for massive files
                if batch_count % 10 == 0:
                    gc.collect()
                
            except Exception as e:
                logger.error(f"❌ Failed to process batch {batch_count}: {e}")
                break
        
        # Final cleanup
        if table is None:
            table = build_table(metadata, table_name, [])
            metadata.create_all(bind=engine)
        
        processing_time = time.time() - self.start_time
        logger.info(f"✅ Massive file processing completed:")
        logger.info(f"📊 Processed {self.processed_rows:,} rows in {processing_time:.1f}s")
        logger.info(f"⚡ Average speed: {self.processed_rows/processing_time:,.0f} rows/second")
        
        return self.processed_rows, table_name
    
    def _log_progress(self, batch_count: int, file_id: int = None):
        """Log progress at optimized intervals for massive files"""
        current_time = time.time()
        
        # Log every 20 batches for massive files (less frequent)
        if batch_count % 20 == 0 or (current_time - self.last_progress_time) > 30:
            elapsed = current_time - self.start_time
            speed = self.processed_rows / elapsed if elapsed > 0 else 0
            
            logger.info(f"📈 Batch {batch_count}: {self.processed_rows:,} rows processed "
                       f"({speed:,.0f} rows/sec)")
            
            # Send WebSocket update for massive files (less frequent)
            if file_id and batch_count % 50 == 0:  # Every 50 batches
                try:
                    from app.core.websocket_manager import websocket_manager
                    message = {
                        "type": "massive_file_progress",
                        "file_id": file_id,
                        "processed_rows": self.processed_rows,
                        "current_batch": batch_count,
                        "processing_stage": "massive_file_processing",
                        "speed_rows_per_sec": int(speed)
                    }
                    
                    loop = None
                    try:
                        loop = asyncio.get_running_loop()
                    except RuntimeError:
                        loop = None
                    
                    if loop and loop.is_running():
                        loop.create_task(websocket_manager.send_progress(str(file_id), message))
                    else:
                        asyncio.run(websocket_manager.send_progress(str(file_id), message))
                except Exception:
                    pass
            
            self.last_progress_time = current_time


def process_massive_file_in_batches(db: Session, file_bytes: bytes, filename: str, 
                                  dataset_name: str, file_id: int = None, 
                                  cancel_check: Optional[Callable[[], bool]] = None) -> tuple[int, str]:
    """
    Main entry point for processing massive files
    """
    processor = MassiveFileProcessor()
    return processor.process_massive_file(db, file_bytes, filename, dataset_name, file_id, cancel_check)
