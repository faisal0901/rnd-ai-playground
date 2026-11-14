"""The tools the model may call. A tool is a JSON schema (what the model sees) plus a function (what runs)."""
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
    }
]


async def run_tool(name: str, tool_input: dict) -> dict:
    """Run one tool call. A wrong call comes back as an error result, so the model can fix it. It never crashes the loop."""
    if name == "run_python":
        code = (tool_input or {}).get("code")
        if not isinstance(code, str) or not code.strip():
            return {"ok": False, "error": "run_python needs a non-empty 'code' string."}
        return await run_python(code)
    return {"ok": False, "error": f"Unknown tool '{name}'."}


def result_for_model(result: dict) -> str:
    """The result as plain text for the model."""
    if "error" in result:
        return f"error: {result['error']}"
    parts = [f"exit code: {result['exit_code']}" + ("  (timed out)" if result["timed_out"] else "")]
    if result["stdout"]:
        parts.append("stdout:\n" + result["stdout"])
    if result["stderr"]:
        parts.append("stderr:\n" + result["stderr"])
    return "\n".join(parts)
