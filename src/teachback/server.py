"""`teachback mcp`: the stdio MCP server an agent starts per session to run reviews.

Each tool description repeats the rule it needs: some agents drop server instructions, none drop tool descriptions.
"""

from datetime import datetime

from mcp.server import MCPServer
from mcp.server.mcpserver.exceptions import ToolError

from teachback import __version__, ledger, review_text

NOTHING_DUE = "Nothing due."

app = MCPServer(
    "teachback",
    version=__version__,
    instructions=(
        "teachback runs spaced reviews of concepts the user hasn't fixed yet.\n"
        "- Ask at most one review question per session.\n"
        "- When the user shows a gap in a concept, offer to add it with teachback_add. "
        "Add it only if they agree.\n"
        "- Grade each review answer honestly as Again, Hard, Good or Easy, and tell the user the grade."
    ),
)


def due() -> str:
    try:
        return review_text(ask="Ask the user one question about it now.") or NOTHING_DUE
    except ValueError as e:  # concepts.json isn't valid JSON: say which file, so the user can fix it
        raise ToolError(str(e)) from None


@app.tool(structured_output=False)  # plain text: no outputSchema for the model to read
def teachback_due() -> str:
    """The concept due for review and how to review it, or "Nothing due."

    Ask at most one review question per session, so call this only if you haven't asked one yet.
    """
    return due()


@app.tool(structured_output=False)
def teachback_rate(id: str, rating: str) -> str:
    """Save the grade for the user's answer to a review question.

    id: the concept's id. rating: Again, Hard, Good or Easy. Grade honestly and tell the user the grade.
    """
    try:
        days = ledger.rate(id, rating)
    except ValueError as e:
        raise ToolError(str(e)) from None  # the model sees the message and can retry; other errors stay hidden
    if days == "archived":
        return "Archived: fixed for now."
    return f"Next review in {days} day{'s' * (days != 1)}."


@app.tool(structured_output=False)
def teachback_add(title: str, note: str, source: str = "", gap: str = "") -> str:
    """Add a concept the user hasn't fixed yet to their reviews.

    Call it only after you offered to add it and the user agreed. Never add one on your own.
    title: a short name. note: the concept in one or two sentences. source: where it came up, such as a
    repo or file. gap: what the user missed or got wrong.
    """
    try:
        id = ledger.add(title, note, source, gap)
    except ValueError as e:
        raise ToolError(str(e)) from None
    first = datetime.fromisoformat(ledger.load()["concepts"][id]["card"]["due"]).astimezone()
    return f"Added {id}. First review on {first:%Y-%m-%d}."


@app.prompt(name="review")
def review_prompt() -> str:
    """Review one due concept now."""
    try:
        return due()
    except ToolError as e:  # raised, it would reach the user as a bare "Internal server error"
        return f"teachback can't read its concepts: {e}"
