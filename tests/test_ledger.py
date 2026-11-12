"""`teachback.ledger`: the concepts file and the review schedule."""

import threading
from datetime import datetime, timedelta, timezone

import pytest

from teachback import ledger

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


def test_rate_twice():
    """Two open sessions got the same concept: the second grade would test short-term memory."""
    ledger.add("A", "n", now=T0)
    ledger.rate("a", "Good", T0 + DAY)
    with pytest.raises(ValueError, match="'a' was already reviewed; next review 20"):
        ledger.rate("a", "Good", T0 + DAY)


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
