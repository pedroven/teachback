"""The agents teachback installs into, and `teachback setup` / `teachback uninstall`.

Each agent installs teachback its own official way, so a change in one agent only touches its class:
- Claude Code and Codex get the teachback plugin (skill, SessionStart hook and MCP server) through their own plugin
  CLIs. This repo is the marketplace (.claude-plugin/ and .agents/plugins/), and the plugin is its plugin/ folder:
  Codex re-asks to trust the hook whenever any file of the plugin changes, so it holds only what agents load.
  The marketplace follows main, like most plugins, so the agents' own plugin update commands work, and setup runs
  them when the plugin is older than the CLI. `setup --pin` pins it to this version's release tag instead. Neither
  CLI can move a marketplace to another tag, so --pin removes it and adds it again, and then installs the plugin
  again, since Claude Code uninstalls it along with its marketplace.
- OpenCode gets the pairing mode skill copied into its skills folder, a plugin file (opencode.js) copied into its
  plugins folder in place of the hook, and the MCP server registered through `opencode mcp add`. OpenCode has no
  `mcp remove`, so uninstall edits its config file.

Both commands first show the plan: the steps still to do, leaving out what's already done. A symlink is never touched,
since it's likely a dev symlink into this repo.
"""

import json
import os
import re
import shutil
import stat
import subprocess
import sys
import tempfile
from abc import ABC, abstractmethod
from collections.abc import Callable
from functools import partial
from importlib.metadata import version
from pathlib import Path
from typing import NamedTuple

import click

if sys.version_info >= (3, 11):
    import tomllib
else:
    import tomli as tomllib

MARKETPLACE = "pedroven/teachback"  # the GitHub repo
PLUGIN = "teachback@teachback"  # plugin@marketplace
VERSION = version("teachback")
TIMEOUT = 120  # seconds: a marketplace add clones the repo from GitHub
IN_PROJECTS_NOTE = "note: removing the marketplace also uninstalls teachback from the projects that installed it"

WHEEL_SKILL = Path(__file__).parent / "skills" / "teachback"  # pyproject.toml copies it there
REPO_SKILL = Path(__file__).parents[2] / "plugin" / "skills" / "teachback"  # for `uv run` from a checkout
SKILL = WHEEL_SKILL if WHEEL_SKILL.is_dir() else REPO_SKILL
OPENCODE_PLUGIN = Path(__file__).with_name("opencode.js")


class Step(NamedTuple):
    """One line of the plan. A step with nothing to apply is a note for the user."""

    text: str
    apply: Callable[[], object] | None = None


class Agent(ABC):
    """A coding agent teachback installs into."""

    name: str  # what --agent takes
    command: str
    uninstalls_without_cli = False

    def installed(self) -> bool:
        return shutil.which(self.command) is not None

    @abstractmethod
    def setup(self, pin: bool) -> list[Step]:
        """What setup would do, leaving out what's already done."""

    @abstractmethod
    def uninstall(self) -> list[Step]:
        """What uninstall would do, leaving out what's already gone."""


class Installed(NamedTuple):
    """What a plugin agent already has of teachback."""

    marketplace_added: bool
    pinned_to: str | None  # None: follows main
    plugin_version: str | None  # None: not installed
    in_projects: bool = False  # also installed for a project, which removing the marketplace uninstalls


class PluginAgent(Agent):
    """An agent that installs the teachback plugin from the marketplace with its own CLI."""

    add_marketplace: str
    tag_separator: str  # how add_marketplace takes a tag: "#" or "@"
    remove_marketplace: str
    update_marketplace: str
    install_plugin: str
    update_plugin: str
    uninstall_plugin: str
    skill_copy: Path  # where an older setup, or 0.0.3's README by hand, copied the skill

    @abstractmethod
    def state(self) -> Installed:
        """What the agent's CLI says it has."""

    def setup(self, pin: bool) -> list[Step]:
        have = self.state()
        tag = f"v{VERSION}"
        add_marketplace = f"{self.add_marketplace}{self.tag_separator}{tag}" if pin else self.add_marketplace
        if not have.marketplace_added:
            commands = [add_marketplace, self.install_plugin]
        elif pin and have.pinned_to != tag:
            commands = [self.remove_marketplace, add_marketplace, self.install_plugin]
        elif have.plugin_version is None:
            commands = [self.install_plugin]
        elif have.pinned_to is None and older(have.plugin_version, VERSION):
            commands = [self.update_marketplace, self.update_plugin]
        else:
            commands = []
        steps = [cli_step(command) for command in commands]

        if self.remove_marketplace in commands and have.in_projects:
            steps.append(Step(IN_PROJECTS_NOTE))
        if not pin and have.pinned_to not in (None, tag):
            steps.append(
                Step(f"note: the plugin is pinned to {have.pinned_to}. `teachback setup --pin` moves it to {tag}")
            )
        if os.path.lexists(self.skill_copy):  # not deleted: it may be the user's own dev symlink
            steps.append(
                Step(f"note: {tilde(self.skill_copy)} also holds the skill. Delete it, or the skill shows up twice")
            )
        return steps

    def uninstall(self) -> list[Step]:
        if not self.installed():
            return [Step(f"can't check for the teachback plugin: `{self.command}` is not on PATH")]
        have = self.state()
        steps = []
        if have.plugin_version is not None:
            steps.append(cli_step(self.uninstall_plugin))
        if have.marketplace_added:
            steps.append(cli_step(self.remove_marketplace))
            if have.in_projects:
                steps.append(Step(IN_PROJECTS_NOTE))
        return steps


