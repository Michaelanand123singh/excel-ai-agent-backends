from typing import Optional
import chromadb
from chromadb.config import Settings as ChromaSettings

from app.core.config import settings

_client: Optional[chromadb.Client] = None


def get_client() -> chromadb.Client:
	global _client
	if _client is None:
		_client = chromadb.PersistentClient(
			path=settings.CHROMA_PERSIST_DIR or ".chroma",
			settings=ChromaSettings(anonymized_telemetry=False),
		)
	return _client


def get_collection(name: str):
	client = get_client()
	return client.get_or_create_collection(name)


