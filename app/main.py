"""The web server: the chat page, the knowledge-base page and their endpoints.
Run it with:  uvicorn app.main:app --reload"""

import asyncio
import json
from collections.abc import AsyncIterator
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse
from pydantic import BaseModel

from app import config, kb, rag
from app.agent import Event, run_agent
from app.config import ROOT
from app.documents import DocumentError, clip, extract_text, safe_name
from app.llm import LLM, DemoLLM, make_llm

STATIC = ROOT / "static"


class ChatRequest(BaseModel):
    messages: list  # the whole conversation so far; the server keeps nothing between requests


def sse(event: Event) -> str:
    """One Server-Sent Event: a line "data: {json}" and a blank line."""
    return f"data: {json.dumps(event)}\n\n"


async def read_upload(file: UploadFile) -> bytes:
    """The bytes of an uploaded file, refusing anything over the size limit."""
    data = await file.read(config.MAX_UPLOAD_BYTES + 1)
    if len(data) > config.MAX_UPLOAD_BYTES:
        raise DocumentError(f"The file is larger than {config.MAX_UPLOAD_BYTES // (1024 * 1024)} MB.", 413)
    return data


def create_app(llm: LLM | None = None, upload_dir: Path | None = None, sample_dir: Path | None = None) -> FastAPI:
    app = FastAPI(title="Learn AI Playground")
    app.state.llm = llm or make_llm()
    uploads, samples = upload_dir or config.UPLOAD_DIR, sample_dir or config.DOCS_DIR

    @app.middleware("http")
    async def refuse_huge_uploads(request: Request, call_next):
        """Say no before the body is read, when the client announces a body far over the limit. (A client that lies
        about its size gets through; for a local learning app that is acceptable.)"""
        announced = int(request.headers.get("content-length") or 0)
        if request.method == "POST" and announced > config.MAX_UPLOAD_BYTES + 1024 * 1024:
            return JSONResponse({"detail": "The upload is too large."}, status_code=413)
        return await call_next(request)

    @app.get("/")
    def page() -> FileResponse:
        return FileResponse(STATIC / "index.html")

    @app.get("/kb")
    def knowledge_base_page() -> FileResponse:
        return FileResponse(STATIC / "kb.html")

    @app.get("/api/health")
    def health() -> dict:
        return {"mode": "demo" if isinstance(app.state.llm, DemoLLM) else "model"}

    @app.post("/api/chat")
    async def chat(request: ChatRequest) -> StreamingResponse:
        async def events() -> AsyncIterator[str]:
            try:
                async for event in run_agent(app.state.llm, request.messages):
                    yield sse(event)
            except Exception as error:  # a broken model call becomes a message in the chat, not a dead connection
                yield sse({"kind": "error", "message": f"{type(error).__name__}: {error}"})

        return StreamingResponse(events(), media_type="text/event-stream")

    @app.get("/api/search")
    async def search(q: str, k: int = 5) -> dict:
        """Search the documents without any LLM: the quickest way to see what the scores look like."""
        store = await asyncio.to_thread(rag.get_store)
        return {"query": q, "results": await asyncio.to_thread(store.search, q, max(1, min(k, 20)))}

    @app.post("/api/index")
    async def index() -> dict:
        """Index the docs/ folder again (unchanged files are skipped). Returns {file: chunks stored, 0 = unchanged}."""
        store = await asyncio.to_thread(rag.get_store)
        return await asyncio.to_thread(rag.index_folder, store)

    # ---- knowledge base: uploads here are saved AND embedded, so search_docs can find them -----------------------
    @app.get("/api/kb")
    async def kb_list() -> dict:
        store = await asyncio.to_thread(rag.get_store)
        return {
            "embedder": store.embedder.name,
            "reranker": store.reranker is not None,
            "max_upload_mb": config.MAX_UPLOAD_BYTES // (1024 * 1024),
            "documents": kb.list_documents(store, uploads, samples),
        }

    @app.post("/api/kb")
    async def kb_upload(file: UploadFile) -> dict:
        try:
            data = await read_upload(file)
            store = await asyncio.to_thread(rag.get_store)
            return await asyncio.to_thread(kb.add_upload, store, file.filename, data, uploads, samples)
        except DocumentError as error:
            raise HTTPException(error.status, str(error)) from error
        except Exception as error:  # e.g. the embedding service is down: nothing was saved
            raise HTTPException(502, f"Indexing failed: {type(error).__name__}: {error}") from error

    @app.delete("/api/kb/{name}")
    async def kb_delete(name: str) -> dict:
        try:
            store = await asyncio.to_thread(rag.get_store)
            return await asyncio.to_thread(kb.remove_upload, store, name, uploads, samples)
        except DocumentError as error:
            raise HTTPException(error.status, str(error)) from error

    # ---- chat attachment: read the file, hand the text back, store NOTHING, embed NOTHING -----------------------
    @app.post("/api/attach")
    async def attach(file: UploadFile) -> dict:
        try:
            name = safe_name(file.filename)
            text, cut = clip(extract_text(name, await read_upload(file)))
        except DocumentError as error:
            raise HTTPException(error.status, str(error)) from error
        return {"name": name, "text": text, "chars": len(text), "truncated": cut}

    return app


app = create_app()
