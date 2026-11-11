"""Every check. Run with: uv run python tests/test_teachback.py"""

import os
import tempfile
import threading

os.environ["TEACHBACK_HOME"] = tempfile.mkdtemp()  # never touch the real file

from teachback import ledger


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


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_"):
            fn()
    print("ok")
