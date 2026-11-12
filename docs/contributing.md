# Contributing

## Tests

You need [uv](https://docs.astral.sh/uv/).

```
uv run pytest      # one test file per module: tests/test_ledger.py, test_agents.py, test_cli.py, test_server.py
uv run ruff format
uv run ruff check
```

ruff and pytest are pinned in the `dev` group of `pyproject.toml`, so your local versions match CI's. pip-audit runs only in CI, pinned in `PIP_AUDIT_VERSION` at the top of `.github/workflows/ci.yml`.

The tests point `TEACHBACK_HOME` at a temporary folder, so they never touch your real `~/.teachback`.

CI (`.github/workflows/ci.yml`) runs the same checks, plus `pip-audit`, on every push to `main` and every pull request, on Python 3.10 and 3.13.

## Releases

1. As you work, add changes under `## [Unreleased]` in `CHANGELOG.md`.
2. Run `uv version --bump patch` (or `minor`, `major`). This updates `pyproject.toml` and `uv.lock`. Set the same version in `plugin/.claude-plugin/plugin.json` and `plugin/.codex-plugin/plugin.json`: Claude Code and Codex use it to tell when the plugin has changed, and `test_plugin_versions` fails until all three match.
3. In `CHANGELOG.md`, rename `[Unreleased]` to `[X.Y.Z] - YYYY-MM-DD` and add an empty `[Unreleased]` above it.
4. Commit "Release X.Y.Z", then `git tag vX.Y.Z && git push origin main vX.Y.Z`.

The tag starts `.github/workflows/publish.yml`. It runs CI, checks that the tag matches the version in `pyproject.toml`, uploads to PyPI through trusted publishing (no token), and creates a GitHub release. The release notes are that version's `CHANGELOG.md` section, plus the install command and the sha256 of each file. If `CHANGELOG.md` has no section for the version, the workflow stops before uploading.

If a release fails partway, re-run it: Actions > Publish to PyPI > Run workflow, and pick the tag, not a branch. Files already on PyPI are skipped, and a GitHub release that already exists is left alone.
