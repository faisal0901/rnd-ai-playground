import json

from fastapi.testclient import TestClient

from app.llm import DemoLLM
from app.main import create_app


def post(client, messages):
    response = client.post("/api/chat", json={"messages": messages})
    assert response.headers["content-type"].startswith("text/event-stream")
    return [json.loads(chunk[len("data: ") :]) for chunk in response.text.split("\n\n") if chunk]


def test_the_page_is_served():
    client = TestClient(create_app(DemoLLM()))
    page = client.get("/")
    assert page.status_code == 200 and "Learn AI Playground" in page.text
    assert client.get("/api/health").json() == {"mode": "demo"}


def test_a_chat_streams_events_and_ends_with_the_whole_transcript():
    events = post(TestClient(create_app(DemoLLM())), [{"role": "user", "content": "Halo"}])
    assert "".join(e["text"] for e in events if e["kind"] == "text").startswith("(mode demo")
    assert events[-1]["kind"] == "done" and events[-1]["messages"][0] == {"role": "user", "content": "Halo"}


def test_the_demo_runs_real_code_in_the_sandbox():
    events = post(
        TestClient(create_app(DemoLLM())), [{"role": "user", "content": "hitung jumlah 1 sampai 100 pakai python"}]
    )
    result = next(e for e in events if e["kind"] == "tool_result")["result"]
    assert result["ok"] and "5050" in result["stdout"]


def test_a_model_that_crashes_becomes_an_error_message_not_a_broken_connection():
    class Broken:
        async def stream(self, messages, tools, system):
            raise RuntimeError("the model is down")
            yield  # pragma: no cover

    events = post(TestClient(create_app(Broken())), [{"role": "user", "content": "hi"}])
    assert events[-1]["kind"] == "error" and "the model is down" in events[-1]["message"]
