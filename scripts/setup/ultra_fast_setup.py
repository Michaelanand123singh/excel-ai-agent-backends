#!/usr/bin/env python3
"""
Ultra-Fast Bulk Search Setup Script
Sets up optimized indexes and configurations for 10K+ part number searches
"""

import sys
import os
import time
import logging
from pathlib import Path

# Add the app directory to the Python path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from sqlalchemy.orm import Session
from sqlalchemy import text
from app.core.database import SessionLocal
from app.services.database.ultra_fast_index_manager import (
    create_ultra_fast_indexes,
    optimize_table_for_bulk_search,
    get_index_performance_stats
)
from app.services.cache.ultra_fast_cache_manager import ultra_fast_cache

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def setup_ultra_fast_system():
    """Set up the ultra-fast bulk search system"""
    
    logger.info("🚀 Setting up Ultra-Fast Bulk Search System...")
    start_time = time.perf_counter()
    
    db: Session = SessionLocal()
    
    try:
        # 1. Get all existing datasets
        logger.info("📊 Discovering existing datasets...")
        datasets = db.execute(text("""
            SELECT table_name 
            FROM information_schema.tables 
            WHERE table_name LIKE 'ds_%'
            ORDER BY table_name
        """)).fetchall()
        
        if not datasets:
            logger.warning("⚠️  No datasets found. Please upload some data first.")
            return
        
        logger.info(f"Found {len(datasets)} datasets")
        
        # 2. Create ultra-fast indexes for each dataset
        for dataset in datasets:
            table_name = dataset[0]
            logger.info(f"🔧 Setting up ultra-fast indexes for {table_name}...")
            
            try:
                # Create ultra-fast indexes
                create_ultra_fast_indexes(db, table_name)
                
                # Apply bulk search optimizations
                optimize_table_for_bulk_search(db, table_name)
                
                # Get performance stats
                stats = get_index_performance_stats(db, table_name)
                logger.info(f"✅ {table_name} optimized successfully")
                logger.info(f"   Table size: {stats.get('table_size', 'Unknown')}")
                logger.info(f"   Indexes created: {len(stats.get('indexes', []))}")
                
            except Exception as e:
                logger.error(f"❌ Failed to optimize {table_name}: {e}")
                continue
        
        # 3. Set up Redis cache
        logger.info("🔄 Setting up Redis cache...")
        try:
            cache_stats = ultra_fast_cache.get_cache_stats()
            logger.info(f"✅ Redis cache ready")
            logger.info(f"   Hit rate: {cache_stats.get('hit_rate', 0)}%")
            logger.info(f"   Memory used: {cache_stats.get('memory_used_human', 'Unknown')}")
        except Exception as e:
            logger.error(f"❌ Redis cache setup failed: {e}")
        
        # 4. Test the system
        logger.info("🧪 Testing ultra-fast system...")
        test_ultra_fast_system(db)
        
        setup_time = (time.perf_counter() - start_time) * 1000
        logger.info(f"🎉 Ultra-Fast Bulk Search System setup complete in {setup_time:.2f}ms")
        
    except Exception as e:
        logger.error(f"❌ Setup failed: {e}")
        raise
    finally:
        db.close()


def test_ultra_fast_system(db: Session):
    """Test the ultra-fast system with sample data"""
    
    try:
        # Get a sample dataset
        sample_table = db.execute(text("""
            SELECT table_name 
            FROM information_schema.tables 
            WHERE table_name LIKE 'ds_%'
            LIMIT 1
        """)).scalar()
        
        if not sample_table:
            logger.warning("No datasets available for testing")
            return
        
        logger.info(f"🧪 Testing with {sample_table}...")
        
        # Test 1: Check indexes
        index_stats = get_index_performance_stats(db, sample_table)
        logger.info(f"   Indexes: {len(index_stats.get('indexes', []))}")
        
        # Test 2: Check cache
        cache_stats = ultra_fast_cache.get_cache_stats()
        logger.info(f"   Cache status: {cache_stats.get('status', 'unknown')}")
        
        # Test 3: Sample query performance
        start_time = time.perf_counter()
        result = db.execute(text(f"""
            SELECT COUNT(*) 
            FROM {sample_table} 
            WHERE "part_number" IS NOT NULL
        """)).scalar()
        query_time = (time.perf_counter() - start_time) * 1000
        
        logger.info(f"   Sample query: {result} rows in {query_time:.2f}ms")
        
        if query_time < 100:  # Less than 100ms
            logger.info("✅ Performance test passed")
        else:
            logger.warning("⚠️  Performance test failed - query too slow")
        
    except Exception as e:
        logger.error(f"❌ Test failed: {e}")


def get_system_status():
    """Get the current status of the ultra-fast system"""
    
    db: Session = SessionLocal()
    
    try:
        logger.info("📊 Ultra-Fast System Status Report")
        logger.info("=" * 50)
        
        # Database status
        datasets = db.execute(text("""
            SELECT table_name, 
                   pg_size_pretty(pg_total_relation_size(table_name::regclass)) as size
            FROM information_schema.tables 
            WHERE table_name LIKE 'ds_%'
            ORDER BY pg_total_relation_size(table_name::regclass) DESC
        """)).fetchall()
        
        logger.info(f"📁 Datasets: {len(datasets)}")
        for dataset in datasets[:5]:  # Show top 5
            logger.info(f"   {dataset[0]}: {dataset[1]}")
        
        # Index status
        total_indexes = db.execute(text("""
            SELECT COUNT(*) 
            FROM pg_indexes 
            WHERE tablename LIKE 'ds_%'
        """)).scalar()
        
        logger.info(f"🔧 Total indexes: {total_indexes}")
        
        # Cache status
        cache_stats = ultra_fast_cache.get_cache_stats()
        logger.info(f"💾 Cache hit rate: {cache_stats.get('hit_rate', 0)}%")
        logger.info(f"💾 Memory used: {cache_stats.get('memory_used_human', 'Unknown')}")
        
        # Performance recommendations
        logger.info("\n🚀 Performance Recommendations:")
        logger.info("   • Use /api/v1/query-optimized/search-part-bulk-ultra-fast for bulk searches")
        logger.info("   • Enable Redis caching for repeated searches")
        logger.info("   • Use batch sizes of 1000+ for optimal performance")
        logger.info("   • Monitor cache hit rates and adjust TTL as needed")
        
    except Exception as e:
        logger.error(f"❌ Status check failed: {e}")
    finally:
        db.close()


if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description="Ultra-Fast Bulk Search Setup")
    parser.add_argument("--setup", action="store_true", help="Set up ultra-fast system")
    parser.add_argument("--status", action="store_true", help="Check system status")
    
    args = parser.parse_args()
    
    if args.setup:
        setup_ultra_fast_system()
    elif args.status:
        get_system_status()
    else:
        print("Usage: python ultra_fast_setup.py --setup or --status")
