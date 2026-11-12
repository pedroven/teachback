import json
import sys
from importlib.metadata import version

import click

from teachback import agents

__version__ = version("teachback")

CAPTURE = (
    "When the user shows a gap in a concept during the session, offer to add it with teachback_add. "
    "Add it only if they agree."
)


def review_text(ask: str = "Before the user's first task, ask them one question about it.") -> str | None:
    """The due concept and how to review it, or None. The hook, teachback_due and the review prompt share it.

    ask: when to ask. The hook asks before the first task; the MCP server, called mid-session, asks now.
    """
    from teachback import ledger

    found = ledger.due()
    if not found:
        return None
    id, c = found
    # One line per field: a newline in stored text can't pass for another field or an instruction.
    fields = [("id", id), ("title", c["title"]), ("note", c["note"]), ("gap", c.get("gap"))]
    fields = [f"{name}: {' '.join(value.split())}" for name, value in fields if value]
    return (
        "teachback: one concept to review this session.\n"
        + "\n".join(fields)
        + f"\n\n{ask} Use new wording, and tie it to the current code when you can. Grade the answer Again, "
        "Hard, Good or Easy, say the grade, then call teachback_rate. Ask at most this one question this session."
    )


def context() -> str:
    """The session-start text: the one due concept, if any, then the capture reminder."""
    review = review_text()
    return f"{review}\n\n{CAPTURE}" if review else CAPTURE


@click.group(invoke_without_command=True)
@click.version_option(__version__, prog_name="teachback")
@click.pass_context
def main(ctx: click.Context) -> None:
    """Learn while you work with coding agents."""
    if ctx.invoked_subcommand is None:
        click.echo(ctx.get_help())  # exit 0, as before click: click's default is exit 2


@main.command()
def hook() -> None:
    """Print the session-start context (run by the agent, not by you)."""
    try:
        session = json.loads(sys.stdin.buffer.read())  # bytes, so the locale can't fail it
        source = session.get("source") if isinstance(session, dict) else None
    except Exception:  # no or odd session JSON: OpenCode's plugin sends none
        source = None
    try:
        # Claude Code runs this again after compacting: the session may already have had its one question.
        text = CAPTURE if source == "compact" else context()
    except Exception as e:  # a corrupt concepts.json, say: still remind, and say why nothing is due
        text = f"{CAPTURE}\n\nteachback can't read its concepts: {e}. Tell the user."
    out = {"hookSpecificOutput": {"hookEventName": "SessionStart", "additionalContext": text}}
    try:
        print(json.dumps(out))  # ASCII escapes, so a non-UTF-8 stdout can't fail it
    except Exception:
        pass  # never block a session


@main.command()
def mcp() -> None:
    """Run the MCP server over stdio (run by the agent, not by you)."""
    from teachback.server import app  # here, so the hook doesn't pay for importing the SDK

    app.run()


@main.command()
@click.option("--agent", type=click.Choice(list(agents.AGENTS)), help="Only this agent.")
@click.option("--yes", "-y", is_flag=True, help="Don't ask before applying.")
@click.option("--pin", is_flag=True, help="Pin the Claude Code and Codex plugin to this version's release tag.")
def setup(agent: str | None, yes: bool, pin: bool) -> None:
    """Install teachback into every agent on PATH: the plugin in Claude Code and Codex, the skill, a plugin file and
    the MCP server in OpenCode."""
    sys.exit(agents.run(remove=False, only=agent, yes=yes, pin=pin))


@main.command()
@click.option("--agent", type=click.Choice(list(agents.AGENTS)), help="Only this agent.")
@click.option("--yes", "-y", is_flag=True, help="Don't ask before applying.")
def uninstall(agent: str | None, yes: bool) -> None:
    """Remove what setup installed, editing OpenCode's config for its MCP server. OpenCode's files and MCP server are
    removed even after OpenCode is gone."""
    sys.exit(agents.run(remove=True, only=agent, yes=yes))
