"""
Ultra-Fast Index Manager for Bulk Search Optimization
Creates specialized indexes for 10K+ part number searches
"""

from sqlalchemy.orm import Session
from sqlalchemy import text
import logging
import time

logger = logging.getLogger(__name__)


def create_ultra_fast_indexes(db: Session, table_name: str) -> None:
    """
    Create ultra-optimized indexes for bulk search performance
    Target: Support 10K part number searches in 5 seconds
    """
    start_time = time.perf_counter()
    
    try:
        # Ensure required extensions
        db.execute(text("CREATE EXTENSION IF NOT EXISTS pg_trgm"))
        db.execute(text("CREATE EXTENSION IF NOT EXISTS btree_gin"))
        
        # 1. PRIMARY PERFORMANCE INDEXES
        
        # B-tree index on part_number (most critical)
        db.execute(text(f"""
            CREATE INDEX IF NOT EXISTS idx_{table_name}_part_number_ultra 
            ON {table_name} ("part_number")
        """))
        
        # GIN index on part_number for array operations
        db.execute(text(f"""
            CREATE INDEX IF NOT EXISTS idx_{table_name}_part_number_gin 
            ON {table_name} USING GIN ("part_number" gin_trgm_ops)
        """))
        
        # 2. DESCRIPTION SEARCH INDEXES
        
        # Trigram GIN on Item_Description (case-insensitive)
        db.execute(text(f"""
            CREATE INDEX IF NOT EXISTS idx_{table_name}_item_desc_trgm_ultra 
            ON {table_name} USING GIN (lower("Item_Description") gin_trgm_ops)
        """))
        
        # B-tree on Item_Description for exact matches
        db.execute(text(f"""
            CREATE INDEX IF NOT EXISTS idx_{table_name}_item_desc_btree 
            ON {table_name} ("Item_Description")
        """))
        
        # 3. PRICE AND QUANTITY INDEXES
        
        # Composite index for price-based ordering
        db.execute(text(f"""
            CREATE INDEX IF NOT EXISTS idx_{table_name}_price_quantity 
            ON {table_name} ("Unit_Price", "Quantity")
        """))
        
        # 4. NORMALIZED PART NUMBER INDEXES
        
        # Index for separator-stripped part_number
        db.execute(text(f"""
            CREATE INDEX IF NOT EXISTS idx_{table_name}_pn_no_seps_ultra 
            ON {table_name} (
                lower(replace(replace(replace(replace(replace(replace(replace(replace("part_number", '-', ''), '/', ''), ',', ''), '*', ''), '&', ''), '~', ''), '.', ''), '%', ''))
            )
        """))
        
        # Index for alphanumeric-only part_number
        db.execute(text(f"""
            CREATE INDEX IF NOT EXISTS idx_{table_name}_pn_alnum_ultra 
            ON {table_name} (
                lower(regexp_replace("part_number", '[^a-zA-Z0-9]+', '', 'g'))
            )
        """))
        
        # 5. COMPOSITE INDEXES FOR BULK SEARCH
        
        # Multi-column index for common bulk search patterns
        db.execute(text(f"""
            CREATE INDEX IF NOT EXISTS idx_{table_name}_bulk_search 
            ON {table_name} ("part_number", "Unit_Price", "Quantity")
        """))
        
        # 6. SIMILARITY SEARCH INDEXES
        
        # Specialized index for similarity operations (removed - similarity function returns real, not text)
        
        # 7. COMPANY AND CONTACT INDEXES
        
        # Index on company names for faster joins
        db.execute(text(f"""
            CREATE INDEX IF NOT EXISTS idx_{table_name}_company 
            ON {table_name} ("Potential Buyer 1")
        """))
        
        # 8. PARTIAL INDEXES FOR COMMON FILTERS
        
        # Partial index for non-zero prices
        db.execute(text(f"""
            CREATE INDEX IF NOT EXISTS idx_{table_name}_price_nonzero 
            ON {table_name} ("Unit_Price") 
            WHERE "Unit_Price" > 0
        """))
        
        # Partial index for non-zero quantities
        db.execute(text(f"""
            CREATE INDEX IF NOT EXISTS idx_{table_name}_quantity_nonzero 
            ON {table_name} ("Quantity") 
            WHERE "Quantity" > 0
        """))
        
        # 9. COVERING INDEXES FOR COMMON QUERIES
        
        # Covering index for part number + price + quantity
        db.execute(text(f"""
            CREATE INDEX IF NOT EXISTS idx_{table_name}_covering_part_price 
            ON {table_name} ("part_number") 
            INCLUDE ("Unit_Price", "Quantity", "Item_Description")
        """))
        
        # 10. STATISTICS UPDATE
        
        # Update table statistics for better query planning
        db.execute(text(f"ANALYZE {table_name}"))
        
        # Update statistics for all indexes
        db.execute(text(f"""
            SELECT schemaname, tablename, attname, n_distinct, correlation 
            FROM pg_stats 
            WHERE tablename = '{table_name}'
        """))
        
        creation_time = (time.perf_counter() - start_time) * 1000
        logger.info(f"Created ultra-fast indexes for table {table_name} in {creation_time:.2f}ms")
        
        # Verify index creation
        verify_indexes(db, table_name)
        
    except Exception as e:
        db.rollback()
        logger.error(f"Failed to create ultra-fast indexes for {table_name}: {e}")
        raise


