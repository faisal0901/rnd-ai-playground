import asyncio
import functools
import json

import pytest
from fastapi.testclient import TestClient

from app import rag
from app.agent import run_agent
from app.embeddings import DemoEmbedder
from app.llm import DemoLLM
from app.main import create_app
from app.tools import result_for_model, run_tool


def sync(test):
    """Run an async test with asyncio.run, like test_agent.py does; no pytest plugin needed."""

    @functools.wraps(test)
    def wrapper(*args, **kwargs):
        return asyncio.run(test(*args, **kwargs))

    return wrapper


@pytest.fixture(autouse=True)
def isolated_store():
    store = rag.VectorStore(DemoEmbedder())
    store.add_document("kopi.md", "Kopi terasa pahit kalau air terlalu panas. Turunkan suhu air.")
    store.add_document("kucing.md", "Kucing makan dua kali sehari dan butuh air bersih.")
    rag.use_store(store)
    yield store
    rag.use_store(None)


@sync
async def test_search_docs_returns_passages_with_their_source():
    result = await run_tool("search_docs", {"query": "kopi pahit"})
    assert result["ok"] and result["results"][0]["source"] == "kopi.md"


@pytest.mark.parametrize("bad", [{}, {"query": ""}, {"query": "   "}, {"query": 5}, None])
@sync
async def test_a_bad_call_is_an_error_result_the_model_can_read(bad):
    result = await run_tool("search_docs", bad)
    assert result["ok"] is False and "query" in result["error"]


@pytest.mark.parametrize("k, expected", [(1, 1), (0, 1), (-3, 1), (500, 2), ("lima", 2), (True, 2), (None, 2)])
@sync
async def test_the_model_cannot_ask_for_a_silly_number_of_results(k, expected):
    result = await run_tool("search_docs", {"query": "air", "k": k})
    assert (
        result["ok"] and len(result["results"]) == expected
    )  # two chunks exist; 'k' is clamped to 1..10, bad types -> 5


@sync
async def test_an_empty_index_says_so_instead_of_returning_nothing():
    rag.use_store(rag.VectorStore(DemoEmbedder()))
    result = await run_tool("search_docs", {"query": "apa saja"})
    assert result["ok"] is False and "docs/" in result["error"]


@sync
async def test_a_broken_search_becomes_an_error_result_not_a_crash():
    class Broken:
        def search(self, query, k):
            raise ConnectionError("voyage is down")

    rag.use_store(Broken())
    result = await run_tool("search_docs", {"query": "x"})
    assert result["ok"] is False and "ConnectionError" in result["error"] and "voyage is down" in result["error"]


def test_the_model_reads_the_hits_as_numbered_passages_with_sources():
    text = result_for_model(
        {
            "ok": True,
            "results": [
                {"source": "kopi.md", "chunk": 0, "score": 0.81, "text": "Isi satu"},
                {"source": "kucing.md", "chunk": 2, "score": 0.4, "text": "Isi dua"},
            ],
        }
    )
    assert text.startswith("[1] kopi.md (part 0, score 0.81)\nIsi satu")
    assert "[2] kucing.md (part 2, score 0.4)\nIsi dua" in text


@sync
async def test_the_agent_calls_the_tool_and_feeds_the_passages_back_to_the_model():
    events = [e async for e in run_agent(DemoLLM(), [{"role": "user", "content": "cari di dokumen kopi pahit"}])]
    call = next(e for e in events if e["kind"] == "tool_call")
    assert call["name"] == "search_docs" and call["input"] == {"query": "cari di dokumen kopi pahit", "k": 2}
    result = next(e for e in events if e["kind"] == "tool_result")["result"]
    assert result["ok"] and result["results"][0]["source"] == "kopi.md"
    done = events[-1]
    assert done["kind"] == "done"
    fed_back = done["messages"][2]["content"][0]  # what the model read in the next round
    assert fed_back["is_error"] is False and "kopi.md" in fed_back["content"]


def test_the_search_endpoint_shows_scores_without_any_llm():
    client = TestClient(create_app(DemoLLM()))
    hits = client.get("/api/search", params={"q": "kucing makan", "k": 1}).json()["results"]
    assert len(hits) == 1 and hits[0]["source"] == "kucing.md" and isinstance(hits[0]["score"], float)


def test_the_index_endpoint_reports_what_it_stored_and_what_it_skipped(isolated_store):
    client = TestClient(create_app(DemoLLM()))
    first = client.post("/api/index").json()
    assert first and all(isinstance(n, int) for n in first.values())
    assert set(client.post("/api/index").json().values()) == {0}  # the second call changes nothing


def test_a_chat_through_the_api_streams_the_search_tool_events():
    client = TestClient(create_app(DemoLLM()))
    response = client.post("/api/chat", json={"messages": [{"role": "user", "content": "cari dokumen tentang kucing"}]})
    events = [json.loads(chunk[len("data: ") :]) for chunk in response.text.split("\n\n") if chunk]
    assert [e["kind"] for e in events if e["kind"] in ("tool_call", "tool_result", "done")] == [
        "tool_call",
        "tool_result",
        "done",
    ]
