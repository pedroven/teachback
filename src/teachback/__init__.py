import argparse
import json
import sys
from importlib.metadata import version

__version__ = version("teachback")

CAPTURE = (
    "When the user shows a gap in a concept during the session, offer to add it with teachback_add. "
    "Add it only if they agree."
)


def context() -> str:
    """The session-start text: the one due concept, if any, then the capture reminder."""
    from teachback import ledger

    found = ledger.due()
    if not found:
        return CAPTURE
    id, c = found
    # One line per field: a newline in stored text can't pass for another field or an instruction.
    fields = [("id", id), ("title", c["title"]), ("note", c["note"]), ("gap", c.get("gap"))]
    fields = [f"{name}: {' '.join(value.split())}" for name, value in fields if value]
    return (
        "teachback: one concept to review this session.\n"
        + "\n".join(fields)
        + "\n\nBefore the user's first task, ask them one question about it. Use new wording, and tie it to the "
        "current code when you can. Grade the answer Again, Hard, Good or Easy, say the grade, then call "
        "teachback_rate. Ask at most this one question this session.\n\n" + CAPTURE
    )


def hook() -> None:
    try:
        sys.stdin.buffer.read()  # the agent's session JSON: unused yet, and bytes so the locale can't fail it
        out = {"hookSpecificOutput": {"hookEventName": "SessionStart", "additionalContext": context()}}
        print(json.dumps(out))  # ASCII escapes, so a non-UTF-8 stdout can't fail it
    except Exception:
        pass  # never block a session, not even over a corrupt concepts.json


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(prog="teachback", description=f"teachback {__version__}")
    sub = parser.add_subparsers(dest="command")
    h = sub.add_parser("hook", help="print the session-start context (run by the agent, not by you)")
    h.add_argument("--agent", help="the agent running the hook; every agent gets the same format for now")
    args = parser.parse_args(argv)
    if args.command == "hook":
        hook()
    else:
        parser.print_help()
