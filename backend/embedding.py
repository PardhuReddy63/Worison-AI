# backend/embedding.py
"""
Lightweight in-memory embedding index for AI Learning Assistant.

Purpose:
- Optional semantic search / RAG support
- Uses ModelWrapper.generate_embeddings()
- Safe to keep even if embeddings API is unavailable

NOTE:
- Currently NOT auto-wired into app.py
- Intended for future extension (RAG, semantic file search)
"""

from typing import List, Optional, Dict
import logging

import numpy as np
from sklearn.neighbors import NearestNeighbors

from model_wrapper import get_wrapper

logger = logging.getLogger("embedding")
logger.setLevel(logging.INFO)


class EmbeddingIndex:
    """
    Simple in-memory embedding index using cosine similarity.

    Design goals:
    - No persistence (RAM only)
    - Safe failure if embeddings are unavailable
    - Small-scale testing (NOT production vector DB)
    """

    def __init__(self):
        self.ids: List[str] = []
        self.vectors: Optional[np.ndarray] = None
        self.nn: Optional[NearestNeighbors] = None
        self.wrapper = get_wrapper()

    # --------------------------------------------------
    # Add texts to index
    # --------------------------------------------------
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

    # --------------------------------------------------
    # Build / rebuild nearest-neighbor index
    # --------------------------------------------------
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

    # --------------------------------------------------
    # Query index
    # --------------------------------------------------
    def query(self, text: str, top_k: int = 5) -> List[Dict[str, float]]:
        """
        Query the index using a text string.

        Returns:
        [
          { "id": <id>, "score": <cosine_distance> }
        ]
        """
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


# --------------------------------------------------
# Optional global index (lazy use)
# --------------------------------------------------
_GLOBAL_INDEX: Optional[EmbeddingIndex] = None


def get_embedding_index() -> EmbeddingIndex:
    """
    Singleton accessor for embedding index.

    Safe:
    - Creates index only when called
    - Does nothing if embeddings are unavailable
    """
    global _GLOBAL_INDEX
    if _GLOBAL_INDEX is None:
        _GLOBAL_INDEX = EmbeddingIndex()
    return _GLOBAL_INDEX
