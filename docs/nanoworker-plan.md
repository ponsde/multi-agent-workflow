# nanoworker Plan

> Working direction for Leader-dispatched worker assignments.

## Direction

The workflow is organized around Leader-dispatched assignments.

Leader is the main agent in the workflow:
- Talks with the user and understands intent.
- Decides how to proceed and when worker help is useful.
- Triggers or loads Leader/runtime skills when the current work needs a reusable method.
- Chooses worker template, model, tool policy, Role Card, and persistent skills.
- Calls nanoworker when an assignment is ready to run.
- Reads worker results, validates outcomes, and decides the next step.
- Writes feedback about Role Cards, skills, models, and role fit after evidence exists.
- Adjusts long-lived role prompts only when Leader's own judgment says the role is weak.

For dispatched assignments, nanoworker provides:
- A small worker runtime.
- A model/provider registry.
- A managed role prompt registry.
- Tool policy enforcement.
- Structured assignment results and journal data.
- Local candidate data and historical notes that support Leader's current judgment.

## Boundaries

- Keep the default route Task Packet-first rather than rebuilding opsx/OpenSpec as a fixed flow.
- Use `suggest` as candidate data for Leader's current judgment.
- Route follow-up assignments through Leader's validation and planning loop.
- Trigger Leader/runtime skills in the Leader runtime before dispatching worker-facing materials.
- Represent concurrency with repeated invocations plus `--assignment-id`, not numbered worker identities such as `coder-1/2/3`.
- Treat long-lived prompts and role metadata as Leader-maintained data.
- Update role metadata from Leader feedback after evidence exists.
- Make remote role sources explicit when they exist.
- Resolve role names through the managed registry.

## Current Snapshot

Implemented so far:

- Worker templates: `write`, `debug`, `fix`, `verify`, `review`.
- Base roles: `coder`, `debug`, `fixer`, `tester`, `reviewer`.
- Legacy `debug-duel` remains available as an optional old-flow skill.
- OpenAI-compatible and Anthropic-native provider support through env-first config.
- Model profiles with strengths, preferred roles, and conservative fallback.
- Tool policies:
  - `product-write`
  - `read-only-review`
  - `test-write-only`
  - `no-shell`
  - `read-only-no-shell`
- Temporary Role Cards through `--role-file`.
- Persistent skills through `--skill`.
- `suggest --candidates` returns candidate role/model/tool-policy data for Leader, includes matching persistent roles from registry metadata, and attaches relevant local Leader feedback plus compact summaries when available.
- `journal` records assignment snapshots and outcomes.
- `feedback` records Leader-authored notes about Role Cards, skills, models, and assignment fit.
- `feedback list` and `stats` expose local history for Leader inspection.
- Worker results include optional Leader-routing fields: `role_fit`, `risk_level`, `next_recommended_roles`, `handoff`, and `evidence`.
- `smoke`, `doctor`, `list`, `migrate-config`, and `init` exist for diagnostics/setup.

Current role maintenance commands:

```bash
nanoworker role list
nanoworker role show reviewer
nanoworker role path reviewer
nanoworker role copy reviewer style-reviewer
nanoworker role edit style-reviewer
nanoworker role skill "Security Reviewer" --description "Reusable security review role" --base-role reviewer --tag security --preferred-model claude-sonnet
nanoworker role import /path/to/roles/reviewer/SKILL.md --id reviewer --base-role reviewer --tag review
nanoworker role import-dir /path/to/roles
nanoworker role register reviewer --path ~/.nanoworker/roles/reviewer/SKILL.md
nanoworker role remove reviewer
nanoworker role doctor
nanoworker feedback frontend-ui-card --target-type role-card --assignment-id frontend-a --tag frontend --comment "Good fit for frontend component polish."
nanoworker feedback list --target frontend-ui-card
nanoworker stats --target frontend-ui-card --target-type role-card --last-days 30
```

## Role Prompt Model

Long-lived role prompts live in the managed nanoworker role store.

Leader-side skills are different from worker-side skills. Leader/runtime skill triggering guides the current Leader agent before planning, debugging, reviewing, or dispatching. If the runtime supports automatic skill activation, Leader should use it before acting. If it does not, Leader should use skill descriptions and local context as a manual trigger checklist. For a worker assignment, nanoworker loads the worker-facing `--skill` and `--role-file` selected for that assignment.

The intended runtime chain is:

```text
role id in config
  -> managed role registry
  -> managed SKILL.md path
  -> injected into worker system prompt
```

The prompt/data layers are:

- Leader runtime skill: reusable method for Leader's own thinking, planning, debugging, review, verification, or prompt maintenance.
- Base role skill: worker stable behavior, reporting format, role boundaries, and common avoidances.
- Worker persistent skill: reusable worker specialization or method passed with `--skill`.
- Temporary Role Card: one assignment's task identity, specialization, constraints, and quality focus.
- Task Packet: concrete goal, scope, context, and acceptance criteria.
- Leader feedback: post-run notes about suitability, role fit, model fit, and when to reuse or avoid a card/skill.

Leader feedback is metadata for future Leader decisions. When a later assignment benefits from a note, Leader can deliberately include the relevant context in the Task Packet or role material.

Example:

