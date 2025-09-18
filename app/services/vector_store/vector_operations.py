from typing import List, Dict

from .chroma_client import get_collection
from app.core.config import settings


def upsert_texts(collection_name: str, ids: List[str], texts: List[str], metadatas: List[Dict] | None = None) -> int:
	"""Upsert texts into Chroma in safe chunks to respect provider batch limits."""
	col = get_collection(collection_name)
	# Chunk size can be tuned by environment
	max_chunk = max(100, int(getattr(settings, 'CHROMA_UPSERT_CHUNK', 1000)))
	count = 0
	md = metadatas or [{} for _ in ids]
	for start in range(0, len(ids), max_chunk):
		end = start + max_chunk
		chunk_ids = ids[start:end]
		chunk_docs = texts[start:end]
		chunk_meta = md[start:end]
		if not chunk_ids:
			continue
		col.upsert(ids=chunk_ids, documents=chunk_docs, metadatas=chunk_meta)
		count += len(chunk_ids)
	return count


