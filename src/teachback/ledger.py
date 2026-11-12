"""concepts.json: load it, change it under a lock, and schedule reviews with FSRS.

Only teachback writes the file. Layout: {"concepts": {id: concept}, "archive": {id: concept}}.
"""

import json
import os
import re
import tempfile
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path

from fsrs import Card, Rating, Scheduler


def home() -> Path:
    return Path(os.environ.get("TEACHBACK_HOME") or "~/.teachback").expanduser()


def load() -> dict:
    """Read without the lock: os.replace means a reader sees the old file or the new one."""
    file = home() / "concepts.json"
    try:
        return json.loads(file.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return {"concepts": {}, "archive": {}}
    except (json.JSONDecodeError, UnicodeDecodeError) as e:  # a hand edit gone wrong: name the file
        raise ValueError(f"{file} is not valid JSON: {e}") from None


@contextmanager
def edit():
    """Locked read-modify-write. Yields the whole file as a dict, saved if the block doesn't raise.

    Don't nest it: an inner edit() waits forever for the lock the outer one holds.
    """
    import fcntl  # here, not at the top, so load() still imports on Windows

    d = home()
    d.mkdir(parents=True, exist_ok=True)
    # ponytail: fcntl is POSIX only; add msvcrt locking if Windows users show up
    with open(d / ".lock", "w") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        data = load()
        yield data
        text = json.dumps(data, indent=2, ensure_ascii=False) + "\n"
        fd, tmp = tempfile.mkstemp(dir=d)
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                f.write(text)
                f.flush()
                os.fsync(f.fileno())
            os.replace(tmp, d / "concepts.json")
        except BaseException:
            os.unlink(tmp)
            raise


# No learning steps: the user is asked at most once a session, so minute-long steps are useless.
# Every rating goes straight to an interval in days. Fuzzing stays on to spread same-day concepts.
SCHEDULER = Scheduler(learning_steps=(), relearning_steps=())
RETIRE_AFTER = timedelta(days=180)


def slug(title: str) -> str:
    """'HTTP 401 vs 403' and 'http 401 vs. 403' both give 'http-401-vs-403'. Accents are kept.

    + and # are spelled out so C, C++ and C# don't share an id.
    """
    title = title.lower().replace("+", " plus ").replace("#", " sharp ")
    return re.sub(r"\W+", "-", title).strip("-")


def add(title: str, note: str, source: str = "", gap: str = "", now: datetime | None = None) -> str:
    """Save a new concept, first due a day later, and return its id."""
    now = now or datetime.now(timezone.utc)
    if now.tzinfo != timezone.utc:  # a naive due date would break every later due(); rate() has the same rule
        raise ValueError("now must be a UTC datetime")
    id = slug(title)
    if not id:
        raise ValueError(f"title {title!r} has no letters or digits")
    with edit() as data:
        if id in data["concepts"] or id in data["archive"]:
            raise ValueError(f"concept {id!r} already exists")
        entry = {"title": title, "note": note}
        if source:
            entry["source"] = source
        if gap:
            entry["gap"] = gap
        # A day out: asking in the same session would test short-term memory, not retention.
        entry["card"] = Card(due=now + timedelta(days=1)).to_dict()
        data["concepts"][id] = entry
    return id


def due(now: datetime | None = None) -> tuple[str, dict] | None:
    """The concept due longest ago, as (id, concept), or None. A read, so no lock."""
    now = now or datetime.now(timezone.utc)
    concepts = load()["concepts"]
    ready = [(datetime.fromisoformat(c["card"]["due"]), id) for id, c in concepts.items()]
    ready = [r for r in ready if r[0] <= now]
    if not ready:
        return None
    id = min(ready)[1]
    return id, concepts[id]


def rate(id: str, rating: str, now: datetime | None = None) -> int | str:
    """Grade a review. Returns the next wait in whole days, or "archived" past RETIRE_AFTER."""
    now = now or datetime.now(timezone.utc)
    try:
        grade = Rating[rating.strip().capitalize()]
    except KeyError:
        raise ValueError(f"rating {rating!r} must be one of {', '.join(r.name for r in Rating)}") from None
    with edit() as data:
        if id not in data["concepts"]:
            raise ValueError(f"no concept {id!r} to review")
        card = Card.from_dict(data["concepts"][id]["card"])
        # Another open session may have graded it minutes ago: a second grade would test short-term memory.
        if card.due > now:
            raise ValueError(f"{id!r} was already reviewed; next review {card.due.astimezone():%Y-%m-%d}")
        card, _ = SCHEDULER.review_card(card, grade, now)
        data["concepts"][id]["card"] = card.to_dict()
        if card.due - now > RETIRE_AFTER:
            data["archive"][id] = data["concepts"].pop(id)
            return "archived"
    return (card.due - now).days
