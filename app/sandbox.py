"""Run the Python code the model wrote: in a throwaway folder, with a time limit and a memory limit.

THIS IS NOT A SECURITY BOUNDARY. The code runs as you, on your machine, and can still read your files and use the
network. It is good enough to learn how a code tool works. Exercise 3 in the README swaps it for Docker.

Debugging note: the model's code runs in a separate process, so a breakpoint in it is never hit. Breakpoints in this
file are (the subprocess is started from a worker thread of the server).
"""

import asyncio
import os
import subprocess
import sys
import tempfile
from pathlib import Path

from app.config import (
    SANDBOX_FILE_BYTES,
    SANDBOX_MAX_OUTPUT,
    SANDBOX_MEMORY_BYTES,
    SANDBOX_TIMEOUT_SECONDS,
)

MAX_OUTPUT = SANDBOX_MAX_OUTPUT


def _limit_resources() -> None:
    """Runs inside the child process before the code starts (Linux and macOS only)."""
    import resource

    resource.setrlimit(resource.RLIMIT_CPU, (SANDBOX_TIMEOUT_SECONDS, SANDBOX_TIMEOUT_SECONDS))
    resource.setrlimit(resource.RLIMIT_AS, (SANDBOX_MEMORY_BYTES, SANDBOX_MEMORY_BYTES))
    resource.setrlimit(resource.RLIMIT_FSIZE, (SANDBOX_FILE_BYTES, SANDBOX_FILE_BYTES))


def _clean_env() -> dict[str, str]:
    """Only what Python needs to start. Your API keys and other secrets are NOT passed on."""
    env = {"PATH": os.environ.get("PATH", ""), "PYTHONIOENCODING": "utf-8"}
    if os.name == "nt":
        env["SYSTEMROOT"] = os.environ.get("SYSTEMROOT", "")
    return env


def _clip(text: str | bytes | None) -> str:
    if isinstance(text, bytes):
        text = text.decode("utf-8", errors="replace")
    text = text or ""
    if len(text) <= MAX_OUTPUT:
        return text
    return text[:MAX_OUTPUT] + f"\n... (cut, {len(text)} characters in total)"


def _run(code: str, timeout: int) -> dict:
    with tempfile.TemporaryDirectory() as folder:  # the folder, and everything the code wrote in it, is deleted after
        script = Path(folder) / "main.py"
        script.write_text(code, encoding="utf-8")
        try:
            done = subprocess.run(
                [sys.executable, "-I", str(script)],
                cwd=folder,
                env=_clean_env(),
                capture_output=True,
                text=True,
                timeout=timeout,
                preexec_fn=_limit_resources if os.name == "posix" else None,
            )
        except subprocess.TimeoutExpired as error:
            return {
                "ok": False,
                "timed_out": True,
                "exit_code": None,
                "stdout": _clip(error.stdout),
                "stderr": _clip(error.stderr) or f"Stopped after {timeout} seconds.",
            }
        return {
            "ok": done.returncode == 0,
            "timed_out": False,
            "exit_code": done.returncode,
            "stdout": _clip(done.stdout),
            "stderr": _clip(done.stderr),
        }


async def run_python(code: str, timeout: int = SANDBOX_TIMEOUT_SECONDS) -> dict:
    """Run ``code`` and return {ok, timed_out, exit_code, stdout, stderr}. A thread keeps the server responsive."""
    return await asyncio.to_thread(_run, code, timeout)
