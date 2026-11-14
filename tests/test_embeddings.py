import sys
import types

import numpy as np
import pytest

from app import config
from app.embeddings import DemoEmbedder, VoyageEmbedder, VoyageReranker, normalize


class FakeVoyageClient:
    """Stands in for voyageai.Client and records every call, so we can check WHAT would be sent."""

    def __init__(self, api_key=None):
        self.api_key, self.embed_calls, self.rerank_calls = api_key, [], []

    def embed(self, texts, model=None, input_type=None):
        self.embed_calls.append({"n": len(texts), "model": model, "input_type": input_type})
        return types.SimpleNamespace(embeddings=[[3.0, 4.0, 0.0] for _ in texts])  # deliberately not unit length

    def rerank(self, query, documents, model, top_k=None):
        self.rerank_calls.append({"query": query, "documents": documents, "model": model, "top_k": top_k})
        picks = sorted(range(len(documents)), key=lambda i: -len(documents[i]))[:top_k]  # "longest passage wins"
        return types.SimpleNamespace(
            results=[
                types.SimpleNamespace(index=i, document=documents[i], relevance_score=1 - n / 10)
                for n, i in enumerate(picks)
            ]
        )


@pytest.fixture
def fake_voyage(monkeypatch):
    module = types.ModuleType("voyageai")
    module.Client = FakeVoyageClient
    monkeypatch.setitem(sys.modules, "voyageai", module)


def cosine(a, b):
    return float(a @ b)


def test_demo_vectors_have_length_one_and_are_repeatable():
    vectors = DemoEmbedder().embed(["kopi pahit", "kopi pahit", "kucing"], "document")
    assert np.allclose(np.linalg.norm(vectors, axis=1), 1.0)
    assert np.array_equal(vectors[0], vectors[1])


def test_demo_texts_sharing_words_are_closer_than_unrelated_ones():
    kopi_a, kopi_b, kucing = DemoEmbedder().embed(
        ["kopi terasa pahit", "kopi saya pahit sekali", "kucing makan ikan"], "document"
    )
    assert cosine(kopi_a, kopi_b) > cosine(kopi_a, kucing) + 0.3


def test_demo_cannot_tell_that_different_words_mean_the_same_thing():
    """The honest limit of the demo: the real model is what knows 'mobil' and 'kendaraan' are related."""
    mobil, kendaraan = DemoEmbedder().embed(["mobil", "kendaraan"], "document")
    assert cosine(mobil, kendaraan) == 0.0


def test_an_empty_text_does_not_divide_by_zero():
    assert np.all(np.isfinite(normalize(np.zeros((1, 4), dtype=np.float32))))


def test_voyage_embedder_sends_the_model_and_input_type_and_normalizes(fake_voyage):
    embedder = VoyageEmbedder(model="voyage-test", api_key="test-key-not-real")
    vectors = embedder.embed(["a", "b"], "query")
    call = embedder.client.embed_calls[0]
    assert call == {"n": 2, "model": "voyage-test", "input_type": "query"}
    assert embedder.client.api_key == "test-key-not-real"
    assert np.allclose(vectors[0], [0.6, 0.8, 0.0])  # (3, 4, 0) scaled to length 1


def test_voyage_embedder_splits_big_inputs_into_batches(fake_voyage):
    embedder = VoyageEmbedder(model="voyage-test")
    vectors = embedder.embed([f"t{i}" for i in range(config.EMBED_BATCH * 2 + 5)], "document")
    assert [c["n"] for c in embedder.client.embed_calls] == [config.EMBED_BATCH, config.EMBED_BATCH, 5]
    assert vectors.shape[0] == config.EMBED_BATCH * 2 + 5


def test_voyage_reranker_returns_index_and_score_best_first(fake_voyage):
    reranker = VoyageReranker(model="rerank-test", api_key="test-key-not-real")
    ranked = reranker.rerank("q", ["pendek", "ini yang paling panjang", "sedang saja"], top_k=2)
    assert [index for index, _ in ranked] == [1, 2]
    assert ranked[0][1] > ranked[1][1]
    assert reranker.client.rerank_calls[0]["model"] == "rerank-test" and reranker.client.rerank_calls[0]["top_k"] == 2
    assert reranker.client.api_key == "test-key-not-real"


def test_a_missing_key_is_left_to_the_voyage_sdk_to_report(fake_voyage):
    assert VoyageEmbedder(model="voyage-test", api_key="").client.api_key is None  # "" means "not set", never sent
