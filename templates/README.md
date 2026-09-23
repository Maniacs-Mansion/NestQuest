# Reusing the development cycle prompt

`ORCHESTRATOR-PROMPT.template.md` is the current NestQuest controller
prompt with project-specific names, models, branches, identities, and launcher
paths replaced by placeholders. `nestquest.profile.json` is the working
example. Render a concrete prompt with:

```bash
scripts/render-cycle-prompt templates/nestquest.profile.json --output /tmp/opencode/nestquest-prompt.md
scripts/render-cycle-prompt templates/nestquest.profile.json --runtime terminal --output /tmp/opencode/nestquest-terminal-prompt.md
```

For another project, copy the profile and set its project name, tracker,
context store, models, branch names, release owner, example IDs, review
account, and installed launcher paths. Review the rendered result section by
section, especially task/feature semantics, release rules, permissions,
review gates, and the host runtime section. The template assumes an OpenCode
controller, a feature/task tracker, a versioned context store, a code host,
and a separate reviewer and approver. Adapt those sections when the project's
systems differ. The default `service` runtime reproduces the CTXD prompt.
The `terminal` runtime replaces Section 27 with a single-session foreground
loop suitable for `opencode --agent ... --prompt ...`.

For NestQuest, `nq-orchestrate --print-prompt` emits the fully rendered
foreground prompt without starting OpenCode. `nq-orchestrate [mission.md]`
renders that same prompt, appends the optional mission, and supplies it to the
foreground orchestrator agent.

Publish the reviewed **service-rendered** prompt into that project's context
store with its version check when CTXD should retain both runtime choices.
Give the project its own agent definitions, broker, profile, and terminal
launcher. The template itself does not start an orchestrator or register
another project.
