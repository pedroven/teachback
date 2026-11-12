"""`teachback.agents`: `teachback setup` and `teachback uninstall`."""

import json
import os
import shlex
import shutil
import stat
import subprocess
import sys
from pathlib import Path

import pytest
from click.testing import CliRunner

import teachback
from teachback import agents


def teachback_cli(*args, input=None):
    """Runs `teachback ARGS` and returns (exit code, output)."""
    result = CliRunner().invoke(teachback.main, args, input=input)
    return result.exit_code, result.output


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
        if command == "opencode --version":
            return "opencode v2.2.6\n"
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
OPENCODE_PLUGIN = ".config/opencode/plugins/teachback.js"


def changes(calls):
    return [c for c in calls if not c.endswith(("--json", "--version"))]  # every command but the reads


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
    assert set(installed) == {OPENCODE_CONFIG, OPENCODE_PLUGIN} | {
        f".config/opencode/skills/teachback/{name}" for name in tree(agents.SKILL)
    }
    assert installed[OPENCODE_PLUGIN] == agents.OPENCODE_PLUGIN.read_bytes()

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


@pytest.mark.skipif(not shutil.which("node"), reason="needs node")
def test_opencode_plugin(tmp_path):
    """opencode.js with a fake OpenCode: the hook text goes into a root session's every request, from one run."""
    real = Path(sys.executable).with_name("teachback")  # the installed script, which reads stdin to EOF
    if not real.exists():
        pytest.skip("needs the teachback script next to python, as `uv run` installs it")
    bin = tmp_path / "bin"
    bin.mkdir()
    (bin / "teachback").write_text(f'#!/bin/sh\necho run >> "$0.log"\nexec {shlex.quote(str(real))} "$@"\n')
    (bin / "teachback").chmod(0o755)
    text = teachback.context()  # what `teachback hook` prints as additionalContext
    script = """
    const plugin = (await import(process.argv[1])).default;
    const here = { directory: "/repo" };
    const sessions = { root: { location: here }, sub: { parentID: "root", location: here },
                       elsewhere: { location: { directory: "/other" } } };
    let context;
    await plugin.setup({
      location: here,
      session: { get: async ({ sessionID }) => sessions[sessionID], hook: async (_, fn) => { context = fn; } },
    });
    const pushed = [];
    for (const sessionID of ["root", "root", "sub", "elsewhere"]) {
      const system = [];
      await context({ sessionID, system });
      pushed.push(system.map((part) => part.text));
    }
    console.log(JSON.stringify(pushed));
    """

    def run(path):
        node = [shutil.which("node"), "--input-type=module", "-e", script, str(agents.OPENCODE_PLUGIN)]
        env = {"PATH": path, "TEACHBACK_HOME": os.environ["TEACHBACK_HOME"]}
        return subprocess.run(node, capture_output=True, text=True, check=True, env=env, timeout=30).stdout

    assert json.loads(run(str(bin))) == [[text], [text], [], []]
    assert (bin / "teachback.log").read_text() == "run\n"  # once per session, not per request
    assert json.loads(run(str(tmp_path / "empty"))) == [[], [], [], []]  # no teachback on PATH: no text, no crash


@pytest.mark.parametrize(("version", "found"), [("opencode v1.14.30", "OpenCode 1"), ("unknown", "an unknown version")])
def test_opencode_plugin_needs_2(home, monkeypatch, version, found):
    """OpenCode 1 can't load a v2 plugin, so setup leaves it out and says why. The skill and MCP server still go in."""
    monkeypatch.setattr(agents, "cli", lambda command: version if command == "opencode --version" else "")
    code, out = teachback_cli("setup", "--yes", "--agent", "opencode")
    assert code == 0 and f"skip the plugin: it needs OpenCode 2 or later, not {found}\n" in out
    assert not (home / OPENCODE_PLUGIN).exists() and (home / ".config/opencode/skills/teachback").is_dir()


def test_plugin_symlink_left_alone_on_opencode_1(home, monkeypatch):
    """A symlinked plugin keeps its own note on any version, and setup doesn't ask OpenCode for one."""
    monkeypatch.setattr(agents, "cli", lambda command: "opencode v1.14.30" if command == "opencode --version" else "")
    link = home / OPENCODE_PLUGIN
    link.parent.mkdir(parents=True)
    link.symlink_to(agents.OPENCODE_PLUGIN)
    _, out = teachback_cli("setup", "--yes", "--agent", "opencode")
    assert "teachback.js alone: it's a symlink" in out and "skip the plugin" not in out


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


def test_older_plugin_replaced(calls, home):
    plugin = home / OPENCODE_PLUGIN
    plugin.parent.mkdir(parents=True)
    plugin.write_text("// what an older teachback installed\n")
    _, out = teachback_cli("setup", "--yes", "--agent", "opencode")
    assert "replace ~/.config/opencode/plugins/teachback.js: it differs from this version's plugin" in out
    assert plugin.read_bytes() == agents.OPENCODE_PLUGIN.read_bytes()


def test_uninstall_after_opencode(calls, home):
    """OpenCode removed before teachback: uninstall still deletes the files setup copied for it."""
    teachback_cli("setup", "--yes", "--agent", "opencode")
    (home.parent / "bin/opencode").unlink()
    assert teachback_cli("uninstall", "--yes")[0] == 0
    assert not (home / OPENCODE_PLUGIN).exists() and not (home / ".config/opencode/skills/teachback").exists()


def test_setup_asks(calls, home):
    assert teachback_cli("setup", input="n\n")[0] == 1
    assert changes(calls) == [] and tree(home) == {}


def test_agent_not_on_path(home):
    (home.parent / "bin/codex").unlink()
    code, out = teachback_cli("setup", "--agent", "codex")
    assert code == 1 and "codex isn't installed" in out
