# NestQuest controller

OpenCode 1.18.31 loads the three named agents from `.opencode/agents/`. Their
models match the current NestQuest CTXD prompt (version 6): DeepSeek V4.1
Flash for controller and approver, GLM 5.3 Flash for development. The
controller runs one OpenCode turn at a time, then starts a fresh turn based on
Maestro, CTXD, Git, and pull-request state. Its state file is
`~/.local/state/nestquest-controller/last-run.json` (mode 0600). A lock allows
only one controller process. It waits while an interactive OpenCode session is
open for the NestQuest checkout.

`scripts/nq-agent` launches developer and approver sessions with fixed agent
definitions and no `--auto` flag. Headless OpenCode runs use `--pure` so the
global idle-notification plugin does not notify on every controller tick.
The approver's shell permission permits read-only Git commands and only the
installed `nq-approve-merge` broker for Gitea. That broker requires exact-head
Claude approval evidence, the `dev` target, a mergeable PR, and passing
configured checks before it requests a squash merge. `scripts/nq-review` launches the independent
Claude review in the task worktree and checks the exact head before review.
The approver verifies the reviewed head again before a merge.

The production service uses a stable copy of this configuration and scripts
at `/home/overseer/.local/share/nestquest-controller`; it does not depend on
which task branch is checked out in the primary NestQuest directory. Install
that copy, run `scripts/nq-controller --check`, and verify all three agents
with `opencode debug agent <name>` while `OPENCODE_CONFIG_DIR` points at the
installed `.opencode` directory. Install `deploy/nestquest-controller.service`
under `/etc/systemd/system/`, then enable it. The service waits for an open
interactive NestQuest session to close before starting work.

The CTXD preflight reads the configured HTTP/MCP server's NestQuest prompt.
It deliberately does not inspect `/home/overseer/.ctx/ctxd.db`, which belongs
to a different local store and lacks this project.

A tick has an explicit six-hour timeout. On timeout or an OpenCode error, the
next tick must reconcile external state before acting. Three consecutive
failed ticks stop the service. A BLOCKED verdict also stops it. QUIESCENT
causes a five-minute poll. Neither a feature merge nor a progress report
stops the controller while eligible work remains.

Do not put tokens in this repository or in unit files. Existing OpenCode MCP
connections supply CTXD and Maestro. Rotate those MCP tokens as a coordinated
operation across every consumer before revoking the old values.
