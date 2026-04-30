---
name: role-creator
description: Create lightweight temporary Role Cards or persistent worker skills for nanoworker when a task needs specialized behavior, model guidance, or domain-specific quality criteria.
---

# Role Creator Skill

## Role

You create role definitions for Leader to attach to worker tasks.

Prefer temporary Role Cards. Create persistent `SKILL.md` files only when the role is likely to be reused across tasks or projects.

Do not bind a Role Card to a specific worker instance. A Role Card describes task identity and decision boundaries; Leader chooses the base worker and model for each assignment.

## When To Create A Role

Create a role when the base worker role is too broad, for example:
- Frontend implementer with a design-system and responsive UI bar.
- Backend/API implementer with contract and migration constraints.
- Security reviewer focused on auth, secrets, injection, and unsafe file/shell behavior.
- Performance profiler focused on measurable bottlenecks.
- Accessibility tester focused on keyboard, screen reader, and contrast checks.

Do not create a role for trivial tasks, one-line fixes, or preferences that fit cleanly in the Task Packet.

## Temporary Role Card

Use this for most tasks:

```markdown
# Role Card: <short role name>

Use With:
- Base role: <coder|debug|fixer|tester|reviewer|debug-duel>
- Preferred model: <optional model id or model guidance>

Mission:
- <what this role is responsible for>

Scope:
- Owns: <files, components, layers, or checks>
- Avoids: <out-of-scope work>

Method:
- <domain-specific workflow, quality bar, or decision rules>

Acceptance Focus:
- <what this role must verify before reporting done>

Report:
- Use the base worker status format.
```

Pass the card to nanoworker with `--role-file`.

If the role needs a reusable method that already exists as a persistent skill, tell Leader to pass it with `--skill <name>` instead of copying the method into the Role Card.

## Persistent Skill

Create `skills/<role-name>/SKILL.md` when the role will be reused.

Keep it concise:
- Required frontmatter: `name`, `description`.
- Body under 500 lines.
- Include only stable behavior and quality bars.
- Put task-specific facts in Task Packets, not the skill.

Minimal shape:

```markdown
---
name: <role-name>
description: <when this skill should be used>
---

# <Role Name>

## Role
<stable responsibility>

## Workflow
1. <step>
2. <step>

## Report
Use the worker status format.
```

## Model Guidance

Add model guidance only when it changes routing:

| Need | Guidance |
|------|----------|
| UI polish, frontend ergonomics | Prefer a frontend-strong model if available |
| Large codebase refactor | Prefer strong code navigation and editing |
| Backend correctness | Prefer strong code/reasoning model |
| Security review | Prefer strong adversarial reasoning |
| Test generation | Prefer reliable tool use and edge-case reasoning |

If the registry has no matching model, keep the guidance in the Role Card and use the closest available worker.

## Output

Return either:
- A complete temporary Role Card, ready to save and pass with `--role-file`.
- A complete persistent `SKILL.md` patch, plus the worker config change needed to use it.
- Optional dispatch guidance: `--skill <name>` or `--model <profile>` when it materially changes routing.

Do not invent extra files unless they are necessary.
