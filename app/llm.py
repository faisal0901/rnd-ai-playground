"""Talking to a model. Both classes have the same method, so the agent does not care which one it gets:

async for event in llm.stream(messages, tools, system):
    {"kind": "text", "text": "..."}                    a piece of text as it arrives
    {"kind": "message", "content": [blocks]}           last: the whole answer as blocks, text and/or tool_use
"""

import asyncio
import re
from collections.abc import AsyncIterator
from typing import Protocol

from app import config


class LLM(Protocol):
    def stream(self, messages: list[dict], tools: list[dict], system: str) -> AsyncIterator[dict]: ...


class AnthropicLLM:
    def __init__(self, model: str = config.MODEL):
        from anthropic import AsyncAnthropic  # imported here so the demo mode works without the package

        self.client = AsyncAnthropic()
        self.model = model

    async def stream(self, messages: list[dict], tools: list[dict], system: str) -> AsyncIterator[dict]:
        async with self.client.messages.stream(
            model=self.model, max_tokens=config.MAX_TOKENS, system=system, messages=messages, tools=tools
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
    """No API key needed. Runs a small Python program for "python"/"hitung"/"jumlah", searches the documents for
    "cari"/"dokumen", and otherwise echoes. Not a real model: it only shows how the loop and the tools fit together."""

    async def stream(self, messages: list[dict], tools: list[dict], system: str) -> AsyncIterator[dict]:
        blocks = self._answer(messages[-1])
        for block in blocks:
            if block["type"] == "text":
                for i in range(0, len(block["text"]), 6):  # a few characters at a time, like a real stream
                    yield {"kind": "text", "text": block["text"][i : i + 6]}
                    await asyncio.sleep(0.015)
        yield {"kind": "message", "content": blocks}

    @staticmethod
    def _answer(last: dict) -> list[dict]:
        if last["role"] == "user" and isinstance(last["content"], list):  # a tool result came back
            return [{"type": "text", "text": "Hasil dari tool:\n" + last["content"][0]["content"]}]
        asked = last["content"] if isinstance(last["content"], str) else ""
        attached = re.findall(r'<attachment name="([^"]+)">', asked)
        if attached:  # check first: the attached text may itself contain words like "python" or "cari"
            names = ", ".join(attached)
            return [
                {
                    "type": "text",
                    "text": f"(mode demo) Lampiran diterima: {names}. Model asli membacanya langsung dari percakapan "
                    "ini. Lampiran tidak disimpan dan tidak di-embed; untuk itu pakai halaman Knowledge base.",
                }
            ]
        words = asked.lower()
        if any(word in words for word in ("python", "hitung", "jumlah")):
            code = "total = sum(range(1, 101))\nprint('Jumlah 1 sampai 100 =', total)"
            return [
                {"type": "text", "text": "Saya jalankan kode Python dulu. "},
                {"type": "tool_use", "id": "demo-1", "name": "run_python", "input": {"code": code}},
            ]
        if any(word in words for word in ("cari", "dokumen")):
            return [
                {"type": "text", "text": "Saya cari di dokumen dulu. "},
                {"type": "tool_use", "id": "demo-2", "name": "search_docs", "input": {"query": asked, "k": 2}},
            ]
        return [{"type": "text", "text": f"(mode demo, tanpa API key) Kamu menulis: {asked}"}]


def make_llm() -> LLM:
    """The real model when ANTHROPIC_API_KEY is set, otherwise the demo."""
    return AnthropicLLM() if config.ANTHROPIC_API_KEY else DemoLLM()
