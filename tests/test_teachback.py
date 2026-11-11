"""The ledger, `teachback hook` and `teachback setup`."""

import json
import shutil
import stat
import sys
import threading
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from click.testing import CliRunner

import teachback
from teachback import agents, ledger

T0 = datetime(2026, 11, 11, 12, tzinfo=timezone.utc)
DAY = timedelta(days=1)


@pytest.fixture
def saved(file):
    """The data dir holding one saved concept."""
    with ledger.edit() as data:
        data["concepts"]["a"] = {"title": "A"}
    return file


def test_round_trip(file):
    assert ledger.load() == {"concepts": {}, "archive": {}}  # no file yet
    with ledger.edit() as data:
        data["concepts"]["injeção"] = {"title": "Injeção", "card": {"due": "2026-11-12T00:00:00+00:00"}}
    assert ledger.load() == data
    assert "Injeção" in file.read_text(encoding="utf-8")  # readable, not \u escapes


def test_error_keeps_file(saved):
    before = saved.read_text(encoding="utf-8")
    with pytest.raises(RuntimeError), ledger.edit() as data:
        data["concepts"].clear()
        raise RuntimeError
    assert saved.read_text(encoding="utf-8") == before


def test_failed_write_leaves_no_temp_file(saved):
    before = saved.read_text(encoding="utf-8")
    with pytest.raises(UnicodeEncodeError), ledger.edit() as data:
        data["concepts"]["bad"] = {"title": "\ud800"}  # lone surrogate: the utf-8 write fails
    assert saved.read_text(encoding="utf-8") == before
    assert sorted(p.name for p in ledger.home().iterdir()) == [".lock", "concepts.json"]


