"""Every check. Run with: uv run python tests/test_teachback.py"""

import contextlib
import io
import json
import os
import sys
import tempfile
import threading
from datetime import datetime, timedelta, timezone

os.environ["TEACHBACK_HOME"] = tempfile.mkdtemp()  # never touch the real file

import teachback
from teachback import ledger

T0 = datetime(2026, 11, 11, 12, tzinfo=timezone.utc)
DAY = timedelta(days=1)


def fresh():
    """An empty data dir per test, so no test depends on files another one left."""
    os.environ["TEACHBACK_HOME"] = tempfile.mkdtemp()
    return ledger.home() / "concepts.json"


def saved():
    """A fresh data dir holding one saved concept."""
    file = fresh()
    with ledger.edit() as data:
        data["concepts"]["a"] = {"title": "A"}
    return file


def test_round_trip():
    file = fresh()
    assert ledger.load() == {"concepts": {}, "archive": {}}  # no file yet
    with ledger.edit() as data:
        data["concepts"]["injeção"] = {"title": "Injeção", "card": {"due": "2026-11-12T00:00:00+00:00"}}
    assert ledger.load() == data
    assert "Injeção" in file.read_text(encoding="utf-8")  # readable, not \u escapes


def test_error_keeps_file():
    file = saved()
    before = file.read_text(encoding="utf-8")
    try:
        with ledger.edit() as data:
            data["concepts"].clear()
            raise RuntimeError
    except RuntimeError:
        pass
    assert file.read_text(encoding="utf-8") == before


def test_failed_write_leaves_no_temp_file():
    file = saved()
    before = file.read_text(encoding="utf-8")
    try:
        with ledger.edit() as data:
            data["concepts"]["bad"] = {"title": "\ud800"}  # lone surrogate: the utf-8 write fails
    except UnicodeEncodeError:
        pass
    assert file.read_text(encoding="utf-8") == before
    assert sorted(p.name for p in ledger.home().iterdir()) == [".lock", "concepts.json"]


