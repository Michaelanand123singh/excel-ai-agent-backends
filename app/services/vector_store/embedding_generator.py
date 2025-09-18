from typing import List
from functools import lru_cache


@lru_cache(maxsize=1)
def _get_model():
	from sentence_transformers import SentenceTransformer
	return SentenceTransformer("all-MiniLM-L6-v2")


def embed_texts(texts: List[str]) -> List[List[float]]:
	if not texts:
		return []
	model = _get_model()
	embeddings = model.encode(texts, normalize_embeddings=True)
	return embeddings.tolist()


