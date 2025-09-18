from sqlalchemy.orm import Session
from sqlalchemy import text
import logging

logger = logging.getLogger(__name__)


def create_search_indexes(db: Session, table_name: str) -> None:
    """Create targeted indexes for very large datasets (>500k rows)."""
    try:
        # Ensure pg_trgm for trigram GIN
        try:
            db.execute(text("CREATE EXTENSION IF NOT EXISTS pg_trgm"))
        except Exception as e:
            logger.warning(f"pg_trgm extension setup failed or not permitted: {e}")

        # B-tree on key filter columns
        db.execute(text(f"CREATE INDEX IF NOT EXISTS idx_{table_name}_part_number_btree ON {table_name} (\"part_number\")"))
        db.execute(text(f"CREATE INDEX IF NOT EXISTS idx_{table_name}_quantity_btree ON {table_name} (\"Quantity\")"))
        db.execute(text(f"CREATE INDEX IF NOT EXISTS idx_{table_name}_unit_price_btree ON {table_name} (\"Unit_Price\")"))

        # Trigram GIN on Item_Description (case-insensitive)
        db.execute(text(f"CREATE INDEX IF NOT EXISTS idx_{table_name}_item_desc_trgm ON {table_name} USING GIN (lower(\"Item_Description\") gin_trgm_ops)"))

        db.commit()
        logger.info(f"Created large-scale search indexes for table {table_name}")
    except Exception as e:
        db.rollback()
        logger.error(f"Failed to create indexes for table {table_name}: {e}")


def drop_search_indexes(db: Session, table_name: str) -> None:
    """Drop all search indexes for a table."""
    try:
        # Get all indexes for the table
        indexes_result = db.execute(text(f"""
            SELECT indexname 
            FROM pg_indexes 
            WHERE tablename = '{table_name}' 
            AND indexname LIKE 'idx_{table_name}_%'
        """))
        
        indexes = [row[0] for row in indexes_result.fetchall()]
        
        for index_name in indexes:
            try:
                db.execute(text(f"DROP INDEX IF EXISTS {index_name}"))
                logger.info(f"Dropped index {index_name}")
            except Exception as e:
                logger.warning(f"Failed to drop index {index_name}: {e}")
        
        db.commit()
        logger.info(f"Successfully dropped search indexes for table {table_name}")
        
    except Exception as e:
        db.rollback()
        logger.error(f"Failed to drop indexes for table {table_name}: {e}")
