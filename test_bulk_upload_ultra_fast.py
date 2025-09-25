#!/usr/bin/env python3
"""
Test the updated bulk upload endpoint with ultra-fast system
"""

import sys
from pathlib import Path
import pandas as pd
import io

# Add the app directory to the Python path
sys.path.insert(0, str(Path(__file__).parent))

from sqlalchemy import text
from app.core.database import SessionLocal
from app.api.v1.endpoints.query import search_part_number_bulk_upload
from fastapi import UploadFile

async def test_bulk_upload_ultra_fast():
    """Test the updated bulk upload endpoint with ultra-fast system"""
    
    print("🚀 Testing Bulk Upload with Ultra-Fast System")
    print("=" * 60)
    
    # Create a test CSV file in memory
    test_data = {
        'part_number': ['8065103', '8065127', 'TEST123', 'F9342NJ']
    }
    df = pd.DataFrame(test_data)
    
    # Convert to CSV bytes
    csv_buffer = io.BytesIO()
    df.to_csv(csv_buffer, index=False)
    csv_content = csv_buffer.getvalue()
    
    # Create a mock UploadFile
    class MockUploadFile:
        def __init__(self, content: bytes, filename: str):
            self.content = content
            self.filename = filename
        
        async def read(self):
            return self.content
    
    mock_file = MockUploadFile(csv_content, "test_parts.csv")
    
    db = SessionLocal()
    try:
        # Test the bulk upload endpoint
        result = await search_part_number_bulk_upload(39, mock_file, db, None)
        
        print(f"✅ Bulk upload successful!")
        print(f"Total parts: {result.get('total_parts', 0)}")
        print(f"Latency: {result.get('latency_ms', 0)}ms")
        print(f"Results count: {len(result.get('results', {}))}")
        
        # Show sample results
        results = result.get('results', {})
        if results:
            print(f"\n📊 Sample results:")
            for part_num, part_data in list(results.items())[:2]:
                print(f"  Part: {part_num}")
                companies = part_data.get('companies', [])
                print(f"    Matches: {len(companies)}")
                if companies:
                    match = companies[0]
                    print(f"    Company: {match.get('company_name', 'N/A')}")
                    print(f"    Price: {match.get('unit_price', 'N/A')}")
                    print(f"    Quantity: {match.get('quantity', 'N/A')}")
                print()
        else:
            print("ℹ️ No results found")
            
    except Exception as e:
        print(f"❌ Bulk upload failed: {e}")
        import traceback
        traceback.print_exc()
    finally:
        db.close()

if __name__ == "__main__":
    import asyncio
    asyncio.run(test_bulk_upload_ultra_fast())
