"""The agents teachback installs into, and `teachback setup` / `teachback uninstall`.

Each agent installs teachback its own official way, so a change in one agent only touches its class:
- Claude Code and Codex get the teachback plugin (skill and SessionStart hook) through their own plugin CLIs.
  This repo is the marketplace: see .claude-plugin/ and .agents/plugins/.
- OpenCode installs JS plugin packages (`opencode plugin add`), and teachback has none yet, so the pairing mode skill
  is copied into OpenCode's skills folder.
"""

import json
import os
import shutil
import subprocess
from abc import ABC, abstractmethod
from collections.abc import Callable
from pathlib import Path
from typing import NamedTuple

import click

MARKETPLACE = "pedroven/teachback"  # the GitHub repo, which both agents' marketplace commands accept
PLUGIN = "teachback@teachback"  # plugin@marketplace, named in plugin.json and marketplace.json
TIMEOUT = 120  # seconds an agent CLI gets: a marketplace add clones the repo from GitHub

# The pairing mode skill, for OpenCode. Installed from the wheel, it sits next to this file (pyproject.toml copies it
# there). Run from a repo checkout (`uv run`), it is only in the repo's top-level skills/ folder.
SKILL = Path(__file__).parent / "skills" / "teachback"
if not SKILL.is_dir():
    SKILL = Path(__file__).parents[2] / "skills" / "teachback"


class Step(NamedTuple):
    text: str  # what the plan shows
    apply: Callable[[], object] | None = None  # None: only reported, nothing to change


class Agent(ABC):
    """A coding agent teachback installs into."""

    name: str  # what --agent takes
    command: str  # on PATH when the agent is installed

    def installed(self) -> bool:
        return shutil.which(self.command) is not None

    @abstractmethod
    def plan(self, remove: bool) -> list[Step]:
        """What setup (or uninstall, when remove) would do for this agent. Leaves out what's already done.

        A step with no apply is only shown, like a note the user has to act on.
        """


class PluginAgent(Agent):
    """An agent that installs the teachback plugin from the marketplace with its own CLI.

    A subclass gives its four commands and says what is already there.
    """

    add_marketplace: str
    install_plugin: str
    uninstall_plugin: str
    remove_marketplace: str

    @abstractmethod
    def state(self) -> tuple[bool, bool]:
        """(the teachback marketplace is added, the plugin is installed)"""

    @property
    @abstractmethod
    def skill_copy(self) -> Path:
        """Where a copy of the skill made by hand (0.0.3's README) or by an older setup would be."""

    def plan(self, remove: bool) -> list[Step]:
        if not self.installed():
            # Only reached by `uninstall --agent NAME`: detect() leaves out plugin agents not on PATH otherwise.
            # Without its CLI, the plugin can't be checked or removed the official way, so say so.
            return [Step(f"can't check for the teachback plugin: `{self.command}` is not on PATH")]

        has_marketplace, has_plugin = self.state()
        commands = []
        # The plugin comes from the marketplace: add the marketplace first, and remove it last.
        if remove:
            if has_plugin:
                commands.append(self.uninstall_plugin)
            if has_marketplace:
                commands.append(self.remove_marketplace)
        else:
            if not has_marketplace:
                commands.append(self.add_marketplace)
            if not has_plugin:
                commands.append(self.install_plugin)
        steps = [cli_step(command) for command in commands]

        copy = self.skill_copy
        if not remove and (copy.exists() or copy.is_symlink()):
            # Not deleted: it may be the user's own dev symlink. Left there, the agent lists the skill twice.
            steps.append(Step(f"note: {tilde(copy)} also holds the skill. Delete it, or the skill shows up twice"))
        return steps


class ClaudeCode(PluginAgent):
    name = "claude-code"
    command = "claude"
    add_marketplace = f"claude plugin marketplace add {MARKETPLACE}"
    install_plugin = f"claude plugin install {PLUGIN}"
    uninstall_plugin = f"claude plugin uninstall {PLUGIN}"
    remove_marketplace = "claude plugin marketplace remove teachback"

    def state(self) -> tuple[bool, bool]:
        marketplaces = cli_json("claude plugin marketplace list --json")
        # User scope only, where setup installs: the list also holds project-scope installs from other repos.
        plugins = [p for p in cli_json("claude plugin list --json") if p["scope"] == "user"]
        return any(m["name"] == "teachback" for m in marketplaces), any(p["id"] == PLUGIN for p in plugins)

    @property
    def skill_copy(self) -> Path:
        return Path(os.environ.get("CLAUDE_CONFIG_DIR") or Path.home() / ".claude") / "skills" / "teachback"


class Codex(PluginAgent):
    name = "codex"
    command = "codex"
    add_marketplace = f"codex plugin marketplace add {MARKETPLACE}"
    install_plugin = f"codex plugin add {PLUGIN}"
    uninstall_plugin = f"codex plugin remove {PLUGIN}"
    remove_marketplace = "codex plugin marketplace remove teachback"

    def state(self) -> tuple[bool, bool]:
        marketplaces = cli_json("codex plugin marketplace list --json")["marketplaces"]
        # -m: without it, Codex also asks its remote catalog, which can take minutes
        plugins = cli_json("codex plugin list -m teachback --json")["installed"]
        return any(m["name"] == "teachback" for m in marketplaces), bool(plugins)

    @property
    def skill_copy(self) -> Path:
        return Path.home() / ".agents" / "skills" / "teachback"

    def plan(self, remove: bool) -> list[Step]:
        steps = super().plan(remove)
        if any(step.text == self.install_plugin for step in steps):
            # Codex skips an untrusted hook without a word, and only the user can trust it.
            steps.append(Step("then open Codex, run /hooks, and trust teachback's SessionStart hook"))
        return steps


