import asyncio
import os

from app.sandbox import MAX_OUTPUT, run_python


def run(code, **kw):
    return asyncio.run(run_python(code, **kw))


def test_it_returns_what_the_code_printed():
    result = run("print('halo', 1 + 2)")
    assert result["ok"] and result["exit_code"] == 0 and result["stdout"].strip() == "halo 3"


def test_a_crash_comes_back_as_an_error_the_model_can_read():
    result = run("print('before')\nraise ValueError('boom')")
    assert not result["ok"] and result["exit_code"] == 1
    assert "before" in result["stdout"] and "ValueError: boom" in result["stderr"]


def test_code_that_never_ends_is_stopped():
    result = run("while True:\n    pass", timeout=1)
    assert result["timed_out"] and not result["ok"]


def test_a_flood_of_output_is_cut():
    result = run("print('x' * 100000)")
    assert len(result["stdout"]) < MAX_OUTPUT + 100 and "cut" in result["stdout"]


def test_your_secrets_are_not_passed_to_the_code(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-secret-value")
    result = run("import os\nprint(os.environ.get('ANTHROPIC_API_KEY'))")
    assert result["stdout"].strip() == "None"


def test_every_run_starts_in_an_empty_throwaway_folder():
    first = run("import os\nopen('note.txt', 'w').write('hi')\nprint(sorted(os.listdir('.')))")
    second = run("import os\nprint(sorted(os.listdir('.')))")
    assert "note.txt" in first["stdout"]
    assert "note.txt" not in second["stdout"]          # nothing survives between runs
    assert not os.path.exists("note.txt")              # and nothing was written next to your project
