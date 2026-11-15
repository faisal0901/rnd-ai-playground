"""The web server: the API for the React app in frontend/ (chat, files) and the app itself, once built.
Run it with:  uvicorn app.main:app --reload"""

import asyncio
import json
import mimetypes
from collections.abc import AsyncIterator
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, StreamingResponse
from pydantic import BaseModel

from app import config, kb, rag
from app.agent import Event, run_agent
from app.documents import DocumentError, clip, extract_text, safe_name
from app.llm import LLM, DemoLLM, make_llm


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


def create_app(
    llm: LLM | None = None,
    upload_dir: Path | None = None,
    sample_dir: Path | None = None,
    frontend_dir: Path | None = None,
) -> FastAPI:
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

    serve_frontend(app, frontend_dir or config.FRONTEND_DIR)  # last: its catch-all route must not shadow /api/*
    return app


def serve_frontend(app: FastAPI, dist: Path) -> None:
    """Serve the React app (built with `npm run build` in frontend/). Every path that is not a file or an /api route
    gets index.html, so /chat/<id> and /files work when you reload them."""
    root = dist.resolve()
    # Python asks the OS for file types, and some Windows machines say .js is text/plain. A browser refuses to run a
    # module script served that way, which leaves the page blank. So say it ourselves.
    for suffix, kind in (
        (".js", "text/javascript"),
        (".mjs", "text/javascript"),
        (".css", "text/css"),
        (".woff2", "font/woff2"),
    ):
        mimetypes.add_type(kind, suffix)

    if not (root / "index.html").is_file():

        @app.get("/", include_in_schema=False)
        def not_built() -> HTMLResponse:
            return HTMLResponse(
                "<h1>The frontend is not built yet</h1>"
                "<p>Run <code>cd frontend &amp;&amp; npm install &amp;&amp; npm run build</code> and reload,"
                " or run <code>npm run dev</code> there and open <a href='http://localhost:5173'>localhost:5173</a>.</p>",
                status_code=503,
            )

        return

    @app.get("/{path:path}", include_in_schema=False)
    def frontend(path: str) -> FileResponse:
        if path == "api" or path.startswith("api/"):
            raise HTTPException(404, "Not found")
        file = (root / path).resolve()
        if path and file.is_file() and file.is_relative_to(root):  # a real file: a script, a font, ...
            return FileResponse(file)
        return FileResponse(root / "index.html")


app = create_app()
