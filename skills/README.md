# Skills

This directory contains the skills used by the multi-agent workflow.

The current direction is Task Packet-first and platform-independent:
- Leader is a responsibility, not a fixed runtime.
- nanoworker runs lightweight worker processes.
- Role Cards handle one-off specialization.
- Leader/runtime skills are triggered by the current Leader agent, not by nanoworker.
- OpenSpec/opsx skills are kept as a legacy compatibility layer.

## Directory Structure

```
skills/
├── leader/
│   └── SKILL.md          # Platform-independent orchestration
├── role-creator/
│   └── SKILL.md          # Temporary Role Card / persistent role creation
├── coder/
│   └── SKILL.md          # Implementation worker
├── debug/
│   └── SKILL.md          # Diagnose/fix worker
├── fixer/
│   └── SKILL.md          # Scoped fix worker
├── reviewer/
│   └── SKILL.md          # Read-only review worker
├── debug-duel/
│   └── SKILL.md          # Legacy competitive bug-hunt worker
├── tester/
│   └── SKILL.md          # Verification worker
└── opsx/
    ├── agent-change-review.SKILL.md
    ├── agent-apply.SKILL.md
    ├── agent-apply-duel.SKILL.md
    └── agent-verify.SKILL.md
```

## Roles

| Role | Purpose |
|------|---------|
| Leader | Clarifies user intent, creates Task Packets, selects workers/models, dispatches nanoworker, validates results |
| Role Creator | Creates lightweight Role Cards or persistent skills when a task needs specialized behavior |
| Coder | Implements scoped changes from a Task Packet |
| Debug | Diagnoses scoped defects and fixes when authorized |
| Fixer | Applies accepted findings or failing-check fixes without redesign |
| Reviewer | Performs read-only review and returns actionable findings |
| Tester | Verifies behavior and reports pass/fail evidence |
| Debug-Duel | Optional legacy competitive bug-hunt skill |

## Leader Skill Triggering

Leader-side skills guide the current Leader's thinking and decisions. If the runtime supports automatic skill activation, use the runtime's trigger system. Otherwise, Leader should read skill descriptions as trigger metadata and load the relevant method before planning, debugging, reviewing, verifying, or creating roles.

nanoworker does not trigger Leader skills. It only loads the worker-facing `--skill` and `--role-file` that Leader selected for an assignment.

## Worker Skill Loading

nanoworker loads skills from this directory through worker config:

```json
{
  "models": {
    "gpt-5.4": { "model": "openai/gpt-5.4", "strengths": ["backend", "reasoning", "tests"] },
    "claude-sonnet": { "model": "anthropic/claude-sonnet-4-6", "strengths": ["frontend", "ui", "review"] }
  },
  "workers": {
    "write": { "role": "coder", "tool_policy": "product-write", "model": "gpt-5.4", "skills": ["coder"], "max_iterations": 30 },
    "debug": { "role": "debug", "tool_policy": "product-write", "model": "gpt-5.4", "skills": ["debug"], "max_iterations": 30 },
    "fix": { "role": "fixer", "tool_policy": "product-write", "model": "gpt-5.4", "skills": ["fixer"], "max_iterations": 30 },
    "verify": { "role": "tester", "tool_policy": "test-write-only", "model": "gpt-5.4", "skills": ["tester"], "max_iterations": 20 },
    "review": { "role": "reviewer", "tool_policy": "read-only-review", "model": "claude-sonnet", "skills": ["reviewer"], "max_iterations": 20 }
  }
}
```

Skill names may use the folder name or the `name:` value in `SKILL.md` frontmatter.
Worker names are templates, not personas. Run the same template concurrently and use `--assignment-id` when you need traceable parallel work. `role` controls the base identity/skill expectation; `tool_policy` controls exposed tools.

Leader may add persistent skills for a single assignment without changing worker config:

```bash
nanoworker write --workspace /path/to/project --message-file /tmp/task.md --skill frontend-ui --model claude-sonnet --assignment-id frontend-a
```

## Role Cards

For a one-off specialized assignment, create a temporary Role Card and pass it to nanoworker:

```bash
nanoworker role create "Frontend Implementer" --task-file /tmp/task.md --output /tmp/frontend-role.md
nanoworker write --workspace /path/to/project --message-file /tmp/task.md --role-file /tmp/frontend-role.md
```

For reusable behavior, create a persistent skill and pass it by name:

```bash
nanoworker role skill "Security Reviewer" --description "Reusable security review role"
nanoworker review --workspace /path/to/project --message-file /tmp/review.md --skill security-reviewer
```

Use `skills/role-creator/SKILL.md` for Role Card structure and persistence rules.

The repository `skills/` directory is the bundled template source. Runtime roles are managed under `~/.nanoworker/roles/` with `index.json` metadata. Use:

```bash
nanoworker role import-dir /path/to/roles
nanoworker role list --json
```

Leader-driven prompt maintenance:

```bash
nanoworker role list
nanoworker role show reviewer
nanoworker role copy reviewer style-reviewer
nanoworker role edit style-reviewer
```

Use `copy` before tuning a base role when the adjustment is project- or task-specific.

## Legacy opsx

`skills/opsx/` contains the old OpenSpec-oriented workflow skills. They are not the default path anymore. Use them only when a task explicitly uses the old OpenSpec flow.
