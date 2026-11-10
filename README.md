# aprendiz

Learn while you work with coding agents.

- **Pairing mode** (`/aprendiz`): the agent writes no non-trivial code until you explain why it has to be shaped that way, and debugging stays with you.
- **Reviews**: concepts you haven't fixed yet are kept in one file. Your agent asks about one when it's due, on an FSRS schedule, until it sticks.

Works across agents through hooks, an MCP server and a skill. Your instruction files (AGENTS.md, CLAUDE.md) are never edited.

## Install pairing mode

Pairing mode is a skill. Until `aprendiz setup` exists, copy it into your agent's skills folder (this is Claude Code's; other agents that read `SKILL.md` have their own):

```
git clone https://github.com/pedroven/aprendiz
cp -r aprendiz/skills/aprendiz ~/.claude/skills/
```

Run `/aprendiz` to turn it on and `/aprendiz off` to turn it off. It was first tested as `/learn`.

Reviews are not built yet.
