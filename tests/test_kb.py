import json

import pytest
from fastapi.testclient import TestClient
from pdfs import blank_pdf, make_pdf

from app import config, rag
from app.embeddings import DemoEmbedder
from app.llm import DemoLLM
from app.main import create_app
from app.rag import VectorStore

KOPI = "Kopi terasa pahit kalau air terlalu panas. Turunkan suhu air sebelum menyeduh kopi."


@pytest.fixture
def env(tmp_path):
    """A client whose folders and index live in tmp_path, with one built-in example already indexed."""
    uploads, samples = tmp_path / "uploads", tmp_path / "samples"
    samples.mkdir()
    (samples / "contoh.md").write_text("Contoh bawaan tentang kucing dan dokter hewan.", encoding="utf-8")
    store = VectorStore(DemoEmbedder())
    rag.index_folder(store, samples)
    rag.use_store(store)
    client = TestClient(create_app(DemoLLM(), upload_dir=uploads, sample_dir=samples))
    yield type("Env", (), {"client": client, "store": store, "uploads": uploads, "samples": samples, "root": tmp_path})
    rag.use_store(None)


def upload(client, name, data, content_type="text/plain"):
    return client.post("/api/kb", files={"file": (name, data, content_type)})


def search(client, query, k=5):
    return client.get("/api/search", params={"q": query, "k": k}).json()["results"]


# ---- uploading: saved AND embedded -----------------------------------------------------------------------------------
def test_an_upload_is_saved_embedded_and_immediately_searchable(env):
    response = upload(env.client, "kopi.md", KOPI.encode())
    assert response.status_code == 200
    assert response.json() == {"name": "kopi.md", "chunks": 1, "status": "indexed"}
    assert (env.uploads / "kopi.md").read_bytes() == KOPI.encode()
    assert search(env.client, "kopi pahit air panas", k=1)[0]["source"] == "kopi.md"


def test_the_list_shows_examples_and_uploads_with_their_chunk_counts(env):
    upload(env.client, "kopi.md", KOPI.encode())
    listing = env.client.get("/api/kb").json()
    assert listing["embedder"] == DemoEmbedder.name and listing["reranker"] is False
    assert listing["max_upload_mb"] == config.MAX_UPLOAD_BYTES // (1024 * 1024)
    rows = {d["name"]: d for d in listing["documents"]}
    assert rows["contoh.md"]["kind"] == "sample" and rows["contoh.md"]["chunks"] == 1
    assert rows["kopi.md"]["kind"] == "upload" and rows["kopi.md"]["chunks"] == 1
    assert rows["kopi.md"]["bytes"] == len(KOPI.encode())


def test_uploading_the_same_file_again_does_not_embed_it_again(env):
    upload(env.client, "kopi.md", KOPI.encode())
    again = upload(env.client, "kopi.md", KOPI.encode()).json()
    assert again["status"] == "unchanged" and again["chunks"] == 1
    assert len(env.store.records) == 2  # the example + one chunk of kopi.md, not duplicated


def test_uploading_a_changed_file_replaces_the_old_text(env):
    upload(env.client, "catatan.txt", b"Catatan lama tentang durian dan rambutan.")
    upload(env.client, "catatan.txt", b"Catatan baru tentang teh melati.")
    texts = " ".join(r["text"] for r in env.store.records)
    assert "melati" in texts and "durian" not in texts
    assert (env.uploads / "catatan.txt").read_text() == "Catatan baru tentang teh melati."


def test_a_pdf_is_read_and_becomes_searchable(env):
    response = upload(env.client, "laporan.pdf", make_pdf("durian montong paling manis"), "application/pdf")
    assert response.status_code == 200 and response.json()["chunks"] == 1
    assert search(env.client, "durian montong", k=1)[0]["source"] == "laporan.pdf"


def test_a_file_name_with_folders_is_stored_inside_the_upload_folder_only(env):
    response = upload(env.client, "../../evil.txt", b"isi yang jahat")
    assert response.status_code == 200 and response.json()["name"] == "evil.txt"
    assert (env.uploads / "evil.txt").exists()
    assert not (env.root / "evil.txt").exists() and not (env.root.parent / "evil.txt").exists()


