"""Embeddings: turn a text into a list of numbers (a vector) so that texts with a similar MEANING get similar vectors.

Once texts are vectors, "which document is closest to this question?" is just arithmetic (see rag.py).

Every embedder has the same two members, like the two models in llm.py:

    embedder.embed(texts, input_type)  ->  numpy array, one unit-length row per text
    embedder.name                      ->  which model made the vectors

* VoyageEmbedder - the real thing (needs VOYAGE_API_KEY). Understands meaning: "kucing" ends up near "anjing".
* DemoEmbedder   - no key, no network. Only counts shared WORDS, so it cannot know that two different words mean
                   something similar. Good for seeing the mechanics; use Voyage to see the point of embeddings.

``input_type`` is "document" for the texts you store and "query" for the question. Voyage adds a different hidden
prefix for each, which makes a question land closer to the passages that answer it.
"""

import hashlib
import re
from typing import Protocol

import numpy as np

from app import config


class Embedder(Protocol):
    name: str

    def embed(self, texts: list[str], input_type: str) -> np.ndarray: ...


class Reranker(Protocol):
    name: str

    def rerank(self, query: str, texts: list[str], top_k: int) -> list[tuple[int, float]]: ...


def normalize(vectors: np.ndarray) -> np.ndarray:
    """Scale every row to length 1. Then the dot product of two rows IS their cosine similarity (-1 .. 1)."""
    norms = np.linalg.norm(vectors, axis=1, keepdims=True)
    return vectors / np.where(norms == 0, 1.0, norms)


class VoyageEmbedder:
    def __init__(self, model: str = config.VOYAGE_MODEL, api_key: str = config.VOYAGE_API_KEY):
        import voyageai  # imported here so the demo works without the package

        self.client = voyageai.Client(api_key=api_key or None)
        self.name = model

    def embed(self, texts: list[str], input_type: str) -> np.ndarray:
        rows: list[list[float]] = []
        for start in range(0, len(texts), config.EMBED_BATCH):  # the API limits how many texts one request may carry
            batch = texts[start : start + config.EMBED_BATCH]
            rows.extend(self.client.embed(batch, model=self.name, input_type=input_type).embeddings)
        return normalize(np.array(rows, dtype=np.float32).reshape(len(texts), -1))


class DemoEmbedder:
    """Hashing trick: each word is thrown into one of 512 buckets. Same words in two texts -> similar vectors."""

    name = f"demo-words-{config.DEMO_DIMENSIONS}"

    def embed(self, texts: list[str], input_type: str) -> np.ndarray:  # input_type is unused, kept for the interface
        vectors = np.zeros((len(texts), config.DEMO_DIMENSIONS), dtype=np.float32)
        for row, text in enumerate(texts):
            for word in re.findall(r"\w+", text.lower()):
                digest = hashlib.md5(word.encode("utf-8")).digest()
                vectors[row, int.from_bytes(digest[:4], "big") % config.DEMO_DIMENSIONS] += 1.0
        return normalize(vectors)


class VoyageReranker:
    """Second opinion. The vector search is fast but rough; a reranker reads the question TOGETHER with each
    candidate passage and scores how well the passage answers it. Slower, so it only sees the top candidates."""

    def __init__(self, model: str = config.VOYAGE_RERANK_MODEL, api_key: str = config.VOYAGE_API_KEY):
        import voyageai

        self.client = voyageai.Client(api_key=api_key or None)
        self.name = model

    def rerank(self, query: str, texts: list[str], top_k: int) -> list[tuple[int, float]]:
        """Return [(index into texts, relevance score)], best first."""
        result = self.client.rerank(query, texts, model=self.name, top_k=top_k)
        return [(item.index, item.relevance_score) for item in result.results]
