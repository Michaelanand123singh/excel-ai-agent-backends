from typing import List, Dict

from .chroma_client import get_collection


def search(query: str, top_k: int = 5, collection_name: str = "default") -> List[Dict]:
	col = get_collection(collection_name)
	res = col.query(query_texts=[query], n_results=top_k)
	# Normalize to a list of dicts
	results = []
	for i in range(len(res.get("ids", [[]])[0])):
		results.append({
			"id": res["ids"][0][i],
			"text": res["documents"][0][i] if res.get("documents") else None,
			"metadata": res["metadatas"][0][i] if res.get("metadatas") else None,
			"distance": res["distances"][0][i] if res.get("distances") else None,
		})
	return results


