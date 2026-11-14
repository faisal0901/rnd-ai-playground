"""RAG = Retrieval-Augmented Generation. The model does not know YOUR documents, so before it answers we look up the
relevant passages and hand them over as text it can read and quote.

    INDEX (once per document)              SEARCH (every question)
    file -> chunks -> embeddings           question -> embedding (input_type="query")
         -> saved in the VectorStore            -> cosine against every stored vector -> top k
                                                -> (optional) reranker reorders the top candidates
                                                -> the agent's search_docs tool returns them to the model

The whole "vector database" here is one numpy matrix and a list of records. A real database (pgvector in the Router)
does the same math with an index so it stays fast with millions of rows; the idea does not change.
"""

import hashlib
import json
from pathlib import Path

import numpy as np

from app import config
from app.chunking import chunk_text
from app.embeddings import DemoEmbedder, Embedder, Reranker, VoyageEmbedder, VoyageReranker

Hit = dict  # {"source": file name, "chunk": number, "text": passage, "score": float}


def _empty_matrix() -> np.ndarray:
    return np.zeros((0, 0), dtype=np.float32)


class VectorStore:
    def __init__(self, embedder: Embedder, reranker: Reranker | None = None, directory: Path | str | None = None):
        self.embedder = embedder
        self.reranker = reranker
        self.directory = Path(directory) if directory else None
        self.records: list[dict] = []  # one per chunk: source, chunk, text
        self.vectors = _empty_matrix()  # row i belongs to records[i]
        self.hashes: dict[str, str] = {}  # source -> fingerprint of the text we indexed
        if self.directory:
            self._load()

    # ---- indexing ---------------------------------------------------------------------------------------------------
    def add_document(
        self, source: str, text: str, size: int = config.CHUNK_SIZE, overlap: int = config.CHUNK_OVERLAP
    ) -> int:
        """Index one document. Returns how many chunks were stored, 0 if it had not changed since last time."""
        fingerprint = hashlib.sha256(text.encode("utf-8")).hexdigest()
        if self.hashes.get(source) == fingerprint:
            return 0  # unchanged: skip, and skip paying for the embeddings
        pieces = chunk_text(text, size, overlap)
        vectors = self.embedder.embed(pieces, "document") if pieces else _empty_matrix()
        self._drop(source)  # a changed document must not leave its old chunks behind
        if pieces:
            self.records += [{"source": source, "chunk": i, "text": piece} for i, piece in enumerate(pieces)]
            self.vectors = vectors if len(self.vectors) == 0 else np.vstack([self.vectors, vectors])
        self.hashes[source] = fingerprint
        self._save()
        return len(pieces)

    def _drop(self, source: str) -> None:
        keep = [i for i, record in enumerate(self.records) if record["source"] != source]
        self.records = [self.records[i] for i in keep]
        self.vectors = self.vectors[keep] if keep else _empty_matrix()

    # ---- searching --------------------------------------------------------------------------------------------------
    def search(self, query: str, k: int = config.DEFAULT_HITS) -> list[Hit]:
        """The k passages closest in meaning to the query, best first."""
        if not self.records:
            return []
        query_vector = self.embedder.embed([query], "query")[0]
        scores = self.vectors @ query_vector  # unit vectors: this dot product is the cosine similarity
        order = np.argsort(-scores)  # best first
        if self.reranker:
            return self._rerank(query, order[: max(k, config.RERANK_CANDIDATES)], k)
        return [{**self.records[i], "score": round(float(scores[i]), 4)} for i in order[:k]]

    def _rerank(self, query: str, candidates: np.ndarray, k: int) -> list[Hit]:
        ranked = self.reranker.rerank(query, [self.records[i]["text"] for i in candidates], k)
        return [{**self.records[candidates[i]], "score": round(float(score), 4)} for i, score in ranked]

    # ---- saving -----------------------------------------------------------------------------------------------------
    def _save(self) -> None:
        if not self.directory:
            return
        self.directory.mkdir(parents=True, exist_ok=True)
        np.save(self.directory / "vectors.npy", self.vectors)
        saved = {"model": self.embedder.name, "hashes": self.hashes, "records": self.records}
        (self.directory / "records.json").write_text(json.dumps(saved, ensure_ascii=False), encoding="utf-8")

    def _load(self) -> None:
        path = self.directory / "records.json"
        if not path.exists():
            return
        saved = json.loads(path.read_text(encoding="utf-8"))
        if saved["model"] != self.embedder.name:
            # Vectors from different models live in different "spaces": comparing them gives nonsense.
            raise ValueError(
                f"The index in {self.directory} was made with '{saved['model']}' but the embedder is "
                f"'{self.embedder.name}'. Delete the folder to index again."
            )
        self.records, self.hashes = saved["records"], saved["hashes"]
        self.vectors = np.load(self.directory / "vectors.npy")


def index_folder(store: VectorStore, folder: Path | str = config.DOCS_DIR) -> dict[str, int]:
    """Index every .md / .txt file in the folder. Returns {file name: chunks stored, 0 = unchanged}."""
    folder = Path(folder)
    files = sorted(folder.iterdir()) if folder.is_dir() else []
    return {
        file.name: store.add_document(file.name, file.read_text(encoding="utf-8"))
        for file in files
        if file.suffix.lower() in (".md", ".txt")
    }


# ---- the store the app uses ------------------------------------------------------------
_store: VectorStore | None = None


def get_store() -> VectorStore:
    """Built on first use, not at startup: a slow first request is better than a slow boot.
    Voyage when VOYAGE_API_KEY is set, otherwise the demo embedder. Unchanged documents cost nothing on later runs."""
    global _store
    if _store is None:
        if config.VOYAGE_API_KEY:
            store = VectorStore(VoyageEmbedder(), VoyageReranker(), config.INDEX_DIR)
        else:
            store = VectorStore(DemoEmbedder())  # the demo index is cheap to rebuild, so it is not saved
        index_folder(store)
        _store = store
    return _store


def use_store(store: VectorStore | None) -> None:
    """Swap the store (tests, or a different folder). None goes back to the default on the next use."""
    global _store
    _store = store


if __name__ == "__main__":  # python -m app.rag "your question"   - search without any LLM, to play with the scores
    import sys

    for hit in get_store().search(" ".join(sys.argv[1:]) or "kopi"):
        print(f"{hit['score']:.3f}  {hit['source']}#{hit['chunk']}  {hit['text'][:90]!r}")
