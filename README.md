# teachback

Learn while you work with coding agents.

- **Pairing mode** (`/teachback`): the agent writes no non-trivial code until you explain why it has to be shaped that way, and debugging stays with you.
- **Reviews**: concepts you haven't fixed yet are kept in one file. Your agent asks about one when it's due, on an FSRS schedule, until it sticks.

Works across agents through hooks, an MCP server and a skill. Your instruction files (AGENTS.md, CLAUDE.md) are never edited.

## Install pairing mode

Pairing mode is a skill. Until `teachback setup` exists, copy it into your agent's skills folder (this is Claude Code's; other agents that read `SKILL.md` have their own):

```
git clone https://github.com/pedroven/teachback
cp -r teachback/plugin/skills/teachback ~/.claude/skills/
```

Run `/teachback` to turn it on and `/teachback off` to turn it off. It was first tested as `/learn`.

Reviews are not built yet.

[Changelog](https://github.com/pedroven/teachback/blob/main/CHANGELOG.md) · [Contributing](https://github.com/pedroven/teachback/blob/main/docs/contributing.md)
