"""The `teachback` command: `teachback hook`, the version and the bare command."""

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

from click.testing import CliRunner

import teachback
from teachback import ledger

DAY = timedelta(days=1)


def teachback_cli(*args, input=None):
    """Runs `teachback ARGS` and returns (exit code, output)."""
    result = CliRunner().invoke(teachback.main, args, input=input)
    return result.exit_code, result.output


def hook():
    """Runs `teachback hook` as an agent does, checks it exits 0, and returns what it printed."""
    code, out = teachback_cli("hook", input='{"session_id": "x"}')
    assert code == 0
    return out


def context():
    return json.loads(hook())["hookSpecificOutput"]["additionalContext"]


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


def test_hook_corrupt_file(file):
    file.write_text("{not json", encoding="utf-8")
    assert hook() == ""


def test_plugin_versions():
    """Claude Code and Codex use the plugin's version to tell when it has changed."""
    root = Path(__file__).parents[1]
    for manifest in (".claude-plugin/plugin.json", ".codex-plugin/plugin.json"):
        assert json.loads((root / manifest).read_text())["version"] == teachback.__version__, manifest


def test_bare_command_shows_help():
    code, out = teachback_cli()
    assert code == 0 and "Commands:" in out
