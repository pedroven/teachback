"""The agents teachback installs into, and `teachback setup` / `teachback uninstall`."""

import os
import shutil
from abc import ABC, abstractmethod
from collections.abc import Callable
from pathlib import Path
from typing import NamedTuple

import click

# The pairing mode skill. Installed from the wheel, it sits next to this file (pyproject.toml copies it there).
# Run from a repo checkout (`uv run`), it is only in the repo's top-level skills/ folder.
SKILL = Path(__file__).parent / "skills" / "teachback"
if not SKILL.is_dir():
    SKILL = Path(__file__).parents[2] / "skills" / "teachback"


class Step(NamedTuple):
    text: str  # what the plan shows
    apply: Callable[[], object] | None = None  # None: only reported, nothing to change


class Agent(ABC):
    """A coding agent teachback installs into. Each concrete agent says where its files go."""

    name: str  # what --agent takes
    command: str  # on PATH when the agent is installed

    @property
    @abstractmethod
    def skills_dir(self) -> Path:
        """The folder the agent loads skills from."""

    def installed(self) -> bool:
        return shutil.which(self.command) is not None

    def plan(self, remove: bool) -> list[Step]:
        """The steps for this agent, leaving out the ones with nothing to do."""
        steps = [self.skill_step(remove)]
        return [step for step in steps if step]

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

        if not folder.exists():
            return Step(f"copy the skill to {shown}", lambda: shutil.copytree(SKILL, folder))
        if files_in(folder) == files_in(SKILL):
            return None  # already installed
        return Step(f"replace {shown}: it differs from this version's skill", lambda: replace_skill(folder))


class ClaudeCode(Agent):
    name = "claude-code"
    command = "claude"

    @property
    def skills_dir(self) -> Path:
        return Path(os.environ.get("CLAUDE_CONFIG_DIR") or Path.home() / ".claude") / "skills"


class Codex(Agent):
    name = "codex"
    command = "codex"

    @property
    def skills_dir(self) -> Path:
        # Not under CODEX_HOME: that is ~/.codex, whose skills/ folder Codex still reads as its older place.
        return Path.home() / ".agents" / "skills"


class OpenCode(Agent):
    name = "opencode"
    command = "opencode"

    @property
    def skills_dir(self) -> Path:
        return Path(os.environ.get("XDG_CONFIG_HOME") or Path.home() / ".config") / "opencode" / "skills"


AGENTS = {agent.name: agent for agent in (ClaudeCode(), Codex(), OpenCode())}


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

    Removing works on every agent, installed or not, so uninstalling an agent first leaves nothing behind.
    """
    if remove:
        return [AGENTS[only]] if only else list(AGENTS.values())
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
    if not remove and not SKILL.is_dir():
        # Checked before planning: a replace deletes the old copy first, and there would be nothing to copy back.
        raise click.ClickException(f"this install of teachback has no skill at {SKILL}. Reinstall teachback.")
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
        except OSError as e:
            print(f"failed  {agent.name}: {step.text}: {e}")
            failed = True
        else:
            print(f"done    {agent.name}: {step.text}")
    return 1 if failed else 0
