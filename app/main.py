"""The web server: one page, one chat endpoint. Run it with:  uvicorn app.main:app --reload"""
import json
import os

from fastapi import FastAPI
from fastapi.responses import FileResponse, StreamingResponse
from pydantic import BaseModel

from app.agent import run_agent
from app.llm import DemoLLM, make_llm

STATIC = os.path.join(os.path.dirname(__file__), "..", "static")


class ChatRequest(BaseModel):
    messages: list   # the whole conversation so far; the server keeps nothing between requests


def create_app(llm=None) -> FastAPI:
    app = FastAPI(title="Learn AI Playground")
    app.state.llm = llm or make_llm()

    @app.get("/")
    def page():
        return FileResponse(os.path.join(STATIC, "index.html"))

    @app.get("/api/health")
    def health():
        return {"mode": "demo" if isinstance(app.state.llm, DemoLLM) else "model"}

    @app.post("/api/chat")
    async def chat(request: ChatRequest):
        async def events():   # Server-Sent Events: each event is one line  "data: {json}"  and a blank line
            try:
                async for event in run_agent(app.state.llm, request.messages):
                    yield f"data: {json.dumps(event)}\n\n"
            except Exception as error:   # a broken model call becomes a message in the chat, not a dead connection
                yield f"data: {json.dumps({'kind': 'error', 'message': f'{type(error).__name__}: {error}'})}\n\n"

        return StreamingResponse(events(), media_type="text/event-stream")

    return app


app = create_app()