```text
system:
- worker identity header
- reviewer base skill
- optional security-review persistent skill
- optional style-review Role Card

user:
- Task Packet
```

## Role Store Target

The target role store is:

```text
~/.nanoworker/roles/
├── index.json
├── coder/SKILL.md
├── debug/SKILL.md
├── fixer/SKILL.md
├── reviewer/SKILL.md
└── tester/SKILL.md
```

`index.json` should record enough metadata for stable resolution:

```json
{
  "version": 1,
  "roles": {
    "reviewer": {
      "id": "reviewer",
      "path": "~/.nanoworker/roles/reviewer/SKILL.md",
      "sha256": "...",
      "source": "user",
      "frontmatter": {
        "name": "reviewer",
        "description": "..."
      },
      "tags": ["review", "security"],
      "base_role": "reviewer",
      "preferred_models": ["claude-sonnet"]
    }
  }
}
```

Runtime lookup should go through this registry. A worker should not find role files by scanning a user project or assuming a checkout path.

## Install Defaults Status

The current implementation keeps `nanoworker role install-defaults` as a hidden developer/bootstrap compatibility command. It copies bundled `skills/` templates into `~/.nanoworker/roles/`, but it is not listed in regular `role --help` and should not be part of the normal user path.

This is not the desired final UX.

Problems:
- The source is implicit.
- It can look like remote installation even though it is local.
- It couples role bootstrapping to package/repo layout.
- It makes ownership unclear: are roles package defaults or user-maintained data?

Current direction:
- Keep `install-defaults` hidden as a developer/bootstrap compatibility command for now.
- Keep role installation explicit instead of pulling from a hardcoded checkout path.
- Let users import or register roles explicitly.
- Never pull from a remote unless the command name and source make that obvious.

Current explicit commands:

```bash
nanoworker role import /path/to/roles/reviewer/SKILL.md --id reviewer
nanoworker role import-dir /path/to/roles
nanoworker role register reviewer --path ~/.nanoworker/roles/reviewer/SKILL.md
nanoworker role remove reviewer
nanoworker role doctor
```

If remote role sources are added later, make them explicit:

```bash
nanoworker role source add official https://github.com/example/nanoworker-roles.git
nanoworker role source pull official
nanoworker role import official/reviewer
```

No command should silently fetch remote data.

## Expected Workflow

1. User installs nanoworker.
2. User creates or imports role prompts into `~/.nanoworker/roles/`.
3. nanoworker records role metadata in `index.json`.
4. Leader calls `nanoworker list` and `nanoworker role list` to inspect available execution templates and roles.
5. Leader writes a Task Packet.
6. Leader optionally creates a Role Card.
7. Leader dispatches a worker.
8. Worker returns structured result data.
9. Leader decides whether to accept, review, fix, verify, or adjust a prompt.
10. Leader optionally records feedback about the Role Card, skill, model, or assignment.

## Role Adjustment Loop

Leader should adjust prompts and role-card data based on evidence:

- Coder ignored project style -> inspect/copy/edit `coder` or add `style-coder`.
- Reviewer reports noisy findings -> tune `reviewer` or create `style-reviewer`.
- Tester misses acceptance criteria -> tune `tester` or create a domain-specific verification skill.
- Frontend Role Card works well for design-system tasks -> add Leader notes such as "good for frontend component polish".
- Backend Role Card works well for database migrations -> add Leader notes such as "good for backend database/schema changes".
- A role/model pairing performs poorly -> record the fit issue before changing default prompts.

Recommended pattern:

```bash
nanoworker role copy reviewer style-reviewer
nanoworker role edit style-reviewer
nanoworker review --workspace /repo --message-file /tmp/review.md --skill style-reviewer
```

Base roles should remain generic. Project- or domain-specific guidance should be a copied role, persistent skill, Role Card, or Task Packet.

## Leader Feedback Data

nanoworker can store and surface Leader-authored role notes for future candidate selection.

Useful feedback fields:

```json
{
  "target": "frontend-ui",
  "target_type": "role_card|skill|base_role|model",
  "assignment_id": "frontend-a",
  "leader_comment": "Good fit for frontend component polish and responsive layout tasks.",
  "fit_tags": ["frontend", "ui", "responsive"],
  "base_role": "coder",
  "model_fit": "good",
  "role_fit": "good",
  "reuse_when": ["component work", "design-system cleanup"],
  "avoid_when": ["backend contract design"],
  "accepted": true
}
```

This data helps `suggest --candidates` show better local candidate context, for example "this card has been useful for frontend UI" or "this skill is noisy for backend database work". Matching feedback is also summarized as counts, top tags, fit distributions, and recent comments, then considered alongside the current Task Packet.

## Near-Term TODO

1. Decide whether role metadata should get a Leader-authored latest-summary field in addition to journal feedback.
2. Decide whether `role install-defaults` should eventually be removed rather than kept as hidden compatibility.
3. Add export/import tooling for role stores if cross-machine reuse becomes important.

## Open Questions

- Should built-in roles ship as package resources only, or should the repo stop containing role templates after packaging?
- Should `role register --path` allow external paths, or should all roles be copied into `~/.nanoworker/roles/`?
- Should modified role hashes be warnings only, or should nanoworker require `role trust` after manual edits?
- Should Leader feedback live only in the journal, or should role metadata also keep a compact latest-summary?