def verify_indexes(db: Session, table_name: str) -> None:
    """Verify that all required indexes were created successfully"""
    
    try:
        # Check for critical indexes
        critical_indexes = [
            f"idx_{table_name}_part_number_ultra",
            f"idx_{table_name}_item_desc_trgm_ultra",
            f"idx_{table_name}_bulk_search",
            f"idx_{table_name}_covering_part_price"
        ]
        
        for index_name in critical_indexes:
            result = db.execute(text(f"""
                SELECT EXISTS (
                    SELECT FROM pg_indexes 
                    WHERE indexname = '{index_name}'
                )
            """)).scalar()
            
            if not result:
                logger.warning(f"Critical index {index_name} not found")
            else:
                logger.info(f"✓ Index {index_name} verified")
        
        # Get index usage statistics
        usage_stats = db.execute(text(f"""
            SELECT 
                schemaname,
                tablename,
                indexname,
                idx_scan,
                idx_tup_read,
                idx_tup_fetch
            FROM pg_stat_user_indexes 
            WHERE tablename = '{table_name}'
            ORDER BY idx_scan DESC
        """)).fetchall()
        
        logger.info(f"Index usage statistics for {table_name}:")
        for stat in usage_stats:
            logger.info(f"  {stat[2]}: {stat[3]} scans, {stat[4]} tuples read")
            
    except Exception as e:
        logger.warning(f"Failed to verify indexes: {e}")


def optimize_table_for_bulk_search(db: Session, table_name: str) -> None:
    """
    Apply additional optimizations for bulk search performance
    """
    try:
        # 1. Set table storage parameters for better performance
        db.execute(text(f"""
            ALTER TABLE {table_name} SET (
                fillfactor = 90,
                autovacuum_vacuum_scale_factor = 0.1,
                autovacuum_analyze_scale_factor = 0.05
            )
        """))
        
        # 2. Update table statistics
        db.execute(text(f"ANALYZE {table_name}"))
        
        # 3. Set work_mem for this session (if possible)
        db.execute(text("SET work_mem = '256MB'"))
        
        # 4. Enable parallel query execution
        db.execute(text("SET max_parallel_workers_per_gather = 4"))
        
        # 5. Set effective cache size
        db.execute(text("SET effective_cache_size = '1GB'"))
        
        logger.info(f"Applied bulk search optimizations to {table_name}")
        
    except Exception as e:
        logger.warning(f"Failed to apply bulk search optimizations: {e}")


def get_index_performance_stats(db: Session, table_name: str) -> dict:
    """Get performance statistics for indexes"""
    
    try:
        # Get index usage statistics
        stats = db.execute(text(f"""
            SELECT 
                indexrelname,
                idx_scan,
                idx_tup_read,
                idx_tup_fetch,
                pg_size_pretty(pg_relation_size(indexrelid)) as index_size
            FROM pg_stat_user_indexes 
            WHERE relname = '{table_name}'
            ORDER BY idx_scan DESC
        """)).fetchall()
        
        # Get table size
        table_size = db.execute(text(f"""
            SELECT pg_size_pretty(pg_total_relation_size('{table_name}'))
        """)).scalar()
        
        return {
            "table_name": table_name,
            "table_size": table_size,
            "indexes": [
                {
                    "name": stat[0],
                    "scans": stat[1],
                    "tuples_read": stat[2],
                    "tuples_fetched": stat[3],
                    "size": stat[4]
                }
                for stat in stats
            ]
        }
        
    except Exception as e:
        logger.error(f"Failed to get index performance stats: {e}")
        return {"error": str(e)}


def cleanup_old_indexes(db: Session, table_name: str) -> None:
    """Remove old, unused indexes to improve performance"""
    
    try:
        # Find unused indexes (not used in last 1000 queries)
        unused_indexes = db.execute(text(f"""
            SELECT indexname
            FROM pg_stat_user_indexes 
            WHERE tablename = '{table_name}' 
            AND idx_scan < 10
            AND indexname NOT LIKE '%_pkey'
        """)).fetchall()
        
        for index in unused_indexes:
            index_name = index[0]
            try:
                db.execute(text(f"DROP INDEX CONCURRENTLY IF EXISTS {index_name}"))
                logger.info(f"Dropped unused index: {index_name}")
            except Exception as e:
                logger.warning(f"Failed to drop index {index_name}: {e}")
        
    except Exception as e:
        logger.warning(f"Failed to cleanup old indexes: {e}")
