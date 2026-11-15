import json

from fastapi.testclient import TestClient

from app.llm import DemoLLM
from app.main import create_app


def post(client, messages):
    response = client.post("/api/chat", json={"messages": messages})
    assert response.headers["content-type"].startswith("text/event-stream")
    return [json.loads(chunk[len("data: ") :]) for chunk in response.text.split("\n\n") if chunk]


def test_the_built_frontend_is_served_and_deep_links_get_the_app(tmp_path):
    dist = tmp_path / "dist"
    (dist / "assets").mkdir(parents=True)
    (dist / "index.html").write_text("<title>Nara</title>", encoding="utf-8")
    (dist / "assets" / "app.js").write_text("console.log(1)", encoding="utf-8")
    (tmp_path / "secret.txt").write_text("top secret", encoding="utf-8")
    client = TestClient(create_app(DemoLLM(), frontend_dir=dist))

    for path in ("/", "/files", "/chat/abc123"):  # the router lives in the browser: reloading these must work
        assert "<title>Nara</title>" in client.get(path).text
    script = client.get("/assets/app.js")
    assert script.text == "console.log(1)"
    assert "javascript" in script.headers["content-type"]  # text/plain would make the browser refuse to run it
    assert client.get("/api/health").json() == {"mode": "demo"}  # real API routes still win
    assert client.get("/api/does-not-exist").status_code == 404  # and an unknown one is not answered with the app
    assert "top secret" not in client.get("/..%2fsecret.txt").text  # nothing outside the build folder


def test_without_a_build_the_root_says_how_to_build_it(tmp_path):
    client = TestClient(create_app(DemoLLM(), frontend_dir=tmp_path))
    page = client.get("/")
    assert page.status_code == 503 and "npm run build" in page.text
    assert client.get("/api/health").status_code == 200


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
