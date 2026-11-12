// teachback for OpenCode: what the SessionStart hook does in Claude Code and Codex.
//
// OpenCode runs no hook commands, so this plugin runs `teachback hook` once per session and adds its text to the
// system prompt. The "context" hook fires before every model request and what it adds isn't kept, so it adds the
// text each time. `teachback setup` copies this file to ~/.config/opencode/plugins/, where OpenCode loads it.
import { execFile } from "node:child_process";
import { promisify } from "node:util";

const run = promisify(execFile);

export default {
  id: "teachback",
  async setup(ctx) {
    // ponytail: one entry per session for the life of the server; drop entries on session.deleted if that grows
    const texts = new Map();

    async function sessionText(sessionID) {
      try {
        const session = await ctx.session.get({ sessionID });
        // A subagent doesn't review. OpenCode can load this plugin once per open project: each handles its own.
        if (session.parentID || session.location.directory !== ctx.location.directory) return "";
        const job = run("teachback", ["hook"], { timeout: 10_000 });
        job.child.stdin.end(); // the hook reads the session JSON the other agents send, up to EOF
        return JSON.parse((await job).stdout).hookSpecificOutput.additionalContext;
      } catch (error) {
        console.warn("teachback: `teachback hook` failed, so no review this session", error);
        return "";
      }
    }

    await ctx.session.hook("context", async (event) => {
      if (!texts.has(event.sessionID)) texts.set(event.sessionID, sessionText(event.sessionID));
      const text = await texts.get(event.sessionID);
      if (text) event.system.push({ type: "text", text });
    });
  },
};