class OpenCode(Agent):
    name = "opencode"
    command = "opencode"

    @property
    def skills_dir(self) -> Path:
        return Path(os.environ.get("XDG_CONFIG_HOME") or Path.home() / ".config") / "opencode" / "skills"

    def plan(self, remove: bool) -> list[Step]:
        step = self.skill_step(remove)
        return [step] if step else []

    def skill_step(self, remove: bool) -> Step | None:
        """Copy the skill into the skills folder, or remove it. None when there's nothing to do."""
        folder = self.skills_dir / "teachback"
        shown = tilde(folder)

        if folder.is_symlink():
            # Likely a dev symlink into this repo: never replace or delete it.
            return Step(f"leave {shown} alone: it's a symlink")

        if remove:
            if not folder.exists():
                return None
            return Step(f"remove {shown}", lambda: shutil.rmtree(folder))

        if not SKILL.is_dir():
            # Checked while planning: a replace deletes the old copy first, and there would be nothing to copy back.
            raise click.ClickException(f"this install of teachback has no skill at {SKILL}. Reinstall teachback.")
        if not folder.exists():
            return Step(f"copy the skill to {shown}", lambda: shutil.copytree(SKILL, folder))
        if files_in(folder) == files_in(SKILL):
            return None  # already installed
        return Step(f"replace {shown}: it differs from this version's skill", lambda: replace_skill(folder))


AGENTS = {agent.name: agent for agent in (ClaudeCode(), Codex(), OpenCode())}


def cli(command: str) -> str:
    """Run an agent's CLI and return its stdout.

    Raises CalledProcessError, holding the CLI's stderr, when it fails, TimeoutExpired when it takes over TIMEOUT
    seconds, and OSError when it can't start.
    """
    # No stdin: the output is captured, so a CLI waiting on a prompt would look frozen. It gets EOF instead.
    done = subprocess.run(
        command.split(), stdin=subprocess.DEVNULL, capture_output=True, text=True, check=True, timeout=TIMEOUT
    )
    return done.stdout


def cli_step(command: str) -> Step:
    """A step that runs an agent's CLI. The plan shows the command itself."""
    return Step(command, lambda: cli(command))


def cli_json(command: str):
    """An agent CLI's JSON output. Stops setup or uninstall if the command fails: without it there's no plan."""
    try:
        return json.loads(cli(command))
    except (OSError, subprocess.SubprocessError, ValueError) as e:
        raise click.ClickException(f"`{command}` failed: {failure(e)}") from None


def failure(e: Exception) -> str:
    """What went wrong, in the CLI's own words when it printed any."""
    stderr = getattr(e, "stderr", None)  # bytes on a timeout, even with text=True
    return stderr.strip() if isinstance(stderr, str) and stderr.strip() else str(e)


def files_in(folder: Path) -> dict[str, bytes]:
    """Every file under folder, as {relative path: content}."""
    files = {}
    for path in folder.rglob("*"):
        if path.is_file():
            files[path.relative_to(folder).as_posix()] = path.read_bytes()
    return files


def tilde(path: Path) -> str:
    """path as the plan shows it, with the home folder written as ~."""
    home = Path.home()
    return f"~/{path.relative_to(home).as_posix()}" if path.is_relative_to(home) else str(path)


def replace_skill(folder: Path) -> None:
    """Swap an older copy of the skill, or one edited in place, for this version's."""
    shutil.rmtree(folder)
    shutil.copytree(SKILL, folder)


def detect(only: str | None, remove: bool) -> list[Agent]:
    """The agents to work on: every supported agent on PATH, or just `only`.

    Removing also covers OpenCode once it's gone, since deleting its skill copy doesn't need OpenCode. A plugin agent
    not on PATH is skipped, since removing its plugin needs its CLI, unless `only` names it: then it says it couldn't
    check, instead of a bare "Nothing to remove.".
    """
    if remove:
        if only:
            return [AGENTS[only]]
        return [agent for agent in AGENTS.values() if agent.installed() or not isinstance(agent, PluginAgent)]
    if only:
        agent = AGENTS[only]
        if not agent.installed():
            raise click.ClickException(f"{only} isn't installed: `{agent.command}` is not on PATH")
        return [agent]
    found = [agent for agent in AGENTS.values() if agent.installed()]
    if not found:
        raise click.ClickException("found no supported agent on PATH: " + ", ".join(AGENTS))
    return found


def run(*, remove: bool, only: str | None, yes: bool) -> int:
    """Show what will change in each agent, ask, then apply. Returns the exit code."""
    todo = []  # (agent, step) pairs that change something
    for agent in detect(only, remove):
        steps = agent.plan(remove)
        if steps:
            print(agent.name)
        for step in steps:
            print(f"  {step.text}")
            if step.apply:
                todo.append((agent, step))

    if not todo:
        print("Nothing to remove." if remove else "Already set up.")
        return 0
    if not yes and not click.confirm("Apply?"):
        print("Nothing changed.")
        return 1

    failed = False
    for agent, step in todo:
        try:
            step.apply()
        except (OSError, subprocess.SubprocessError) as e:  # SubprocessError: a failed or timed-out CLI
            print(f"failed  {agent.name}: {step.text}: {failure(e)}")
            failed = True
        else:
            print(f"done    {agent.name}: {step.text}")
    return 1 if failed else 0