class ClaudeCode(PluginAgent):
    name = "claude-code"
    command = "claude"
    add_marketplace = f"claude plugin marketplace add {MARKETPLACE}"
    tag_separator = "#"
    remove_marketplace = "claude plugin marketplace remove teachback"
    update_marketplace = "claude plugin marketplace update teachback"
    install_plugin = f"claude plugin install {PLUGIN}"
    update_plugin = f"claude plugin update {PLUGIN}"
    uninstall_plugin = f"claude plugin uninstall {PLUGIN}"

    def state(self) -> Installed:
        marketplaces = cli_json("claude plugin marketplace list --json")
        marketplace = next((m for m in marketplaces if m["name"] == "teachback"), None)
        plugins = [p for p in cli_json("claude plugin list --json") if p["id"] == PLUGIN]
        # User scope only, where setup installs: the list also holds project-scope installs from other repos.
        plugin = next((p for p in plugins if p["scope"] == "user"), None)
        return Installed(
            marketplace_added=marketplace is not None,
            pinned_to=marketplace.get("ref") if marketplace else None,
            plugin_version=plugin.get("version", "") if plugin else None,
            in_projects=any(p["scope"] != "user" for p in plugins),
        )

    @property
    def skill_copy(self) -> Path:
        return Path(os.environ.get("CLAUDE_CONFIG_DIR") or Path.home() / ".claude") / "skills" / "teachback"


class Codex(PluginAgent):
    name = "codex"
    command = "codex"
    add_marketplace = f"codex plugin marketplace add {MARKETPLACE}"
    tag_separator = "@"
    remove_marketplace = "codex plugin marketplace remove teachback"
    update_marketplace = "codex plugin marketplace upgrade teachback"
    install_plugin = f"codex plugin add {PLUGIN}"
    update_plugin = install_plugin  # `plugin add` overwrites the installed version
    uninstall_plugin = f"codex plugin remove {PLUGIN}"

    def state(self) -> Installed:
        marketplaces = cli_json("codex plugin marketplace list --json")["marketplaces"]
        added = any(m["name"] == "teachback" for m in marketplaces)
        plugins = cli_json("codex plugin list -m teachback --json")["installed"]  # -m skips the slow remote catalog
        return Installed(
            marketplace_added=added,
            pinned_to=self.pinned_to() if added else None,
            plugin_version=plugins[0].get("version", "") if plugins else None,
        )

    @staticmethod
    def pinned_to() -> str | None:
        """The marketplace's tag, from config.toml: `codex plugin marketplace list` doesn't show it."""
        file = Path(os.environ.get("CODEX_HOME") or Path.home() / ".codex") / "config.toml"
        try:
            config = tomllib.loads(file.read_text(encoding="utf-8"))
        except (OSError, tomllib.TOMLDecodeError):
            return None
        return config.get("marketplaces", {}).get("teachback", {}).get("ref")

    @property
    def skill_copy(self) -> Path:
        return Path.home() / ".agents" / "skills" / "teachback"

    def setup(self, pin: bool) -> list[Step]:
        steps = super().setup(pin)
        if any(step.text == self.install_plugin for step in steps):
            # Only the user can trust a hook. Codex 0.167 asks on start; 0.155 skipped an untrusted hook without a word.
            steps.append(Step("then open Codex, run /hooks, and trust teachback's SessionStart hook"))
        return steps


