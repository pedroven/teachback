# Changelog

Notable changes to teachback. The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and versions follow [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [0.1.1] - 2026-11-12

### Changed

- The README now opens with the problem teachback solves: an agent can write code you couldn't explain, and you forget what you looked up along the way.
- The release steps in `docs/contributing.md` say to bump the version in both plugin manifests along with `pyproject.toml`.

## [0.1.0] - 2026-11-11

### Added

- Storage for reviews: concepts you haven't fixed yet live in `~/.teachback/concepts.json` (`TEACHBACK_HOME` overrides the folder) and are scheduled with FSRS.
- `teachback hook`: the session-start text an agent injects, with the one concept due for review, if any.
- `teachback mcp`: a stdio MCP server with the tools `teachback_due`, `teachback_rate` and `teachback_add`, plus a `review` prompt for agents whose hooks can't inject text. `teachback_due` is marked read-only, so Codex calls it without asking; it still asks before `teachback_add` and `teachback_rate`.
- A Claude Code and Codex plugin: the pairing mode skill, a SessionStart hook that runs `teachback hook`, and the `teachback mcp` server. This repository is its marketplace (`pedroven/teachback`). Codex runs the hook only after you trust it in `/hooks`, and passes `TEACHBACK_HOME` on to the MCP server, which it otherwise drops.
- `teachback setup` and `teachback uninstall`: show what will change in each agent found on PATH, ask, then apply.
  - Claude Code and Codex get the plugin through their own `plugin` commands. A skill copied there by hand earlier is pointed out so you can delete it.
  - OpenCode gets the skill copied into its skills folder. An older copy is replaced, a symlink is left alone, and the folder follows `XDG_CONFIG_HOME`.
  - OpenCode 2 or later also gets a plugin in its plugins folder. It adds the session-start review text to each session, as the hook does in the other agents.
  - OpenCode's MCP server is registered through `opencode mcp add`. Uninstall removes it from `opencode.json` or `opencode.jsonc`, through a symlink and keeping the file's permissions. A config it can't read is reported and left alone.
  - Uninstall also covers OpenCode after it is gone.
- Pairing mode offers to add a concept you're missing to your reviews, once, in the turn right after you pass the explanation gate. It only does this when the `teachback_add` tool is available.

## [0.0.3] - 2026-11-10

### Added

- Pairing mode skill (`/teachback`). Install it by copying `skills/teachback` into your agent's skills folder.

### Changed

- Renamed from aprendiz to teachback: the PyPI package, the CLI, the Python package and the skill.

## [0.0.2] - 2026-11-10

### Added

- MIT license and repository link in the PyPI metadata. Published as aprendiz.

## [0.0.1] - 2026-11-10

### Added

- Placeholder package that claims the name on PyPI. Published as aprendiz.
