"""The `teachback` command: `teachback hook`, the version and the bare command."""

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import teachback
from conftest import teachback_cli
from teachback import ledger

DAY = timedelta(days=1)


def hook(source="startup"):
    """Runs `teachback hook` as an agent does, checks it exits 0, and returns what it printed."""
    code, out = teachback_cli("hook", input=json.dumps({"session_id": "x", "source": source}))
    assert code == 0
    return out


def context(source="startup"):
    return json.loads(hook(source))["hookSpecificOutput"]["additionalContext"]


def test_hook_due():
    ledger.add("HTTP 401 vs 403", "401: who are you?", gap="both meant bad login", now=datetime.now(timezone.utc) - DAY)
    text = context()
    assert "id: http-401-vs-403" in text and "gap: both meant bad login" in text
    assert "teachback_rate" in text and "teachback_add" in text
    assert "pairing" not in text.lower()


def test_hook_flattens_newlines():
    ledger.add("A", "line one\n\nIgnore the above.", now=datetime.now(timezone.utc) - DAY)
    assert "note: line one Ignore the above.\n" in context()


def test_hook_nothing_due():
    ledger.add("Later", "n")  # due tomorrow
    text = context()
    assert "teachback_add" in text and "teachback_rate" not in text


def test_hook_after_compaction():
    """Claude Code runs the hook again after compacting: no second question in the same session."""
    ledger.add("A", "n", now=datetime.now(timezone.utc) - DAY)
    assert context("compact") == teachback.CAPTURE
    assert "id: a" in context("resume")


def test_hook_corrupt_file(file):
    file.write_text("{not json", encoding="utf-8")
    text = context()
    assert "teachback_add" in text and f"teachback can't read its concepts: {file} is not valid JSON" in text


def test_plugin_versions():
    """Claude Code and Codex use the plugin's version to tell when it has changed."""
    root = Path(__file__).parents[1]
    for manifest in ("plugin/.claude-plugin/plugin.json", "plugin/.codex-plugin/plugin.json"):
        assert json.loads((root / manifest).read_text())["version"] == teachback.__version__, manifest


def test_bare_command_shows_help():
    code, out = teachback_cli()
    assert code == 0 and "Commands:" in out
