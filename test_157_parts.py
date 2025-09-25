#!/usr/bin/env python3

import sys
import time
import asyncio
sys.path.insert(0, '.')
from app.api.v1.endpoints.query_elasticsearch import search_part_number_bulk_elasticsearch
from app.core.database import SessionLocal

async def test_157_parts():
    """Test with the actual 157 parts that were causing timeout"""
    
    # The actual 157 parts from the user's test
    part_numbers = [
        "R536446", "R536444", "FOC IQ8HC 72 M INT", "MAT0170187", "MAT01718034", "MAT0170640",
        "CF113.037.D", "CF270.UL.40.04.D", "CF78.UL.10.03", "CFBUS.PVC.049", "CF220.UL.H101.10.04",
        "CF9.05.03", "CF77.UL.07.03.D", "CF270.UL.250.01.D", "CF130.15.04.UL", "CF211.041",
        "CF9.UL.03.04.INI", "CF130.15.05.UL", "CF211.PUR.05.06.02", "MAT0171598", "MAT0171464",
        "MAT0171468", "MAT01714788", "MAT01723505", "MAT01710114", "MAT01710120", "MAT01710121",
        "MAT0172342", "MAT01710124", "MAT01710144", "MAT0171334", "MAT01712103", "MSG24KN6XXX",
        "2TC65-5", "E29253CA", "1SAM201901R1004", "1SAM201920R1000", "1SAM201909R1021", "1SAM201920R1001",
        "GJL1313901R0011", "GJL1313901R0101", "1SAM340000R1007", "1SAM340000R1006", "1SAM340000R1008",
        "1SAM340000R1009", "1SAM360000R1012", "1SAM350000R1012", "1SAM350000R1011", "1SVR508100R0100",
        "1SAM360000R1013", "1SAM150000R1005", "1SAM360000R1014", "1SVR550882R9500", "1SAM360000R1015",
        "1SAM150000R1014", "1SVR550801R9300", "1SVR500160R0000", "1SVR730210R3300", "1SVR508020R1100",
        "1SVR730712R0200", "1SAZ421201R1003", "1SAZ421201R1005", "1SVR740010R0200", "1SVR730840R0400",
        "2TLA010070R0400", "1SAM350000R1008", "1SAM250000R1009", "1SAM350000R1015", "1SVR730005R0100",
        "1SAM350000R1001", "1SAM250000R1005", "1SVR405613R1100", "1SAM201901R1001", "1SAJ243000R0001",
        "1SAJ650000R0100", "1SAJ925000R0001", "1SAJ929500R0185", "1SAJ929600R0001", "1SAM201902R1001",
        "1SAM250000R1003", "1SAM250000R1004", "1SVR730660R0100", "GJH1213061R5221", "GJL1313061R5011",
        "1SVR730824R9300", "1SVR405613R1000", "1SVR405613R7000", "1SVR405611R1000", "1SVR405611R8000",
        "1SVR405612R1100", "1SVR405613R9000", "1SVR405650R1000", "1SVR405651R2000", "1SAJ242000R0001",
        "GJL1211001R0011", "GJL1211901R0011", "GJL1213001R0101", "GHV2501902R0002", "1SAM250000R1007",
        "1SVR405613R3100", "1SVR730840R0500", "1SVR405541R3110", "1SVR405651R1000", "1SAM250000R1008",
        "1SVR508100R0000", "A2C33018600", "CCS-720XP-48Y6-F-C14", "610-00623", "DDPB02962", "5255345",
        "E73840A01-B", "E66962A02", "PCB-A20B-2101-0300", "A860-0309-T352", "649-221311-00030T4LF",
        "538-51047-0400", "538-51021-0200", "80-C0603C224K4RECAUT", "791-0402B104K160CT", "810-C1005X5R1V105K",
        "187-CL31A226KAHNNNE", "791-0402N330G500CT", "791-0402N160J500CT", "187-CL21A106KAYNNNE", "833-SMD24PL-TP",
        "798-DF11-6DP-2DSA01", "538-504050-1091", "538-54104-3031", "538-52207-0860", "798-DF11-12DS-2DSA06",
        "851-CDRH4D22PNP100MC", "673-PA4332222NLT", "71-RCC08050000Z0EA", "279-352222RFT", "652-CRM2512FXR910ELF",
        "603-RC0402JR-070RL", "603-RC0402JR-0710KL", "652-CRM2512-JW1R0ELF", "603-RC0402FR-07180KL", "603-AC0402FR-07360KL",
        "603-RC0402JR-072K2L", "603-RC0402FR-0722RL", "71-CRCW0402-100K-E3", "71-RCWE2512R620FKEA", "279-35224R7JT",
        "603-RC0603FR-07180KL", "71-CRCW0402-453K-E3", "603-RC0603FR-070RL", "612-TL1105JA", "595-TPS61165DRVR",
        "595-TPS62410DRCR", "595-TS3USB3000RSER", "595-LSF0204RGYR", "595-TPS22942DCKR", "402-SLG59M1545V", "595-TPS62160DSGR"
    ]
    
    print(f"🚀 Testing with {len(part_numbers)} parts (the actual parts that caused timeout)")
    print("=" * 80)
    
    # Test with file_id 39 (the one that was being used)
    file_id = 39
    
    # Create request payload
    req = {
        "file_id": file_id,
        "part_numbers": part_numbers,
        "page": 1,
        "page_size": 50,
        "show_all": False,
        "search_mode": "hybrid"
    }
    
    # Test the search
    start_time = time.perf_counter()
    
    try:
        db = SessionLocal()
        result = await search_part_number_bulk_elasticsearch(req, db, None)
        end_time = time.perf_counter()
        
        search_time = (end_time - start_time) * 1000  # Convert to milliseconds
        
        print(f"✅ Search completed!")
        print(f"⏱️  Time: {search_time:.2f}ms")
        print(f"📊 Total parts: {len(part_numbers)}")
        print(f"📊 Results count: {len(result.get('results', {}))}")
        print(f"🔍 Search engine: {result.get('search_engine', 'unknown')}")
        
        # Performance rating
        if search_time < 1000:
            rating = "🚀 EXCELLENT"
        elif search_time < 5000:
            rating = "✅ GOOD"
        elif search_time < 10000:
            rating = "⚠️ ACCEPTABLE"
        else:
            rating = "❌ SLOW"
        
        print(f"📈 Performance: {rating} ({search_time:.2f}ms)")
        
        # Check if we achieved the 5-second target
        if search_time < 5000:
            print(f"🎯 TARGET ACHIEVED! {len(part_numbers)} parts in {search_time:.2f}ms (under 5 seconds)!")
        else:
            print(f"❌ TARGET MISSED! {len(part_numbers)} parts took {search_time:.2f}ms (over 5 seconds)")
        
        # Show sample results
        results = result.get('results', {})
        if results:
            sample_part = list(results.keys())[0]
            sample_data = results[sample_part]
            print(f"📋 Sample: {sample_part} -> {len(sample_data.get('companies', []))} matches")
            if sample_data.get('companies'):
                first_company = sample_data['companies'][0]
                print(f"    Company: {first_company.get('company_name', 'N/A')}")
                print(f"    Price: {first_company.get('unit_price', 'N/A')}")
        
    except Exception as e:
        end_time = time.perf_counter()
        search_time = (end_time - start_time) * 1000
        print(f"❌ Search failed after {search_time:.2f}ms: {e}")
    finally:
        db.close()

if __name__ == "__main__":
    asyncio.run(test_157_parts())

