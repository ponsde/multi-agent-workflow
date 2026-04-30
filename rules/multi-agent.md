# Multi-Agent Rule

> Optional global reminder for any Leader runtime that supports always-loaded project rules.

```markdown
# Multi-Agent Collaboration

Leader is a responsibility, not a fixed platform.

Default workflow:
1. Clarify the user's goal.
2. Create a concise Task Packet.
3. Add a temporary Role Card when a worker needs specialized behavior.
4. Dispatch nanoworker with `--message-file` and optional `--skill`, `--role-file`, or `--model`.
5. Route by worker JSON `status`.
6. Validate before reporting completion.

Assignment policy:
- Treat workers as immutable templates.
- Do not create numbered workers just to express parallelism; use the same template concurrently.
- Use `--assignment-id` when parallel assignments need stable trace names.
- Use `--skill` for reusable methods and `--role-file` for temporary task identity.
- Use `--model <profile-or-id>` only for the current assignment; do not rewrite worker config.
- Keep `role` for base identity/skill behavior and `tool_policy` for tool permissions.
- Use `--tool-policy <policy>` when a single assignment needs a different tool boundary.
- `nanoworker suggest` is only a registry-based hint; Leader still owns the final assignment decision.
- Use `nanoworker suggest --candidates` for candidate Role Card data; treat it as evidence, not orchestration.
- Prefer `reviewer` for read-only findings, `fixer` for accepted findings, `debug` when root cause is unknown, and `tester` for verification evidence.
- Use `nanoworker role list/show/path/edit/copy` when Leader needs to inspect or tune long-lived role prompts.
- Long-lived roles resolve through the managed `~/.nanoworker/roles/index.json` registry; repository `skills/` are bundled defaults, not the runtime source of truth.
- Model fallback should only happen before recorded write/edit/bash side effects.

Context policy:
- Put critical context directly in the Task Packet.
- Reference AI-CONTEXT.md, OpenSpec, or other context files only when useful.
- Do not assume ignored or untracked context files are visible in worktrees.

See:
- `skills/leader/SKILL.md`
- `skills/role-creator/SKILL.md`
- `docs/nanoworker-setup.md`
```
