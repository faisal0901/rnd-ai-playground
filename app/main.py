"""The web server: one page, one chat endpoint, two document endpoints. Run it with:  uvicorn app.main:app --reload"""

import asyncio
import json
from collections.abc import AsyncIterator

from fastapi import FastAPI
from fastapi.responses import FileResponse, StreamingResponse
from pydantic import BaseModel

from app import rag
from app.agent import Event, run_agent
from app.config import ROOT
from app.llm import LLM, DemoLLM, make_llm

STATIC = ROOT / "static"


class ChatRequest(BaseModel):
    messages: list  # the whole conversation so far; the server keeps nothing between requests


def sse(event: Event) -> str:
    """One Server-Sent Event: a line "data: {json}" and a blank line."""
    return f"data: {json.dumps(event)}\n\n"


def create_app(llm: LLM | None = None) -> FastAPI:
    app = FastAPI(title="Learn AI Playground")
    app.state.llm = llm or make_llm()

    @app.get("/")
    def page() -> FileResponse:
        return FileResponse(STATIC / "index.html")

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

    return app


app = create_app()