def test_lock():
    def add(i):
        with ledger.edit() as data:
            data["concepts"][f"c{i}"] = {}

    threads = [threading.Thread(target=add, args=(i,)) for i in range(20)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert all(f"c{i}" in ledger.load()["concepts"] for i in range(20))


@pytest.mark.parametrize("bad", [b"{not json", b"\xff{}"], ids=["broken-json", "not-utf8"])
def test_bad_file_named(file, bad):
    file.write_bytes(bad)
    with pytest.raises(ValueError) as e:
        ledger.load()
    assert f"{file} is not valid JSON" in str(e.value)


@pytest.mark.parametrize(
    "title, id",
    [
        ("HTTP 401 vs 403", "http-401-vs-403"),
        ("  http 401 vs. 403!", "http-401-vs-403"),
        ("Injeção de dependência", "injeção-de-dependência"),
    ],
)
def test_slug(title, id):
    assert ledger.slug(title) == id


def test_slug_keeps_symbols_apart():
    ids = {ledger.slug(t) for t in ("C templates", "C++ templates", "C# templates")}
    assert len(ids) == 3, ids


def test_add_then_due_a_day_later():
    id = ledger.add("HTTP 401 vs 403", "401: who are you? 403: I know you, and no.", "demo", "both meant bad login", T0)
    assert id == "http-401-vs-403"
    assert ledger.due(T0) is None
    got_id, concept = ledger.due(T0 + DAY)
    assert got_id == id and concept["gap"] == "both meant bad login"


def test_empty_fields_not_saved():
    ledger.add("No extras", "note", now=T0)
    assert "source" not in ledger.load()["concepts"]["no-extras"]


def test_due_picks_oldest():
    ledger.add("Late", "n", now=T0)
    ledger.add("Early", "n", now=T0 - DAY)
    assert ledger.due(T0 + DAY)[0] == "early"


def test_good_until_archived():
    id = ledger.add("A", "n", now=T0)
    now = T0 + DAY
    for _ in range(1, 15):
        if ledger.rate(id, "good", now) == "archived":
            break
        now = datetime.fromisoformat(ledger.load()["concepts"][id]["card"]["due"])
    else:
        pytest.fail("still not archived after 14 Good reviews")
    data = ledger.load()
    assert id not in data["concepts"]
    # The archived card is the one the last review produced, and it's past the cutoff.
    due = datetime.fromisoformat(data["archive"][id]["card"]["due"])
    assert due - now > ledger.RETIRE_AFTER


def test_again_waits_less_than_good():
    ledger.add("A", "n", now=T0)
    ledger.add("B", "n", now=T0)
    assert ledger.rate("a", "Again", T0 + DAY) < ledger.rate("b", "Good", T0 + DAY)


def test_add_duplicate():
    ledger.add("HTTP 401 vs 403", "n", now=T0)
    with pytest.raises(ValueError, match="already exists"):
        ledger.add("http 401 vs. 403", "n")


def test_add_duplicate_of_archived():
    with ledger.edit() as data:
        data["archive"]["old"] = {"title": "Old"}
    with pytest.raises(ValueError, match="already exists"):
        ledger.add("Old", "n")


def test_add_no_letters():
    with pytest.raises(ValueError, match="no letters"):
        ledger.add("?!", "n")


def test_add_naive_time():
    with pytest.raises(ValueError, match="UTC"):
        ledger.add("Naive", "n", now=datetime(2026, 11, 11))
    assert "naive" not in ledger.load()["concepts"]


@pytest.mark.parametrize(
    "id, rating, message",
    [("nope", "Good", "no concept"), ("a", "meh", "Again, Hard, Good, Easy")],
)
def test_rate_errors(id, rating, message):
    ledger.add("A", "n", now=T0)
    with pytest.raises(ValueError, match=message):
        ledger.rate(id, rating)


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


@pytest.fixture
def home(tmp_path, monkeypatch):
    """A temp HOME, with stub claude, codex and opencode on an otherwise empty PATH."""
    bin = tmp_path / "bin"
    bin.mkdir()
    for name in ("claude", "codex", "opencode"):
        (bin / name).write_text("#!/bin/sh\n")
        (bin / name).chmod(0o755)
    monkeypatch.setenv("PATH", str(bin))
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    # The agents' folders follow HOME only, whatever this machine sets.
    monkeypatch.delenv("CLAUDE_CONFIG_DIR", raising=False)
    monkeypatch.delenv("XDG_CONFIG_HOME", raising=False)
    return tmp_path / "home"


@pytest.fixture
def calls(home, monkeypatch):
    """Fakes the claude and codex plugin CLIs, which remember what they added, and `opencode mcp add`, which writes
    opencode.json as OpenCode does. Returns every command run."""
    calls, added = [], set()  # added: {(agent, "marketplace" or "plugin")}

    def cli(command):
        calls.append(command)
        agent, args = command.split(" ", 1)
        if agent == "opencode":
            file = home / ".config/opencode/opencode.json"
            config = json.loads(file.read_text()) if file.exists() else {}
            server = {"type": "local", "command": ["teachback", "mcp"]}
            config.setdefault("mcp", {}).setdefault("servers", {})["teachback"] = server
            file.parent.mkdir(parents=True, exist_ok=True)
            file.write_text(json.dumps(config, indent=2))
            return ""
        if args == "plugin marketplace list --json":
            names = [{"name": "teachback"}] if (agent, "marketplace") in added else []
            return json.dumps(names if agent == "claude" else {"marketplaces": names})
        if args == "plugin list --json":
            return json.dumps([{"id": agents.PLUGIN, "scope": "user"}] if (agent, "plugin") in added else [])
        if args == "plugin list -m teachback --json":
            return json.dumps({"installed": [{"pluginId": agents.PLUGIN}] if (agent, "plugin") in added else []})
        thing = "marketplace" if "marketplace" in args else "plugin"
        if args.split()[-2] in ("add", "install"):
            added.add((agent, thing))
        else:
            added.discard((agent, thing))
        return ""

    monkeypatch.setattr(agents, "cli", cli)
    return calls


tree = agents.files_in
OPENCODE_CONFIG = ".config/opencode/opencode.json"


def changes(calls):
    return [c for c in calls if not c.endswith("--json")]  # every command but the lists


def test_setup(calls, home):
    code, out = teachback_cli("setup", "--yes")
    assert code == 0 and "trust teachback's SessionStart hook" in out
    assert changes(calls) == [
        "claude plugin marketplace add pedroven/teachback",
        "claude plugin install teachback@teachback",
        "codex plugin marketplace add pedroven/teachback",
        "codex plugin add teachback@teachback",
        "opencode mcp add --global teachback -- teachback mcp",
    ]
    installed = tree(home)
    assert set(installed) == {OPENCODE_CONFIG} | {
        f".config/opencode/skills/teachback/{name}" for name in tree(agents.SKILL)
    }

    calls.clear()
    assert teachback_cli("setup", "--yes") == (0, "Already set up.\n")
    assert changes(calls) == [] and tree(home) == installed

    assert teachback_cli("uninstall", "--yes")[0] == 0
    assert changes(calls) == [
        "claude plugin uninstall teachback@teachback",
        "claude plugin marketplace remove teachback",
        "codex plugin remove teachback@teachback",
        "codex plugin marketplace remove teachback",
    ]
    assert tree(home) == {OPENCODE_CONFIG: b"{}\n"}


def test_uninstall_after_the_agent(calls, home):
    teachback_cli("setup", "--yes")
    (home.parent / "bin/claude").unlink()  # the user removed Claude Code before teachback
    calls.clear()
    code, out = teachback_cli("uninstall", "--yes")
    assert code == 0 and "claude" not in out  # skipped quietly: most people never had every agent
    assert not [c for c in calls if c.startswith("claude")]
    assert tree(home) == {OPENCODE_CONFIG: b"{}\n"}

    _, out = teachback_cli("uninstall", "--yes", "--agent", "claude-code")
    # Named: not a bare "Nothing to remove."
    assert "can't check for the teachback plugin: `claude` is not on PATH" in out


def test_agent_cli_fails(home):
    """The real subprocess path: a failing list stops setup, and a failing marketplace add is reported."""
    claude = home.parent / "bin/claude"
    claude.write_text("#!/bin/sh\necho 'not logged in' >&2\nexit 1\n")
    code, out = teachback_cli("setup", "--yes", "--agent", "claude-code")
    assert code == 1 and "`claude plugin marketplace list --json` failed: not logged in" in out

    claude.write_text('#!/bin/sh\ncase "$*" in *list*) echo "[]" ;; *) echo "no network" >&2; exit 1 ;; esac\n')
    code, out = teachback_cli("setup", "--yes", "--agent", "claude-code")
    assert code == 1
    assert "failed  claude-code: claude plugin marketplace add pedroven/teachback: no network" in out


def test_agent_cli_times_out(home, monkeypatch):
    monkeypatch.setattr(agents, "TIMEOUT", 0.2)
    (home.parent / "bin/claude").write_text(f"#!{sys.executable}\nimport time\ntime.sleep(5)\n")  # PATH has no sleep
    code, out = teachback_cli("setup", "--yes", "--agent", "claude-code")
    assert code == 1 and "timed out after 0.2 seconds" in out


def test_project_scope_install_is_not_enough(home, monkeypatch):
    """Installed for another repo only: setup still installs it for the user."""
    lists = {
        "claude plugin marketplace list --json": [{"name": "teachback"}],
        "claude plugin list --json": [{"id": agents.PLUGIN, "scope": "project"}],
    }
    monkeypatch.setattr(agents, "cli", lambda command: json.dumps(lists.get(command)))
    _, out = teachback_cli("setup", "--yes", "--agent", "claude-code")
    assert "done    claude-code: claude plugin install teachback@teachback" in out


def test_older_skill_copy_noted(calls, home):
    (home / ".claude/skills/teachback").mkdir(parents=True)  # what 0.0.3's README had you copy
    _, out = teachback_cli("setup", "--yes", "--agent", "claude-code")
    assert "note: ~/.claude/skills/teachback also holds the skill" in out
    assert (home / ".claude/skills/teachback").is_dir()  # reported, never deleted


def test_plugin_versions():
    """Claude Code and Codex use the plugin's version to tell when it has changed."""
    root = Path(__file__).parents[1]
    for manifest in (".claude-plugin/plugin.json", ".codex-plugin/plugin.json"):
        assert json.loads((root / manifest).read_text())["version"] == teachback.__version__, manifest


def test_opencode_mcp_round_trip(calls, home, tmp_path):
    """The user's other keys and servers stay as they were, and uninstall gives back the same JSON.

    The config is a symlink to a private file, as in a dotfiles repo: both survive.
    """
    real = tmp_path / "dotfiles/opencode.json"
    real.parent.mkdir()
    original = {"model": "m", "mcp": {"servers": {"ai-memory": {"type": "remote", "url": "http://127.0.0.1:1/mcp"}}}}
    real.write_text(json.dumps(original))
    real.chmod(0o640)
    file = home / OPENCODE_CONFIG
    file.parent.mkdir(parents=True)
    file.symlink_to(real)
    teachback_cli("setup", "--yes", "--agent", "opencode")
    teachback_cli("setup", "--yes", "--agent", "opencode")
    assert changes(calls) == ["opencode mcp add --global teachback -- teachback mcp"]  # once: then it's registered

    _, out = teachback_cli("uninstall", "--yes", "--agent", "opencode")
    assert "done    opencode: remove the teachback MCP server from ~/.config/opencode/opencode.json" in out
    assert file.is_symlink() and json.loads(real.read_text()) == original
    assert stat.S_IMODE(real.stat().st_mode) == 0o640


def test_opencode_jsonc(calls, home):
    """`opencode mcp add` writes to opencode.jsonc when that's the only config: setup sees it, uninstall removes it."""
    file = home / ".config/opencode/opencode.jsonc"
    file.parent.mkdir(parents=True)
    file.write_text(json.dumps({"mcp": {"servers": {"teachback": {"type": "local"}}}}))
    assert teachback_cli("setup", "--yes", "--agent", "opencode")[0] == 0
    assert changes(calls) == []
    _, out = teachback_cli("uninstall", "--yes", "--agent", "opencode")
    assert "done    opencode: remove the teachback MCP server from ~/.config/opencode/opencode.jsonc" in out
    assert json.loads(file.read_text()) == {}


@pytest.mark.parametrize(
    "text",
    [
        '{"mcp": {"servers": {"teachback": {}}}, // a comment\n}',
        "null",
        "[]",
        '{"mcp": null}',
        '{"mcp": {"servers": []}}',
    ],
)
def test_opencode_config_unreadable(calls, home, text):
    """Reported and never rewritten, and it doesn't stop the other agents."""
    file = home / OPENCODE_CONFIG
    file.parent.mkdir(parents=True)
    file.write_text(text)
    for command in ("setup", "uninstall"):
        code, out = teachback_cli(command, "--yes")
        assert code == 0 and "can't read ~/.config/opencode/opencode.json, so the MCP server is left as it is" in out
    assert file.read_text() == text
    assert not [c for c in changes(calls) if c.startswith("opencode")]


def test_config_changed_while_asking(calls, home, monkeypatch):
    """The user broke opencode.json while Apply? was open: reported, not a traceback, and left alone."""
    file = home / OPENCODE_CONFIG
    file.parent.mkdir(parents=True)
    file.write_text(json.dumps({"mcp": {"servers": {"teachback": {}}}}))
    monkeypatch.setattr(agents.click, "confirm", lambda _: file.write_text('{"mcp": null}') or True)
    code, out = teachback_cli("uninstall", "--agent", "opencode")
    assert code == 1 and "failed  opencode: remove the teachback MCP server" in out
    assert file.read_text() == '{"mcp": null}'


def test_symlink_left_alone(home, tmp_path):
    link = home / ".config/opencode/skills/teachback"
    link.parent.mkdir(parents=True)
    link.symlink_to(tmp_path)
    for command in ("setup", "uninstall"):
        _, out = teachback_cli(command, "--yes", "--agent", "opencode")
        assert "symlink" in out
        assert link.readlink() == tmp_path


@pytest.fixture
def older_copy(home):
    """What an older teachback installed for OpenCode: the same files, but SKILL.md has changed since."""
    folder = home / ".config/opencode/skills/teachback"
    shutil.copytree(agents.SKILL, folder)
    with open(folder / "SKILL.md", "a", encoding="utf-8") as f:
        f.write("A line this version dropped.\n")
    return folder


def test_older_copy_replaced(older_copy):
    code, out = teachback_cli("setup", "--yes", "--agent", "opencode")
    assert code == 0 and "replace ~/.config/opencode/skills/teachback" in out
    assert tree(older_copy) == tree(agents.SKILL)


def test_replace_drops_old_files(older_copy):
    (older_copy / "OLD.md").write_text("a file this version no longer ships")
    teachback_cli("setup", "--yes", "--agent", "opencode")
    assert not (older_copy / "OLD.md").exists()


def test_missing_skill_keeps_the_old_copy(older_copy, tmp_path, monkeypatch):
    monkeypatch.setattr(agents, "SKILL", tmp_path / "nowhere")  # a broken install
    before = tree(older_copy)
    code, out = teachback_cli("setup", "--yes", "--agent", "opencode")
    assert code == 1 and "Reinstall teachback" in out
    assert tree(older_copy) == before


def test_setup_asks(calls, home):
    assert teachback_cli("setup", input="n\n")[0] == 1
    assert changes(calls) == [] and tree(home) == {}


def test_agent_not_on_path(home):
    (home.parent / "bin/codex").unlink()
    code, out = teachback_cli("setup", "--agent", "codex")
    assert code == 1 and "codex isn't installed" in out


def test_bare_command_shows_help():
    code, out = teachback_cli()
    assert code == 0 and "Commands:" in out
