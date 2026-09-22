# NestQuest controller

OpenCode 1.18.31 loads the three named agents from `.opencode/agents/`. Their
models match the current NestQuest CTXD prompt: DeepSeek V4.1
Flash for controller and approver, GLM 5.3 Flash for development. The
controller runs one OpenCode turn at a time, then starts a fresh turn based on
Maestro, CTXD, Git, and pull-request state. Its state file is
`~/.local/state/nestquest-controller/last-run.json` (mode 0600). A lock allows
only one controller process. It waits while an interactive OpenCode session is
open for the NestQuest checkout.

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

The production service uses a stable copy of this configuration and scripts
at `/home/overseer/.local/share/nestquest-controller`; it does not depend on
which task branch is checked out in the primary NestQuest directory. Install
that copy, run `scripts/nq-controller --check`, and verify all four OpenCode
agents (orchestrator, developer, approver, cycle-control)
with `opencode debug agent <name>` while `OPENCODE_CONFIG_DIR` points at the
installed `.opencode` directory. Install `deploy/nestquest-controller.service`
under `~/.config/systemd/user/` and reload the user manager. Its lack of an
`[Install]` section makes it a manual-only unit; development starts only
when requested. Copy `deploy/opencode-global-commands/*.md` into
`~/.config/opencode/commands/` and `.opencode/agents/cycle-control.md` into
`~/.config/opencode/agents/` for the commands to work from older branches.
The host has lingering
enabled for the `overseer` user. The service waits for an open interactive
NestQuest session to close before starting work.

In NestQuest's OpenCode session, use `/start-development`,
`/stop-development`, or `/development-status`. The matching global
`/start-nestquest-development`, `/stop-nestquest-development`, and
`/nestquest-development-status` commands work even while an older branch is
checked out. Starting the unit in an interactive NestQuest session puts it
in a waiting state; close that session to let the first controller tick run.
The commands call `scripts/nq-cycle`; they do not run a developer inside
the interactive chat.

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

A tick has an explicit six-hour timeout. On timeout or an OpenCode error, the
next tick must reconcile external state before acting. Three consecutive
failed ticks stop the service. A BLOCKED verdict also stops it. QUIESCENT
causes a five-minute poll. Neither a feature merge nor a progress report
stops the controller while eligible work remains.

Do not put tokens in this repository or in unit files. Existing OpenCode MCP
connections supply CTXD and Maestro. Rotate those MCP tokens as a coordinated
operation across every consumer before revoking the old values.
