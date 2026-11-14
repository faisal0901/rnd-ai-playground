"""Talking to a model. Both classes have the same method, so the agent does not care which one it gets:

    async for event in llm.stream(messages, tools, system):
        {"kind": "text", "text": "..."}                    a piece of text as it arrives
        {"kind": "message", "content": [blocks]}           last: the whole answer as blocks, text and/or tool_use
"""
import asyncio
import os

MODEL = os.environ.get("MODEL", "claude-haiku-5-5")


class AnthropicLLM:
    def __init__(self, model: str = MODEL):
        from anthropic import AsyncAnthropic   # imported here so the demo mode works without the package

        self.client, self.model = AsyncAnthropic(), model

    async def stream(self, messages, tools, system):
        async with self.client.messages.stream(
            model=self.model, max_tokens=2048, system=system, messages=messages, tools=tools
        ) as stream:
            async for text in stream.text_stream:
                yield {"kind": "text", "text": text}
            final = await stream.get_final_message()
        blocks = []
        for block in final.content:
            if block.type == "text":
                blocks.append({"type": "text", "text": block.text})
            elif block.type == "tool_use":
                blocks.append({"type": "tool_use", "id": block.id, "name": block.name, "input": block.input})
        yield {"kind": "message", "content": blocks}


class DemoLLM:
    """No API key needed: runs a small Python program when you mention python or counting, otherwise echoes."""

    async def stream(self, messages, tools, system):
        last = messages[-1]
        blocks = []
        if last["role"] == "user" and isinstance(last["content"], list):      # a tool result came back
            blocks = [{"type": "text", "text": "Hasil dari sandbox:\n" + last["content"][0]["content"]}]
        else:
            asked = last["content"] if isinstance(last["content"], str) else ""
            if any(word in asked.lower() for word in ("python", "hitung", "jumlah")):
                blocks = [
                    {"type": "text", "text": "Saya jalankan kode Python dulu. "},
                    {"type": "tool_use", "id": "demo-1", "name": "run_python",
                     "input": {"code": "total = sum(range(1, 101))\nprint('Jumlah 1 sampai 100 =', total)"}},
                ]
            else:
                blocks = [{"type": "text", "text": f"(mode demo, tanpa API key) Kamu menulis: {asked}"}]
        for block in blocks:
            if block["type"] == "text":
                for i in range(0, len(block["text"]), 6):
                    yield {"kind": "text", "text": block["text"][i:i + 6]}
                    await asyncio.sleep(0.015)
        yield {"kind": "message", "content": blocks}


def make_llm():
    """The real model when ANTHROPIC_API_KEY is set, otherwise the demo."""
    return AnthropicLLM() if os.environ.get("ANTHROPIC_API_KEY") else DemoLLM()
