import json

import numpy as np
import pytest

from app.embeddings import DemoEmbedder
from app.rag import VectorStore, index_folder

KOPI = "Kopi terasa pahit kalau air terlalu panas. Turunkan suhu air sebelum menyeduh kopi."
KUCING = "Kucing makan dua kali sehari dan butuh air bersih. Bawa kucing ke dokter hewan setahun sekali."
CUTI = "Cuti tahunan berjumlah dua belas hari. Ajukan cuti tujuh hari sebelumnya melalui atasan."


class RecordingEmbedder(DemoEmbedder):
    name = "recording"

    def __init__(self):
        self.calls = []

    def embed(self, texts, input_type):
        self.calls.append((len(texts), input_type))
        return super().embed(texts, input_type)


def make_store(**kwargs):
    store = VectorStore(DemoEmbedder(), **kwargs)
    for name, text in (("kopi.md", KOPI), ("kucing.md", KUCING), ("cuti.md", CUTI)):
        store.add_document(name, text)
    return store


def test_the_best_match_comes_first_and_scores_go_down():
    hits = make_store().search("kopi pahit air panas", k=3)
    assert hits[0]["source"] == "kopi.md"
    assert [h["score"] for h in hits] == sorted((h["score"] for h in hits), reverse=True)
    assert set(hits[0]) == {"source", "chunk", "text", "score"}


def test_k_limits_the_number_of_results():
    assert len(make_store().search("kopi", k=2)) == 2
    assert len(make_store().search("kopi", k=99)) == 3  # only three chunks exist


def test_an_empty_store_finds_nothing():
    assert VectorStore(DemoEmbedder()).search("apa saja") == []


def test_documents_are_embedded_as_document_and_questions_as_query():
    embedder = RecordingEmbedder()
    store = VectorStore(embedder)
    store.add_document("kopi.md", KOPI)
    store.search("kopi")
    assert embedder.calls == [(1, "document"), (1, "query")]


def test_an_unchanged_document_is_skipped_and_costs_no_embedding_call():
    embedder = RecordingEmbedder()
    store = VectorStore(embedder)
    assert store.add_document("kopi.md", KOPI) == 1
    assert store.add_document("kopi.md", KOPI) == 0
    assert embedder.calls == [(1, "document")]


def test_a_changed_document_replaces_its_old_chunks_instead_of_adding_to_them():
    store = make_store()
    store.add_document("kopi.md", "Sekarang dokumen ini hanya membahas teh hijau dan teh melati.")
    assert [r["text"] for r in store.records if r["source"] == "kopi.md"] == [
        "Sekarang dokumen ini hanya membahas teh hijau dan teh melati."
    ]
    assert len(store.records) == len(store.vectors) == 3
    assert store.search("teh melati hijau", k=1)[0]["source"] == "kopi.md"
    assert all("pahit" not in r["text"] for r in store.records)  # the old text is really gone


def test_long_documents_become_several_chunks_with_numbers():
    store = VectorStore(DemoEmbedder())
    store.add_document("buku.md", " ".join(f"kata{i}" for i in range(600)), size=300, overlap=50)
    chunks = [r["chunk"] for r in store.records]
    assert len(chunks) > 5 and chunks == list(range(len(chunks)))
    assert store.vectors.shape[0] == len(chunks)


def test_the_index_survives_a_restart(tmp_path):
    first = make_store(directory=str(tmp_path))
    again = VectorStore(DemoEmbedder(), directory=str(tmp_path))
    assert again.records == first.records and np.array_equal(again.vectors, first.vectors)
    assert again.search("kucing dokter hewan", k=1)[0]["source"] == "kucing.md"
    assert again.add_document("kopi.md", KOPI) == 0  # and it remembers what it already indexed


def test_an_index_made_by_another_model_is_refused(tmp_path):
    make_store(directory=str(tmp_path))
    other = RecordingEmbedder()  # a different model name
    with pytest.raises(ValueError, match="demo-words.*recording"):
        VectorStore(other, directory=str(tmp_path))


def test_the_saved_files_hold_no_secrets_and_are_readable(tmp_path):
    make_store(directory=str(tmp_path))
    saved = json.loads((tmp_path / "records.json").read_text(encoding="utf-8"))
    assert saved["model"] == "demo-words-512" and len(saved["records"]) == 3


class ReverseReranker:
    """Pretends the vector search got the order wrong and puts the LAST candidate first."""

    name = "reverse"

    def __init__(self):
        self.seen = None

    def rerank(self, query, texts, top_k):
        self.seen = (query, list(texts), top_k)
        return [(i, 1.0 - n * 0.1) for n, i in enumerate(reversed(range(len(texts))))][:top_k]


def test_the_reranker_gets_the_candidates_and_its_order_wins():
    reranker = ReverseReranker()
    store = make_store(reranker=reranker)
    plain = make_store().search("kopi pahit air panas", k=3)
    hits = store.search("kopi pahit air panas", k=2)
    assert reranker.seen[0] == "kopi pahit air panas" and reranker.seen[2] == 2
    assert len(reranker.seen[1]) == 3  # all candidates, not only k
    assert hits[0]["text"] == plain[2]["text"]  # the vector search's worst became the reranker's first
    assert hits[0]["score"] == 1.0  # and the score shown is the reranker's


def test_index_folder_reads_md_and_txt_only_and_reports_chunks(tmp_path):
    (tmp_path / "a.md").write_text(KOPI, encoding="utf-8")
    (tmp_path / "b.txt").write_text(KUCING, encoding="utf-8")
    (tmp_path / "c.pdf").write_bytes(b"%PDF not text")
    store = VectorStore(DemoEmbedder())
    assert index_folder(store, str(tmp_path)) == {"a.md": 1, "b.txt": 1}
    assert index_folder(store, str(tmp_path)) == {"a.md": 0, "b.txt": 0}  # second run: nothing changed
    assert index_folder(store, str(tmp_path / "missing")) == {}
