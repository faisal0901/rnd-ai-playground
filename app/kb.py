"""The knowledge base: files you upload on the /kb page. Each one is saved, split into chunks and embedded right away,
so the chat's search_docs tool can find it. (A file attached in the chat is different: it is never stored or embedded.)

Two folders feed it: docs/ (built-in examples, read-only) and data/uploads/ (yours, can be deleted).
"""

from collections import Counter
from pathlib import Path

from app import config
from app.documents import SUPPORTED, DocumentError, extract_text, safe_name
from app.rag import VectorStore


def add_upload(store: VectorStore, filename: str | None, data: bytes, upload_dir: Path, sample_dir: Path) -> dict:
    name = safe_name(filename)
    if len(data) > config.MAX_UPLOAD_BYTES:
        raise DocumentError(f"The file is larger than {config.MAX_UPLOAD_BYTES // (1024 * 1024)} MB.", 413)
    text = extract_text(name, data)
    if len(text) > config.MAX_DOC_CHARS:
        raise DocumentError(f"The text is longer than {config.MAX_DOC_CHARS:,} characters.", 413)
    if (sample_dir / name).exists():
        raise DocumentError(f"A built-in example is already called '{name}'. Rename your file.", 409)

    upload_dir.mkdir(parents=True, exist_ok=True)
    path = upload_dir / name
    existed = path.exists()
    path.write_bytes(data)
    try:
        stored = store.add_document(name, text)  # chunk + embed + save the index; 0 means "same as before"
    except Exception:
        if not existed:
            path.unlink(missing_ok=True)  # do not keep a file the index does not know about
        raise
    return {"name": name, "chunks": _chunks(store)[name], "status": "indexed" if stored else "unchanged"}


def remove_upload(store: VectorStore, name: str, upload_dir: Path, sample_dir: Path) -> dict:
    name = safe_name(name)
    path = upload_dir / name
    if not path.is_file():
        if (sample_dir / name).is_file():
            raise DocumentError("Built-in examples cannot be deleted.", 403)
        raise DocumentError(f"'{name}' is not in your knowledge base.", 404)
    path.unlink()
    return {"name": name, "removed_chunks": store.remove_document(name)}


def list_documents(store: VectorStore, upload_dir: Path, sample_dir: Path) -> list[dict]:
    chunks = _chunks(store)
    rows = []
    for kind, folder in (("sample", sample_dir), ("upload", upload_dir)):
        for file in sorted(folder.iterdir()) if folder.is_dir() else []:
            if file.is_file() and file.suffix.lower() in SUPPORTED:
                rows.append(
                    {"name": file.name, "kind": kind, "chunks": chunks.get(file.name, 0), "bytes": file.stat().st_size}
                )
    return rows


def _chunks(store: VectorStore) -> Counter:
    return Counter(record["source"] for record in list(store.records))
