"""concepts.json: load it, or change it under a lock. Scheduling lives on top of this.

Only teachback writes the file. Layout: {"concepts": {id: concept}, "archive": {id: concept}}.
"""

import json
import os
import tempfile
from contextlib import contextmanager
from pathlib import Path


def home() -> Path:
    return Path(os.environ.get("TEACHBACK_HOME") or "~/.teachback").expanduser()


def load() -> dict:
    """Read without the lock: os.replace means a reader sees the old file or the new one."""
    try:
        return json.loads((home() / "concepts.json").read_text(encoding="utf-8"))
    except FileNotFoundError:
        return {"concepts": {}, "archive": {}}


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
