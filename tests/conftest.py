import os
import tempfile

import pytest
from click.testing import CliRunner

import teachback

# Fallback for anything that runs outside a test (collection, wider-scoped fixtures): never the real ~/.teachback.
os.environ["TEACHBACK_HOME"] = tempfile.mkdtemp()


@pytest.fixture(autouse=True)
def _teachback_home(tmp_path, monkeypatch):
    """An empty data dir per test, so no test sees files another test left.

    Named so no test parameter or fixture can shadow it by accident.
    """
    monkeypatch.setenv("TEACHBACK_HOME", str(tmp_path))


@pytest.fixture
def file(tmp_path):
    """concepts.json in this test's data dir."""
    return tmp_path / "concepts.json"


def teachback_cli(*args, input=None):
    """Runs `teachback ARGS` and returns (exit code, output)."""
    result = CliRunner().invoke(teachback.main, args, input=input)
    return result.exit_code, result.output
