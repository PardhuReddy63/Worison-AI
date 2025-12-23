# backend/embedding.py

from typing import List, Optional, Dict
import logging

import numpy as np
from sklearn.neighbors import NearestNeighbors

from model_wrapper import get_wrapper


# Configure logger for embedding-related operations
logger = logging.getLogger("embedding")
logger.setLevel(logging.INFO)


# In-memory embedding index supporting similarity search
class EmbeddingIndex:
    # Initialize storage for IDs, vectors, nearest-neighbor model, and model wrapper
    def __init__(self):
        self.ids: List[str] = []
        self.vectors: Optional[np.ndarray] = None
        self.nn: Optional[NearestNeighbors] = None
        self.wrapper = get_wrapper()

    # Add a list of texts and optional IDs into the embedding index
    def add(self, texts: List[str], ids: Optional[List[str]] = None) -> None:
        if not texts:
            return

        embeddings = self.wrapper.generate_embeddings(texts)
        if not embeddings:
            logger.warning("Embeddings not available. Skipping index add.")
            return

        arr = np.array(embeddings, dtype=float)

        if self.vectors is None:
            self.vectors = arr
            self.ids = ids or [str(i) for i in range(len(arr))]
        else:
            start = len(self.ids)
            self.vectors = np.vstack([self.vectors, arr])
            new_ids = ids or [str(start + i) for i in range(len(arr))]
            self.ids.extend(new_ids)

        self._rebuild_index()

    # Create or refresh the nearest-neighbor search structure
    def _rebuild_index(self) -> None:
        if self.vectors is None or len(self.vectors) == 0:
            self.nn = None
            return

        n_neighbors = min(10, len(self.vectors))
        self.nn = NearestNeighbors(
            n_neighbors=n_neighbors,
            metric="cosine",
        )
        self.nn.fit(self.vectors)

    # Query the index using a text input and return similarity results
    def query(self, text: str, top_k: int = 5) -> List[Dict[str, float]]:
        if not text or not self.nn:
            return []

        embeddings = self.wrapper.generate_embeddings([text])
        if not embeddings:
            return []

        arr = np.array(embeddings, dtype=float)

        try:
            k = min(top_k, len(self.vectors))
            distances, indices = self.nn.kneighbors(arr, n_neighbors=k)

            results = []
            for rank, idx in enumerate(indices[0]):
                results.append(
                    {
                        "id": self.ids[idx],
                        "score": float(distances[0][rank]),
                    }
                )
            return results
        except Exception as e:
            logger.exception("Embedding query failed: %s", e)
            return []


# Global singleton instance for shared embedding index usage
_GLOBAL_INDEX: Optional[EmbeddingIndex] = None


# Retrieve or create the global embedding index instance
def get_embedding_index() -> EmbeddingIndex:
    global _GLOBAL_INDEX
    if _GLOBAL_INDEX is None:
        _GLOBAL_INDEX = EmbeddingIndex()
    return _GLOBAL_INDEX