# ---- uploading: refusals --------------------------------------------------------------------------------------------
@pytest.mark.parametrize(
    ("name", "data", "status"),
    [
        ("a.exe", b"MZ", 415),
        ("a.docx", b"PK", 415),
        ("kosong.txt", b"", 422),
        ("spasi.md", b"  \n ", 422),
        ("biner.txt", b"a\x00b", 415),
    ],
)
def test_unusable_files_are_refused_and_nothing_is_kept(env, name, data, status):
    response = upload(env.client, name, data)
    assert response.status_code == status and response.json()["detail"]
    assert not list(env.uploads.glob("*")) if env.uploads.exists() else True
    assert len(env.store.records) == 1  # only the example


def test_a_scanned_pdf_gets_a_clear_message(env):
    response = upload(env.client, "scan.pdf", blank_pdf(), "application/pdf")
    assert response.status_code == 422 and "OCR" in response.json()["detail"]


def test_a_file_named_like_a_built_in_example_is_refused(env):
    response = upload(env.client, "contoh.md", b"saya mau menimpa contoh")
    assert response.status_code == 409
    assert (env.samples / "contoh.md").read_text().startswith("Contoh bawaan")  # the example is untouched


def test_a_file_over_the_size_limit_is_refused(env, monkeypatch):
    monkeypatch.setattr(config, "MAX_UPLOAD_BYTES", 100)
    assert upload(env.client, "ok.txt", b"x" * 100).status_code == 200
    assert upload(env.client, "besar.txt", b"x" * 101).status_code == 413


def test_the_kb_itself_refuses_oversized_data_even_without_the_api(env, monkeypatch):
    from app import kb
    from app.documents import DocumentError

    monkeypatch.setattr(config, "MAX_UPLOAD_BYTES", 100)
    with pytest.raises(DocumentError) as error:
        kb.add_upload(env.store, "besar.txt", b"x" * 101, env.uploads, env.samples)
    assert error.value.status == 413 and not env.uploads.exists()


def test_the_api_never_reads_more_than_one_byte_past_the_limit(monkeypatch):
    import asyncio

    from app.documents import DocumentError
    from app.main import read_upload

    monkeypatch.setattr(config, "MAX_UPLOAD_BYTES", 100)
    asked = []

    class Endless:
        async def read(self, n):
            asked.append(n)
            return b"x" * n

    with pytest.raises(DocumentError) as error:
        asyncio.run(read_upload(Endless()))
    assert error.value.status == 413 and asked == [101]  # one byte more than allowed is enough to know it is too big


def test_an_announced_huge_body_is_refused_before_it_is_read(env, monkeypatch):
    monkeypatch.setattr(config, "MAX_UPLOAD_BYTES", 10)
    response = upload(env.client, "raksasa.txt", b"x" * (2 * 1024 * 1024))  # far over limit + 1 MB of slack
    assert response.status_code == 413 and "too large" in response.json()["detail"]


def test_a_text_with_too_many_characters_is_refused(env, monkeypatch):
    monkeypatch.setattr(config, "MAX_DOC_CHARS", 50)
    assert upload(env.client, "panjang.txt", b"x " * 60).status_code == 413


def test_when_embedding_fails_nothing_is_saved_and_the_index_is_unchanged(env):
    class Broken(DemoEmbedder):
        def embed(self, texts, input_type):
            raise ConnectionError("voyage is down")

    rag.use_store(VectorStore(Broken()))
    response = upload(env.client, "baru.txt", b"isi baru")
    assert response.status_code == 502 and "ConnectionError" in response.json()["detail"]
    assert not (env.uploads / "baru.txt").exists()  # a file the index does not know about is not kept


# ---- deleting -------------------------------------------------------------------------------------------------------
def test_deleting_removes_the_file_the_chunks_and_the_search_results(env):
    upload(env.client, "kopi.md", KOPI.encode())
    response = env.client.delete("/api/kb/kopi.md")
    assert response.status_code == 200 and response.json() == {"name": "kopi.md", "removed_chunks": 1}
    assert not (env.uploads / "kopi.md").exists()
    assert all(hit["source"] != "kopi.md" for hit in search(env.client, "kopi pahit air panas"))
    assert "kopi.md" not in {d["name"] for d in env.client.get("/api/kb").json()["documents"]}


def test_a_deleted_file_can_be_uploaded_again(env):
    upload(env.client, "kopi.md", KOPI.encode())
    env.client.delete("/api/kb/kopi.md")
    assert upload(env.client, "kopi.md", KOPI.encode()).json()["status"] == "indexed"


