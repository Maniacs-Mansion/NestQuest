# NestQuest foreground orchestrator

OpenCode 1.18.32 loads the named agents from `.opencode/agents/`. Their
models match the current NestQuest CTXD prompt: DeepSeek V4.1 Flash for the
foreground orchestrator and approver, and GLM 5.3 Flash for development.
Run orchestration directly from a shell:

```bash
nq-orchestrate
nq-orchestrate mission.md
cat mission.md | nq-orchestrate -
nq-orchestrate --print-prompt > nestquest-orchestrator.md
```

The launcher renders the project prompt with the foreground terminal runtime,
stops the dormant legacy service, refuses immediately when another NestQuest
TUI is open, and then replaces itself with OpenCode using
`terminal-orchestrator`. There is no background polling process and no wait
for a controller tick. Exit or interrupt the TUI to stop the foreground run;
resume that OpenCode session when a host-forced yield needs continuation.

`scripts/nq-agent` launches developer and approver sessions with fixed agent
definitions and no `--auto` flag. Headless OpenCode runs use `--pure` so the
global idle-notification plugin does not notify on every controller tick.
The approver's shell permission permits only the installed
`nq-approve-merge` broker for Gitea. That broker requires exact-head
Claude approval evidence, an exact-head Gitea approval by `review_agent`,
the `dev` target, a mergeable PR, and passing configured checks before it
requests a squash merge with Gitea's atomic `head_commit_id` guard.
`scripts/nq-review` launches the independent
Claude review in a noninteractive read-only session in the task worktree,
checks the head again afterward, saves
the output under `/tmp/opencode`, and posts the Gitea approval.
The approver verifies the reviewed head again before a merge.

The terminal launcher uses a stable copy of this configuration and scripts
at `/home/overseer/.local/share/nestquest-controller`; it does not depend on
which task branch is checked out in the primary NestQuest directory. Install
that copy, run `scripts/nq-controller --check`, and verify the OpenCode
agents (terminal-orchestrator, developer, and approver)
with `opencode debug agent <name>` while `OPENCODE_CONFIG_DIR` points at the
installed `.opencode` directory. Install `scripts/nq-orchestrate` in
`~/.local/bin/`. For the global slash command, also install
`.opencode/agents/terminal-orchestrator.md` under
`~/.config/opencode/agents/` and
`deploy/opencode-global-commands/start-nestquest-development.md` under
`~/.config/opencode/commands/`. The old `nestquest-controller.service` remains static and
inactive only for migration safety; foreground launch stops it.

Inside an already-open OpenCode TUI, `/start-development` (or the global
`/start-nestquest-development`) switches to the same foreground
`terminal-orchestrator` behavior immediately. The shell launcher is the
preferred entry point when supplying a mission prompt file.

`templates/ORCHESTRATOR-PROMPT.template.md` and
`templates/nestquest.profile.json` make the current CTXD cycle prompt
adaptable to another project. See `templates/README.md` before publishing a
rendered prompt for a new project.

The CTXD preflight reads the configured HTTP/MCP server's NestQuest prompt.
It deliberately does not inspect `/home/overseer/.ctx/ctxd.db`, which belongs
to a different local store and lacks this project.

All four agent credentials are currently readable by the same Unix account.
The Gitea review and merge gates enforce normal workflow sequencing, but
they are not a hard isolation boundary against a process running as that
account. Strong isolation requires separate OS identities and protected
credentials for the controller, reviewer, and approver.

The terminal runtime repeatedly executes CONTROLLER_TICK within the foreground
session. Neither a feature merge nor a progress report ends the run while
eligible work remains. A host-forced yield returns a continuation checkpoint
that can be resumed in the same OpenCode session.

Do not put tokens in this repository or in unit files. Existing OpenCode MCP
connections supply CTXD and Maestro. Rotate those MCP tokens as a coordinated
operation across every consumer before revoking the old values.