class OpenCode(Agent):
    name = "opencode"
    command = "opencode"
    uninstalls_without_cli = True
    add_mcp = "opencode mcp add --global teachback -- teachback mcp"  # bare teachback: on PATH, as for the plugin

    @property
    def config_dir(self) -> Path:
        return Path(os.environ.get("XDG_CONFIG_HOME") or Path.home() / ".config") / "opencode"

    @property
    def skill(self) -> Path:
        return self.config_dir / "skills" / "teachback"

    @property
    def plugin(self) -> Path:
        return self.config_dir / "plugins" / "teachback.js"

    def setup(self, pin: bool) -> list[Step]:
        steps = [copy_step(SKILL, self.skill, "skill"), self.plugin_step()]
        registered, unreadable = self.find_mcp()
        if not registered and not unreadable:  # an add to a file teachback can't read couldn't be undone
            steps.append(cli_step(self.add_mcp))
        return [step for step in steps if step] + unreadable

    def uninstall(self) -> list[Step]:
        steps = [remove_step(self.skill), remove_step(self.plugin)]
        registered, unreadable = self.find_mcp()
        steps += [Step(f"remove the teachback MCP server from {tilde(f)}", partial(remove_mcp, f)) for f in registered]
        return [step for step in steps if step] + unreadable

    def plugin_step(self) -> Step | None:
        step = copy_step(OPENCODE_PLUGIN, self.plugin, "plugin")
        # Only a copy or replace: a symlink keeps its own note. opencode.js is written for OpenCode 2's plugin API:
        # OpenCode 1 calls each export as a function and fails to load it.
        if step and step.apply and (version := self.major_version()) < 2:
            found = f"OpenCode {version}" if version else "an unknown version"
            return Step(f"skip the plugin: it needs OpenCode 2 or later, not {found}")
        return step

    def major_version(self) -> int:
        """0 when `opencode --version` doesn't say."""
        try:
            match = re.search(r"(\d+)\.\d+", cli("opencode --version"))
        except (OSError, subprocess.SubprocessError):
            return 0
        return int(match[1]) if match else 0

    def find_mcp(self) -> tuple[list[Path], list[Step]]:
        """(the config files that register teachback's MCP server, a note for each one that can't be read)

        `opencode mcp add` writes to opencode.json or opencode.jsonc, so both are checked.
        """
        registered, unreadable = [], []
        for file in (self.config_dir / "opencode.json", self.config_dir / "opencode.jsonc"):
            try:
                if file.exists() and "teachback" in read_config(file)[1]:
                    registered.append(file)
            except (OSError, ValueError) as e:  # comments, say: never rewrite a file we can't read
                unreadable.append(Step(f"can't read {tilde(file)}, so the MCP server is left as it is: {e}"))
        return registered, unreadable


AGENTS = {agent.name: agent for agent in (ClaudeCode(), Codex(), OpenCode())}


def cli(command: str) -> str:
    """Run an agent's CLI and return its stdout. Raises when it fails, times out, or can't start."""
    # No stdin: a CLI waiting on a prompt gets EOF instead of hanging unseen.
    done = subprocess.run(
        command.split(), stdin=subprocess.DEVNULL, capture_output=True, text=True, check=True, timeout=TIMEOUT
    )
    return done.stdout


def cli_step(command: str) -> Step:
    return Step(command, lambda: cli(command))


def cli_json(command: str):
    """An agent CLI's JSON output. Without it there's no plan, so a failure stops setup or uninstall."""
    try:
        return json.loads(cli(command))
    except (OSError, subprocess.SubprocessError, ValueError) as e:
        raise click.ClickException(f"`{command}` failed: {failure(e)}") from None


def failure(e: Exception) -> str:
    """What went wrong, in the CLI's own words when it printed any."""
    stderr = getattr(e, "stderr", None)  # bytes on a timeout, even with text=True
    return stderr.strip() if isinstance(stderr, str) and stderr.strip() else str(e)


def files_in(folder: Path) -> dict[str, bytes]:
    """Every file under folder, as {relative path: content}. A file is its own one entry."""
    if folder.is_file():
        return {"": folder.read_bytes()}
    return {path.relative_to(folder).as_posix(): path.read_bytes() for path in folder.rglob("*") if path.is_file()}


def older(version: str, than: str) -> bool:
    """Whether version X.Y.Z comes before than. False when either isn't X.Y.Z, say a CLI that lists no version:
    setup can't tell, so it leaves the plugin as it is."""
    try:
        return tuple(map(int, version.split("."))) < tuple(map(int, than.split(".")))
    except ValueError:
        return False


def tilde(path: Path) -> str:
    """path with the home folder written as ~."""
    home = Path.home()
    return f"~/{path.relative_to(home).as_posix()}" if path.is_relative_to(home) else str(path)