def test_deleting_something_that_is_not_there_is_404(env):
    assert env.client.delete("/api/kb/tidak-ada.md").status_code == 404


def test_built_in_examples_cannot_be_deleted(env):
    response = env.client.delete("/api/kb/contoh.md")
    assert response.status_code == 403
    assert (env.samples / "contoh.md").exists() and len(env.store.records) == 1


def test_a_delete_cannot_reach_a_file_outside_the_upload_folder(env):
    outside = env.root / "penting.txt"
    outside.write_text("jangan dihapus")
    env.uploads.mkdir()
    for attempt in ("../penting.txt", "..%2Fpenting.txt", "%2E%2E%2Fpenting.txt"):
        env.client.delete(f"/api/kb/{attempt}")
    assert outside.exists()


# ---- chat attachments: read, never stored, never embedded ------------------------------
def attach(env, name, data):
    return env.client.post("/api/attach", files={"file": (name, data, "text/plain")})


def test_an_attachment_returns_its_text_and_keeps_nothing(env):
    before = len(env.store.records)
    response = attach(env, "catatan.txt", b"Rapat jam 3 sore.")
    assert response.status_code == 200
    assert response.json() == {"name": "catatan.txt", "text": "Rapat jam 3 sore.", "chars": 17, "truncated": False}
    assert len(env.store.records) == before  # NOT embedded
    assert not env.uploads.exists() or not list(env.uploads.iterdir())  # NOT saved
    assert env.store.hashes.keys() == {"contoh.md"}


def test_a_long_attachment_is_cut_and_marked_as_cut(env):
    data = attach(env, "panjang.txt", b"abc " * 20_000).json()
    assert data["truncated"] is True and data["chars"] == config.MAX_ATTACH_CHARS == len(data["text"])


def test_a_pdf_can_be_attached(env):
    assert "rapat penting" in attach(env, "memo.pdf", make_pdf("rapat penting hari ini")).json()["text"]


@pytest.mark.parametrize(
    ("name", "data", "status"), [("a.exe", b"MZ", 415), ("kosong.txt", b"", 422), ("../x.txt", b"ok", 200)]
)
def test_attachments_follow_the_same_rules_as_uploads(env, name, data, status):
    assert attach(env, name, data).status_code == status


def post_chat(client, content):
    response = client.post("/api/chat", json={"messages": [{"role": "user", "content": content}]})
    return [json.loads(chunk[len("data: ") :]) for chunk in response.text.split("\n\n") if chunk]


def test_the_model_is_told_about_the_attachment_and_does_not_search_for_it(env):
    # the attached text contains the words "cari" and "python"; the demo must still just acknowledge the attachment
    content = 'Tolong baca ini\n\n<attachment name="rapat.txt">\ncari python dokumen\n</attachment>'
    events = post_chat(env.client, content)
    assert not [e for e in events if e["kind"] == "tool_call"]
    answer = "".join(e["text"] for e in events if e["kind"] == "text")
    assert "rapat.txt" in answer and "tidak di-embed" in answer


# ---- pages and startup ----------------------------------------------------------------------------------------------
def test_the_knowledge_base_page_is_served_and_linked_from_the_chat(env):
    page = env.client.get("/kb")
    assert page.status_code == 200 and "Your Knowledge Base" in page.text
    assert 'href="/kb"' in env.client.get("/").text and 'id="attach"' in env.client.get("/").text


def test_uploads_from_an_earlier_run_are_indexed_again_when_the_app_starts(tmp_path, monkeypatch):
    samples, uploads = tmp_path / "samples", tmp_path / "uploads"
    samples.mkdir(), uploads.mkdir()
    (samples / "contoh.md").write_text("Contoh tentang kucing.", encoding="utf-8")
    (uploads / "lama.txt").write_text("Dokumen lama tentang durian montong.", encoding="utf-8")
    (uploads / "lama.pdf").write_bytes(make_pdf("laporan lama tentang rambutan"))
    monkeypatch.setattr(config, "DOCS_DIR", samples)
    monkeypatch.setattr(config, "UPLOAD_DIR", uploads)
    monkeypatch.setattr(config, "VOYAGE_API_KEY", "")  # force the offline demo embedder, whatever the real .env says
    rag.use_store(None)
    try:
        store = rag.get_store()
        assert {r["source"] for r in store.records} == {"contoh.md", "lama.txt", "lama.pdf"}
    finally:
        rag.use_store(None)
