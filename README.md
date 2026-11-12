# teachback

A coding agent can write code you couldn't explain, and you forget what you looked up along the way. teachback makes you learn while you work with coding agents.

- **Pairing mode**: the agent writes no non-trivial code until you explain why it has to be shaped that way, and debugging stays with you.
- **Reviews**: concepts you haven't fixed yet are kept in one file. Your agent asks about one when it's due, on an FSRS schedule, until it sticks.

## Install

```
uv tool install teachback
teachback setup
```

`setup` finds Claude Code, Codex and OpenCode on your PATH, shows what it will change in each, and asks before applying. `--agent NAME` limits it to one agent and `--yes` skips the question. `teachback uninstall` takes the same flags and removes everything setup added.

- **Claude Code and Codex** get the teachback plugin through their own `plugin` commands: the pairing mode skill, a SessionStart hook and the MCP server. This repository is the plugin's marketplace.
- **OpenCode** gets the skill copied to `~/.config/opencode/skills/`, a plugin that does the hook's job copied to `~/.config/opencode/plugins/` (OpenCode 2 or later), and the MCP server registered with `opencode mcp add`.

Your instruction files (AGENTS.md, CLAUDE.md) are never edited.

Without Python, you can still get pairing mode alone: copy [`plugin/skills/teachback`](https://github.com/pedroven/teachback/tree/main/plugin/skills/teachback) into your agent's skills folder.

## Pairing mode

Turn it on with `/teachback` in Claude Code, `$teachback` in Codex or `@teachback` in OpenCode. Turn it off by saying "stop teachback", or with `/teachback off` in Claude Code.

## Reviews

- **Adding a concept:** when you show a gap in a concept, the agent offers to add it to your reviews, and adds it only if you agree. You can also ask it to add one. Pairing mode makes the same offer after you pass an explanation you got stuck on.
- **Being asked:** at session start, the agent gets the one concept that's due, if any. It asks you one question, grades your answer Again, Hard, Good or Easy, and saves the grade. That's at most one question per session, and the first comes a day after the concept is added.
- **Leaving:** once a concept's next review would be more than 180 days away, it moves to the file's `archive` section.
- **Your data:** `~/.teachback/concepts.json`, written only by teachback. `TEACHBACK_HOME` changes the folder. The file is indented JSON, so `cat` shows what's in it.
- **No session-start hook?** Run the `review` prompt to review now: `/plugin:teachback:teachback:review` in Claude Code, `/teachback:review` in OpenCode.

## Agent support

| Agent | Pairing mode | Review at session start | Review tools |
|---|---|---|---|
| Claude Code | `/teachback` | hook | yes |
| Codex | `$teachback` | hook, once you trust it in `/hooks` | yes, and it asks before adding or grading |
| OpenCode 2+ | `@teachback` | plugin | yes |
| OpenCode 1 | `@teachback` | no, use `/teachback:review` | yes |

Codex runs the hook only after you trust it, when it asks at start or in `/hooks`, and again after each teachback update.

To stop Codex asking before each add or grade, add this to `~/.codex/config.toml`:

```toml
[plugins."teachback@teachback".mcp_servers.teachback]
default_tools_approval_mode = "approve"
```

[Changelog](https://github.com/pedroven/teachback/blob/main/CHANGELOG.md) · [Contributing](https://github.com/pedroven/teachback/blob/main/docs/contributing.md)
