"""The tools the model may call. A tool is a JSON schema (what the model sees) plus a handler (what runs).

To add a tool: write an ``async def handler(tool_input: dict) -> dict`` that returns {"ok": ..., ...}, add its schema
to TOOLS, and register the handler in HANDLERS. A handler never raises for a bad call: it returns {"ok": False,
"error": "..."} so the model can read the mistake and try again.
"""

import asyncio
from collections.abc import Awaitable, Callable

from app import config, rag
from app.sandbox import run_python

TOOLS = [
    {
        "name": "run_python",
        "description": "Run Python 3 code in a sandbox and get back stdout, stderr and the exit code. "
        "Use print() to show results. Nothing is kept between calls.",
        "input_schema": {
            "type": "object",
            "properties": {"code": {"type": "string", "description": "The complete Python program."}},
            "required": ["code"],
        },
    },
    {
        "name": "search_docs",
        "description": "Search the user's own documents by meaning and get back the best matching passages with their "
        "source file. Use it for any question about the user's documents; answer only from what it returns.",
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "What to look for, as a short sentence or a few keywords."},
                "k": {
                    "type": "integer",
                    "description": f"How many passages to return (default {config.DEFAULT_HITS}, "
                    f"at most {config.MAX_HITS}).",
                },
            },
            "required": ["query"],
        },
    },
]


async def _run_python(tool_input: dict) -> dict:
    code = tool_input.get("code")
    if not isinstance(code, str) or not code.strip():
        return {"ok": False, "error": "run_python needs a non-empty 'code' string."}
    return await run_python(code)


def _clamp_hits(k: object) -> int:
    """The model picks k; keep it sane. Anything that is not a whole number falls back to the default."""
    if isinstance(k, int) and not isinstance(k, bool):
        return min(max(k, 1), config.MAX_HITS)
    return config.DEFAULT_HITS


async def _search_docs(tool_input: dict) -> dict:
    query = tool_input.get("query")
    if not isinstance(query, str) or not query.strip():
        return {"ok": False, "error": "search_docs needs a non-empty 'query' string."}
    try:
        # Both calls block on the network (embedding the question), so they run in a thread, not on the event loop.
        store = await asyncio.to_thread(rag.get_store)  # the first call builds the store; it may take a moment
        hits = await asyncio.to_thread(store.search, query, _clamp_hits(tool_input.get("k", config.DEFAULT_HITS)))
    except Exception as error:  # a down service must reach the model as an error result, not crash the loop
        return {"ok": False, "error": f"Search failed: {type(error).__name__}: {error}"}
    if not hits:
        return {"ok": False, "error": "No documents are indexed. Put .md or .txt files in the docs/ folder."}
    return {"ok": True, "query": query, "results": hits}


HANDLERS: dict[str, Callable[[dict], Awaitable[dict]]] = {
    "run_python": _run_python,
    "search_docs": _search_docs,
}


async def run_tool(name: str, tool_input: object) -> dict:
    """Run one tool call. A wrong call comes back as an error result; it never crashes the loop."""
    handler = HANDLERS.get(name)
    if handler is None:
        return {"ok": False, "error": f"Unknown tool '{name}'."}
    return await handler(tool_input if isinstance(tool_input, dict) else {})


def result_for_model(result: dict) -> str:
    """The result as plain text for the model."""
    if "error" in result:
        return f"error: {result['error']}"
    if "results" in result:
        return "\n\n".join(
            f"[{n}] {hit['source']} (part {hit['chunk']}, score {hit['score']})\n{hit['text']}"
            for n, hit in enumerate(result["results"], 1)
        )
    parts = [f"exit code: {result['exit_code']}" + ("  (timed out)" if result["timed_out"] else "")]
    if result["stdout"]:
        parts.append("stdout:\n" + result["stdout"])
    if result["stderr"]:
        parts.append("stderr:\n" + result["stderr"])
    return "\n".join(parts)
