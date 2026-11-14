import asyncio

from app.agent import MAX_ROUNDS, run_agent


class Scripted:
    """A fake model: each call to stream() plays the next scripted answer (a list of blocks)."""

    def __init__(self, answers):
        self.answers, self.seen = list(answers), []

    async def stream(self, messages, tools, system):
        self.seen.append([dict(m) for m in messages])
        blocks = self.answers.pop(0) if len(self.answers) > 1 else self.answers[0]
        for block in blocks:
            if block["type"] == "text":
                yield {"kind": "text", "text": block["text"]}
        yield {"kind": "message", "content": blocks}


def call(code, id="t1"):
    return {"type": "tool_use", "id": id, "name": "run_python", "input": {"code": code}}


def collect(llm, text="hi"):
    async def go():
        return [event async for event in run_agent(llm, [{"role": "user", "content": text}])]

    return asyncio.run(go())


def test_a_plain_answer_needs_one_round_and_ends_with_the_transcript():
    llm = Scripted([[{"type": "text", "text": "Halo!"}]])
    events = collect(llm)
    assert [e["kind"] for e in events] == ["text", "done"]
    assert events[-1]["messages"][-1] == {"role": "assistant", "content": [{"type": "text", "text": "Halo!"}]}


def test_a_tool_call_runs_the_code_and_the_model_reads_the_result_in_the_next_round():
    llm = Scripted([[call("print(6 * 7)")], [{"type": "text", "text": "Hasilnya 42."}]])
    events = collect(llm)

    assert [e["kind"] for e in events] == ["tool_call", "tool_result", "text", "done"]
    assert events[1]["result"]["stdout"].strip() == "42"
    second_round = llm.seen[1]  # what the model was shown the second time
    result_message = second_round[-1]
    assert result_message["role"] == "user" and result_message["content"][0]["type"] == "tool_result"
    assert result_message["content"][0]["tool_use_id"] == "t1" and "42" in result_message["content"][0]["content"]


def test_a_failing_tool_call_is_given_back_marked_as_an_error():
    llm = Scripted([[call("1/0")], [{"type": "text", "text": "Maaf, ada error."}]])
    collect(llm)
    result = llm.seen[1][-1]["content"][0]
    assert result["is_error"] is True and "ZeroDivisionError" in result["content"]


def test_an_unknown_tool_does_not_crash_the_loop():
    bad = {"type": "tool_use", "id": "t9", "name": "launch_rocket", "input": {}}
    llm = Scripted([[bad], [{"type": "text", "text": "ok"}]])
    events = collect(llm)
    assert events[1]["result"]["ok"] is False and events[-1]["kind"] == "done"


def test_a_model_that_never_stops_calling_tools_is_cut_off():
    llm = Scripted([[call("print(1)")]])  # the same tool call, forever
    events = collect(llm)
    assert events[-1]["kind"] == "error" and str(MAX_ROUNDS) in events[-1]["message"]
    assert sum(1 for e in events if e["kind"] == "tool_call") == MAX_ROUNDS
