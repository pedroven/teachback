"""`teachback mcp`: what the model sees, through the SDK's client."""

import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import anyio
import pytest
from mcp import Client, StdioServerParameters

from teachback import ledger
from teachback.server import app

pytestmark = pytest.mark.anyio  # anyio's pytest plugin, installed with mcp


@pytest.fixture
async def client():
    async with Client(app) as c:  # in memory, no subprocess
        yield c


async def call(client, tool, **args):
    r = await client.call_tool(tool, args)
    return r.is_error, r.content[0].text


async def review_prompt(client):
    return (await client.get_prompt("review")).messages[0].content.text


async def test_nothing_due(client):
    assert await call(client, "teachback_due") == (False, "Nothing due.")
    assert await review_prompt(client) == "Nothing due."


async def test_add(client):
    error, text = await call(client, "teachback_add", title="HTTP 401 vs 403", note="401: who are you?")
    assert not error and text.startswith("Added http-401-vs-403. First review on 20"), text
    error, text = await call(client, "teachback_add", title="http 401 vs. 403", note="n")
    assert error and "already exists" in text  # the reason reaches the model, not just "failed"


async def test_due_then_rate(client):
    ledger.add("Old", "n", now=datetime.now(timezone.utc) - timedelta(days=1))
    error, text = await call(client, "teachback_due")
    assert not error and "id: old" in text and "teachback_rate" in text
    assert "one question about it now." in text and "first task" not in text  # called mid-session
    error, text = await call(client, "teachback_rate", id="old", rating="meh")
    assert error and "Again, Hard, Good, Easy" in text
    error, text = await call(client, "teachback_rate", id="old", rating="Good")
    assert not error and text.startswith("Next review in "), text
    assert await review_prompt(client) == "Nothing due."  # concepts saved, none due


async def test_tools_plain_text_no_pairing(client):
    tools = (await client.list_tools()).tools
    assert all(t.output_schema is None for t in tools)  # plain text only
    words = [app.instructions] + [t.description for t in tools]
    assert "pairing" not in " ".join(words).lower()
    # Codex asks before every MCP call, unless the tool says it is read-only
    read_only = {t.name for t in tools if t.annotations and t.annotations.read_only_hint}
    assert read_only == {"teachback_due"}


async def test_corrupt_file_named(client, file):
    file.write_text("{not json", encoding="utf-8")
    error, text = await call(client, "teachback_due")
    assert error and f"{file} is not valid JSON" in text, text
    assert f"{file} is not valid JSON" in await review_prompt(client)


async def test_stdio(tmp_path):
    """`teachback mcp` as an agent starts it: a subprocess speaking MCP over stdin and stdout."""
    exe = Path(sys.executable).with_name("teachback")  # the installed script, next to the venv's python
    server = StdioServerParameters(command=str(exe), args=["mcp"], env={"TEACHBACK_HOME": str(tmp_path)})
    with anyio.fail_after(30):  # a hung server fails the test instead of stalling CI
        async with Client(server) as c:  # connecting runs initialize
            names = sorted(t.name for t in (await c.list_tools()).tools)
    assert names == ["teachback_add", "teachback_due", "teachback_rate"]