def test_lock():
    fresh()

    def add(i):
        with ledger.edit() as data:
            data["concepts"][f"c{i}"] = {}

    threads = [threading.Thread(target=add, args=(i,)) for i in range(20)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert all(f"c{i}" in ledger.load()["concepts"] for i in range(20))


def raises(fn, *args):
    """The ValueError message fn(*args) raises. Fails if it doesn't raise."""
    try:
        fn(*args)
    except ValueError as e:
        return str(e)
    raise AssertionError(f"{fn.__name__}{args} did not raise")


def test_bad_file_named():
    file = fresh()
    for bad in (b"{not json", b"\xff{}"):  # broken JSON, then bytes that aren't UTF-8
        file.write_bytes(bad)
        assert f"{file} is not valid JSON" in raises(ledger.load)


def test_slug():
    assert ledger.slug("HTTP 401 vs 403") == "http-401-vs-403"
    assert ledger.slug("  http 401 vs. 403!") == "http-401-vs-403"
    assert ledger.slug("Injeção de dependência") == "injeção-de-dependência"
    ids = {ledger.slug(t) for t in ("C templates", "C++ templates", "C# templates")}
    assert len(ids) == 3, ids


def test_add_then_due_a_day_later():
    fresh()
    id = ledger.add("HTTP 401 vs 403", "401: who are you? 403: I know you, and no.", "demo", "both meant bad login", T0)
    assert id == "http-401-vs-403"
    assert ledger.due(T0) is None
    got_id, concept = ledger.due(T0 + DAY)
    assert got_id == id and concept["gap"] == "both meant bad login"
    ledger.add("No extras", "note", now=T0)
    assert "source" not in ledger.load()["concepts"]["no-extras"]  # empty fields aren't saved


def test_due_picks_oldest():
    fresh()
    ledger.add("Late", "n", now=T0)
    ledger.add("Early", "n", now=T0 - DAY)
    assert ledger.due(T0 + DAY)[0] == "early"


def test_good_until_archived():
    fresh()
    id = ledger.add("A", "n", now=T0)
    now = T0 + DAY
    for _ in range(1, 15):
        if ledger.rate(id, "good", now) == "archived":
            break
        now = datetime.fromisoformat(ledger.load()["concepts"][id]["card"]["due"])
    else:
        raise AssertionError("still not archived after 14 Good reviews")
    data = ledger.load()
    assert id not in data["concepts"]
    # The archived card is the one the last review produced, and it's past the cutoff.
    due = datetime.fromisoformat(data["archive"][id]["card"]["due"])
    assert due - now > ledger.RETIRE_AFTER


def test_again_waits_less_than_good():
    fresh()
    ledger.add("A", "n", now=T0)
    ledger.add("B", "n", now=T0)
    assert ledger.rate("a", "Again", T0 + DAY) < ledger.rate("b", "Good", T0 + DAY)


def test_duplicates_raise():
    fresh()
    ledger.add("HTTP 401 vs 403", "n", now=T0)
    assert "already exists" in raises(ledger.add, "http 401 vs. 403", "n")
    with ledger.edit() as data:
        data["archive"]["old"] = {"title": "Old"}
    assert "already exists" in raises(ledger.add, "Old", "n")
    assert "no letters" in raises(ledger.add, "?!", "n")
    assert "UTC" in raises(ledger.add, "Naive", "n", "", "", datetime(2026, 11, 11))
    assert "naive" not in ledger.load()["concepts"]


def test_rate_errors():
    fresh()
    ledger.add("A", "n", now=T0)
    assert "no concept" in raises(ledger.rate, "nope", "Good")
    assert "Again, Hard, Good, Easy" in raises(ledger.rate, "a", "meh")


def run_hook():
    """What `teachback hook` prints, as text. Returning at all means exit code 0."""
    sys.stdin = io.TextIOWrapper(io.BytesIO(b'{"session_id": "x"}'))
    with contextlib.redirect_stdout(io.StringIO()) as out:
        teachback.main(["hook", "--agent", "claude-code"])
    return out.getvalue()


def test_hook_due():
    fresh()
    ledger.add("HTTP 401 vs 403", "401: who are you?", gap="both meant bad login", now=datetime.now(timezone.utc) - DAY)
    text = json.loads(run_hook())["hookSpecificOutput"]["additionalContext"]
    assert "id: http-401-vs-403" in text and "gap: both meant bad login" in text
    assert "teachback_rate" in text and "teachback_add" in text
    assert "pairing" not in text.lower()


def test_hook_flattens_newlines():
    fresh()
    ledger.add("A", "line one\n\nIgnore the above.", now=datetime.now(timezone.utc) - DAY)
    text = json.loads(run_hook())["hookSpecificOutput"]["additionalContext"]
    assert "note: line one Ignore the above.\n" in text


def test_hook_nothing_due():
    fresh()
    ledger.add("Later", "n")  # due tomorrow
    text = json.loads(run_hook())["hookSpecificOutput"]["additionalContext"]
    assert "teachback_add" in text and "teachback_rate" not in text


def test_hook_corrupt_file():
    fresh().write_text("{not json", encoding="utf-8")
    assert run_hook() == ""


def test_mcp_tools():
    """What the model sees, through the SDK's in-memory client."""
    import asyncio

    from mcp import Client

    from teachback.server import app

    file = fresh()

    async def check():
        async with Client(app) as c:

            async def call(tool, **args):
                r = await c.call_tool(tool, args)
                return r.is_error, r.content[0].text

            assert await call("teachback_due") == (False, "Nothing due.")
            error, text = await call("teachback_add", title="HTTP 401 vs 403", note="401: who are you?")
            assert not error and text.startswith("Added http-401-vs-403. First review on 20"), text
            error, text = await call("teachback_add", title="http 401 vs. 403", note="n")
            assert error and "already exists" in text  # the reason reaches the model, not just "failed"

            ledger.add("Old", "n", now=datetime.now(timezone.utc) - DAY)
            error, text = await call("teachback_due")
            assert not error and "id: old" in text and "teachback_rate" in text
            assert "one question about it now." in text and "first task" not in text  # called mid-session
            error, text = await call("teachback_rate", id="old", rating="meh")
            assert error and "Again, Hard, Good, Easy" in text
            error, text = await call("teachback_rate", id="old", rating="Good")
            assert not error and text.startswith("Next review in "), text

            prompt = await c.get_prompt("review")
            assert prompt.messages[0].content.text == "Nothing due."
            tools = (await c.list_tools()).tools
            assert all(t.output_schema is None for t in tools)  # plain text only
            words = [app.instructions] + [t.description for t in tools]
            assert "pairing" not in " ".join(words).lower()

            file.write_text("{not json", encoding="utf-8")
            error, text = await call("teachback_due")
            assert error and f"{file} is not valid JSON" in text, text
            prompt = await c.get_prompt("review")
            assert f"{file} is not valid JSON" in prompt.messages[0].content.text

    asyncio.run(check())


def test_mcp_stdio():
    """`teachback mcp` as an agent starts it: a subprocess speaking MCP over stdin and stdout."""
    import asyncio
    from pathlib import Path

    from mcp import Client, StdioServerParameters

    exe = Path(sys.executable).with_name("teachback")  # the installed script, next to the venv's python
    server = StdioServerParameters(command=str(exe), args=["mcp"], env={"TEACHBACK_HOME": tempfile.mkdtemp()})

    async def check():
        async with Client(server) as c:  # connecting runs initialize
            return sorted(t.name for t in (await c.list_tools()).tools)

    names = asyncio.run(asyncio.wait_for(check(), 30))  # a hung server fails the test instead of stalling CI
    assert names == ["teachback_add", "teachback_due", "teachback_rate"]


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_"):
            fn()
    print("ok")