def copy_step(source: Path, target: Path, what: str) -> Step | None:
    """Copy source, a folder or a file, to target. None when target already matches it."""
    shown = tilde(target)
    if target.is_symlink():
        return Step(f"leave {shown} alone: it's a symlink")
    if not source.exists():
        # Checked while planning: a replace deletes the old copy first, and there would be nothing to copy back.
        raise click.ClickException(f"this install of teachback has no {what} at {source}. Reinstall teachback.")
    if not target.exists():
        return Step(f"copy the {what} to {shown}", partial(copy, source, target))
    if files_in(target) == files_in(source):
        return None
    return Step(f"replace {shown}: it differs from this version's {what}", partial(replace, source, target))


def remove_step(target: Path) -> Step | None:
    """Remove a copy setup made. None when there's none."""
    if target.is_symlink():
        return Step(f"leave {tilde(target)} alone: it's a symlink")
    if not target.exists():
        return None
    return Step(f"remove {tilde(target)}", partial(delete, target))


def copy(source: Path, target: Path) -> None:
    if source.is_dir():
        shutil.copytree(source, target)
    else:
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, target)


def delete(path: Path) -> None:
    if path.is_dir():
        shutil.rmtree(path)
    else:
        path.unlink()


def replace(source: Path, target: Path) -> None:
    delete(target)
    copy(source, target)


def read_config(file: Path) -> tuple[dict, dict]:
    """An OpenCode config and its MCP servers. Raises ValueError when the file isn't a config teachback can edit."""
    config = json.loads(file.read_text(encoding="utf-8"))
    mcp = config.get("mcp", {}) if isinstance(config, dict) else None
    servers = mcp.get("servers", {}) if isinstance(mcp, dict) else None
    if not isinstance(servers, dict):
        raise ValueError("not the config layout teachback knows")
    return config, servers


def remove_mcp(file: Path) -> None:
    """Delete teachback from an OpenCode config's MCP servers, and the keys that leaves empty."""
    target = file.resolve()  # a symlinked config stays a symlink
    config, servers = read_config(target)  # again: the user may have edited it while Apply? was open
    if "teachback" not in servers:
        return
    del servers["teachback"]
    if not servers:
        del config["mcp"]["servers"]
    if not config["mcp"]:
        del config["mcp"]
    write_atomically(target, json.dumps(config, indent=2, ensure_ascii=False) + "\n")


def write_atomically(file: Path, text: str) -> None:
    """Replace file in one step, keeping its permissions: an OpenCode config may hold API keys."""
    fd, temp = tempfile.mkstemp(dir=file.parent)  # 0600 until the chmod: never readable by others meanwhile
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(text)
        os.chmod(temp, stat.S_IMODE(file.stat().st_mode))
        os.replace(temp, file)  # OpenCode never sees a half-written file
    except BaseException:
        os.unlink(temp)
        raise


def detect(only: str | None, remove: bool) -> list[Agent]:
    """The agents to work on: `only`, or every agent on PATH, plus OpenCode's leftovers when removing."""
    if only:
        agent = AGENTS[only]
        if remove or agent.installed():  # a plugin agent not on PATH then says it can't check
            return [agent]
        raise click.ClickException(f"{only} isn't installed: `{agent.command}` is not on PATH")
    found = [a for a in AGENTS.values() if a.installed() or (remove and a.uninstalls_without_cli)]
    if found or remove:
        return found
    raise click.ClickException("found no supported agent on PATH: " + ", ".join(AGENTS))


def run(*, remove: bool, only: str | None, yes: bool, pin: bool = False) -> int:
    """Show what will change in each agent, ask, then apply. Returns the exit code."""
    todo = []
    for agent in detect(only, remove):
        steps = agent.uninstall() if remove else agent.setup(pin)
        if steps:
            print(agent.name)
        for step in steps:
            print(f"  {step.text}")
        todo += [(agent, step) for step in steps if step.apply]

    if not todo:
        print("Nothing to remove." if remove else "Already set up.")
        return 0
    if not yes and not click.confirm("Apply?"):
        print("Nothing changed.")
        return 1
    ok, stopped = True, set()
    for agent, step in todo:  # a failure doesn't stop the other agents
        if agent in stopped:
            continue
        if not apply(agent, step):
            ok = False
            # A plugin agent's setup steps build on each other: after a failed marketplace add, an install fails too.
            # OpenCode's don't: a failed skill copy still leaves the MCP server to register.
            if not remove and isinstance(agent, PluginAgent):
                stopped.add(agent)
                print(f"stopped {agent.name}: run `teachback setup` again to restore it")
    return 0 if ok else 1


def apply(agent: Agent, step: Step) -> bool:
    """Apply one step and print how it went. False when it failed."""
    try:
        step.apply()
    except (OSError, subprocess.SubprocessError, ValueError) as e:
        print(f"failed  {agent.name}: {step.text}: {failure(e)}")
        return False
    print(f"done    {agent.name}: {step.text}")
    return True
