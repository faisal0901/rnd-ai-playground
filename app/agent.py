"""The agent loop (often called ReAct): ask the model; if it wants a tool, run it, show it the result, ask again.

Everything the browser needs is yielded as small events:
    {"kind": "text", "text": "..."}                        a piece of the answer, as it is written
    {"kind": "tool_call", "name", "input"}                 the model asked for a tool
    {"kind": "tool_result", "name", "result"}              what the tool returned
    {"kind": "done", "messages": [...]}                    finished; the full transcript, to send back next turn
    {"kind": "error", "message": "..."}                    something went wrong
"""

from collections.abc import AsyncIterator

from app.config import MAX_ROUNDS
from app.llm import LLM
from app.tools import TOOLS, result_for_model, run_tool

Event = dict

SYSTEM = (
    "You are a helpful assistant in a small learning playground. Answer in the user's language. "
    "When a calculation or a piece of code helps, use the run_python tool instead of guessing, "
    "then explain the result briefly. For questions about the user's own documents, call search_docs and answer only "
    "from the passages it returns, naming the source file. If nothing relevant comes back, say so instead of guessing."
)


async def run_agent(llm: LLM, messages: list[dict]) -> AsyncIterator[Event]:
    messages = list(messages)
    for _ in range(MAX_ROUNDS):
        assistant_content = None
        async for event in llm.stream(messages, TOOLS, SYSTEM):
            if event["kind"] == "text":
                yield event
            elif event["kind"] == "message":
                assistant_content = event["content"]
        if assistant_content is None:
            yield {"kind": "error", "message": "The model returned no message."}
            return
        messages.append({"role": "assistant", "content": assistant_content})

        calls = [block for block in assistant_content if block["type"] == "tool_use"]
        if not calls:  # a plain answer: we are done
            yield {"kind": "done", "messages": messages}
            return

        tool_results = []
        for call in calls:
            yield {"kind": "tool_call", "name": call["name"], "input": call["input"]}
            result = await run_tool(call["name"], call["input"])
            yield {"kind": "tool_result", "name": call["name"], "result": result}
            tool_results.append(
                {
                    "type": "tool_result",
                    "tool_use_id": call["id"],
                    "content": result_for_model(result),
                    "is_error": not result["ok"],
                }
            )
        messages.append({"role": "user", "content": tool_results})  # the model reads the results in the next round

    yield {"kind": "error", "message": f"Stopped after {MAX_ROUNDS} rounds of tool calls."}
