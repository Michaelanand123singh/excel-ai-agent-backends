#!/usr/bin/env python3
import argparse
import json
import sys
from sqlalchemy import text

from app.core.database import SessionLocal
from app.services.search_engine.data_sync import DataSyncService
from app.services.search_engine.elasticsearch_client import ElasticsearchBulkSearch


def main() -> int:
    parser = argparse.ArgumentParser(description="E2E test: sync dataset to Elasticsearch and run bulk search")
    parser.add_argument("--file-id", type=int, required=True)
    parser.add_argument("--limit", type=int, default=5)
    args = parser.parse_args()

    file_id = args.file_id
    limit = max(1, args.limit)

    print(f"[STEP] Syncing file {file_id} to Elasticsearch…", flush=True)
    ok = DataSyncService().sync_file_to_elasticsearch(file_id)
    print(f"SYNC: {ok}")

    print("[STEP] Selecting sample part numbers from dataset…", flush=True)
    sess = SessionLocal()
    try:
        table = f"ds_{file_id}"
        q = text(f"SELECT \"part_number\" FROM {table} WHERE \"part_number\" IS NOT NULL AND \"part_number\"<>'' LIMIT {limit}")
        rows = sess.execute(q).fetchall()
        parts = [r[0] for r in rows]
    finally:
        sess.close()

    if not parts:
        print("No part numbers found in dataset; cannot run search.")
        return 1

    print(f"PARTS: {parts}")

    print("[STEP] Connecting to Elasticsearch…", flush=True)
    client = ElasticsearchBulkSearch()
    print("ES_AVAILABLE:", client.is_available())
    if not client.is_available():
        print("Elasticsearch not available; aborting.")
        return 1

    print("[STEP] Running bulk search…", flush=True)
    res = client.bulk_search(parts, file_id, limit_per_part=3)
    summary = {k: res[k] for k in ("total_parts", "total_matches", "latency_ms", "search_engine")}
    print("SUMMARY:", summary)
    sample = {p: res["results"].get(p) for p in parts}
    print("SAMPLE:", json.dumps(sample)[:1200])
    return 0


if __name__ == "__main__":
    sys.exit(main())


