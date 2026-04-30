# 使用指南

> 当前默认路线：平台无关 Leader + Task Packet + worker assignment。
> Leader 与用户交流、理解目标、生成 Task Packet，并为每个 assignment 选择 base role、Role Card、skill、model 和工具边界；nanoworker 按这份分派输入运行 worker。

旧的 OpenSpec/Claude Code opsx 流程仍保留在 `skills/opsx/`，但不再是默认路径。

方向、当前实现和后续计划见 [nanoworker-plan.md](nanoworker-plan.md)。

## 前提条件

- Python 3.11+（`pyproject.toml` 要求）
- nanoworker 已安装（详见 [nanoworker-setup.md](nanoworker-setup.md)）
- `~/.nanoworker/config.json` 已配置 providers、models（可选）和 workers；密钥放在环境变量或 GitHub Actions secrets
- 一个可作为 Leader 的 agent/runtime：Claude Code、Codex、Gemini、Pi、自建 CLI/TUI 均可

## 角色技能

| 路径 | 用途 |
|------|------|
| `skills/leader/SKILL.md` | Leader 编排：澄清需求、生成 Task Packet、选 worker/model、验收 |
| `skills/role-creator/SKILL.md` | 创建临时 Role Card 或持久角色 skill |
| `skills/coder/SKILL.md` | 实现 worker |
| `skills/debug/SKILL.md` | 定位问题、解释根因，必要时修复 |
| `skills/fixer/SKILL.md` | 根据 findings 或失败证据做定点修复 |
| `skills/reviewer/SKILL.md` | 只读审查，输出 findings，不改代码 |
| `skills/tester/SKILL.md` | 验证 worker |
| `skills/debug-duel/SKILL.md` | 旧流程的对抗赛审查 skill，可选保留 |

## 配置 nanoworker

示例 `~/.nanoworker/config.json`：

```bash
export LLM_API_KEY="..."
export LLM_API_BASE="https://xianyutoken.com/v1"

# Anthropic native 格式通常需要非 /v1 base
export LLM_ANTHROPIC_API_BASE="https://xianyutoken.com"
```

本机可把这些 export 放到 `~/.nanoworker/env`；nanoworker 会自动读取，且不会覆盖当前进程已有 env。

```json
{
  "providers": {
    "openai": {
      "api_key_env": "LLM_API_KEY",
      "api_base_env": "LLM_API_BASE"
    },
    "anthropic": {
      "api_key_env": "LLM_API_KEY",
      "api_base_env": "LLM_ANTHROPIC_API_BASE"
    }
  },
  "models": {
    "gpt-5.4": {
      "model": "openai/gpt-5.4",
      "strengths": ["backend", "reasoning", "refactor", "tests"],
      "preferred_roles": ["coder", "debug", "fixer", "tester"],
      "fallbacks": ["claude-sonnet"],
      "cost_tier": "medium",
      "latency_tier": "medium"
    },
    "claude-sonnet": {
      "model": "anthropic/claude-sonnet-4-6",
      "strengths": ["frontend", "ui", "review", "code"],
      "preferred_roles": ["coder", "debug", "fixer", "reviewer"],
      "fallbacks": ["gpt-5.4"],
      "cost_tier": "medium",
      "latency_tier": "medium"
    }
  },
  "workers": {
    "write": { "role": "coder", "tool_policy": "product-write", "model": "gpt-5.4", "skills": ["coder"], "max_iterations": 30 },
    "debug": { "role": "debug", "tool_policy": "product-write", "model": "gpt-5.4", "skills": ["debug"], "max_iterations": 30 },
    "fix": { "role": "fixer", "tool_policy": "product-write", "model": "gpt-5.4", "skills": ["fixer"], "max_iterations": 30 },
    "verify": { "role": "tester", "tool_policy": "test-write-only", "model": "gpt-5.4", "skills": ["tester"], "max_iterations": 20 },
    "review": { "role": "reviewer", "tool_policy": "read-only-review", "model": "claude-sonnet", "skills": ["reviewer"], "max_iterations": 20 }
  },
  "journal": {
    "enabled": false,
    "path": "~/.nanoworker/journal.jsonl"
  }
}
```

按需增加 worker 和 model profile。`workers` 更像基础执行模板，同一个模板可被无状态地并发调用；需要区分并发 assignment 时使用 `--assignment-id`。`role` 决定基础身份和底座 skill，`tool_policy` 决定工具权限，临时职责用 Role Card。Leader 可以用 `--model <profile-or-model-id>` 在单次 assignment 覆盖模型，不会写回 worker 配置。

## 基本流程

1. 用户向 Leader 描述目标。
2. Leader 澄清关键缺口，必要时阅读项目文件，并触发或加载适合当前工作的 Leader/runtime skill，例如 brainstorming、debugging、review、verification、role creation；随后把 worker 需要的材料写入 Task Packet 或命令参数。
3. Leader 生成 Task Packet。
4. 如果任务需要专业角色，Leader 用 `role-creator` 生成 Role Card。
5. Leader 选择 worker-facing persistent skill，必要时通过 `--skill` 显式传给 nanoworker。
6. Worker 返回 stdout JSON。
7. Leader 根据 `status`、findings、evidence 和自己的验收判断路由后续：接受、补上下文、派 Reviewer、派 Fixer、派 Tester，或要求重新执行。
8. Leader 可以为本次 Role Card、skill、model 记录评语，例如适合前端 UI、后端数据库、后端 API、迁移修复等。
9. Leader 验证结果并向用户汇报。

## Task Packet

```markdown
# Task Packet

Goal:
- <要达成什么>

Scope:
- Owned files: <允许修改的文件/目录>
- Out of scope: <不要做什么>

Context:
- <必要背景、相关文件、错误日志、用户决策>

Acceptance:
- <验收标准或必须通过的命令>

Coordination:
- <并行边界、依赖关系、合并注意事项>

Role Notes:
- <可选角色/模型偏好>
```

## Role Card

Role Card 是单次 assignment 的临时角色，不写回 worker 配置。可以手写，也可以让 CLI 按任务描述生成一个可编辑的起点：

```bash
nanoworker role create "Frontend Implementer" \
  --task-file /tmp/task.md \
  --preferred-model claude-sonnet \
  --skill frontend-ui \
  --output /tmp/frontend-role.md
```

```markdown
# Role Card: Frontend Implementer

Use With:
- Base role: coder
- Preferred model: frontend-strong model if available

Mission:
- Implement the UI slice with existing design conventions.

Scope:
- Owns: src/components/, src/styles/
- Avoids: backend contracts unless needed for typing.

Method:
- Match existing component patterns.
- Verify responsive layout and empty/error/loading states.

Acceptance Focus:
- UI renders correctly and tests/build pass.

Report:
- Use the base worker status format.
```

如果这个角色会长期复用，再沉淀为持久 skill：

```bash
nanoworker role skill "Security Reviewer" \
  --description "Reusable security review role" \
  --base-role reviewer \
  --tag security \
  --tag backend \
  --preferred-model claude-sonnet

nanoworker review \
  --workspace /path/to/project \
  --message-file /tmp/review.md \
  --skill security-reviewer
```

长期角色保存在 nanoworker 托管的 `~/.nanoworker/roles/`，并由 `~/.nanoworker/roles/index.json` 记录 id、路径、hash、frontmatter、`tags`、`base_role` 和 `preferred_models`。运行时通过 registry 解析角色；仓库里的 `skills/` 是出厂模板，需要显式导入或注册。

```bash
nanoworker role import /path/to/reviewer/SKILL.md --id reviewer --base-role reviewer --tag review
nanoworker role import-dir /path/to/roles
nanoworker role register reviewer --path ~/.nanoworker/roles/reviewer/SKILL.md
nanoworker role doctor
nanoworker role list --json
```

`role install-defaults` 保留为隐藏的开发/bootstrap 兼容入口；常规路径使用显式导入、注册、复制和编辑。

`suggest --candidates` 会用 role metadata 匹配持久角色，并把相关 Leader feedback 压成 `feedback_summary`；这些会进入 Leader 的候选上下文。

提示层分工：

| 层 | 用途 |
|----|------|
| Leader Runtime Skill | Leader 自己的思考、规划、调试、审查、验证或提示词维护方法 |
| Base Role Skill | 通用工作方式、工具使用习惯、报告格式、边界和避免事项 |
| Worker Persistent Skill | 通过 `--skill` 传给 worker 的可复用专业能力，例如 security-review、frontend-ui、migration-check |
| Role Card | 本次任务身份、专业关注点、方法偏好和适用模型提示 |
| Task Packet | 本次具体目标、scope、上下文和验收标准 |
| Leader Feedback | Leader 验收后的适用场景、效果评价、复用/避免建议 |

Role Card 可以写“该怎么做”，但应优先写工作方法和质量标准，而不是无必要地微操实现方案。Leader 的评语是后续候选数据，例如“这个 Role Card 适合前端组件打磨”“这个 skill 适合后端数据库迁移”；后续分派仍结合当前任务、上下文和验收风险判断。

## 调用示例

```bash
nanoworker write \
  --workspace /path/to/project \
  --message-file /tmp/task.md

nanoworker write \
  --workspace /path/to/project \
  --message-file /tmp/task.md \
  --skill frontend-ui \
  --model claude-sonnet \
  --tool-policy product-write \
  --assignment-id frontend-a \
  --role-file /tmp/frontend-role.md

nanoworker debug \
  --workspace /path/to/project \
  --message-file /tmp/fix-bug.md

nanoworker review \
  --workspace /path/to/project \
  --message-file /tmp/review.md

nanoworker fix \
  --workspace /path/to/project \
  --message-file /tmp/accepted-findings.md
```

Leader 所在 runtime 负责并行或后台执行。不同平台可以用后台进程、任务队列、协程、内置 task API 等方式实现。

## 诊断命令

```bash
nanoworker init
nanoworker init --provider anthropic-native
nanoworker migrate-config --json
nanoworker suggest "修复认证接口报错" --workspace /path/to/project --candidates --json
nanoworker role create "Frontend Implementer" --task-file /tmp/task.md --output /tmp/frontend-role.md
nanoworker role skill "Security Reviewer" --description "Reusable security review role" --base-role reviewer --tag security --preferred-model claude-sonnet
nanoworker role import /path/to/reviewer/SKILL.md --id reviewer --base-role reviewer --tag review
nanoworker role import-dir /path/to/roles
nanoworker role register reviewer --path ~/.nanoworker/roles/reviewer/SKILL.md
nanoworker role remove reviewer
nanoworker role doctor
nanoworker role list
nanoworker role show reviewer
nanoworker role copy reviewer style-reviewer
nanoworker role edit style-reviewer
nanoworker list --json
nanoworker journal --limit 10
nanoworker feedback frontend-ui-card --target-type role-card --assignment-id frontend-a --tag frontend --comment "Good fit for frontend component polish."
nanoworker feedback list --target frontend-ui-card
nanoworker stats --target frontend-ui-card --target-type role-card --last-days 30
nanoworker doctor
nanoworker smoke write --workspace /tmp
nanoworker smoke write --workspace /tmp --tool
```

`init` 生成 env-first 样例配置，`migrate-config` 把旧的 `coder-1/2/3` 配置迁到模板形态，`suggest --candidates` 给 Leader 返回候选角色卡数据并附加相关历史评语，`role create` 生成临时 Role Card，`role skill` 沉淀持久 skill，`role import/import-dir/register/remove/doctor` 显式管理托管角色库，`role list/show/path/edit/copy` 让 Leader 定位和调整长期角色提示词，`list` 查看执行模板和模型画像，`journal` 查看 assignment 记录，`feedback` 记录或查询 Leader 对 Role Card/skill/model/assignment 的评语，`stats` 聚合 assignment 和 feedback 数据，`doctor` 检查 config/env/skill/PATH，`smoke` 做真实 LLM 连通性测试。

## Assignment Journal

默认不写 journal。需要留审计线索时可以在 config 中打开，或单次运行打开：

```bash
nanoworker write --workspace /path/to/project --message-file /tmp/task.md --journal
nanoworker write --workspace /path/to/project --message-file /tmp/task.md --journal-path /tmp/nanoworker.jsonl
NANOWORKER_JOURNAL=1 nanoworker write --workspace /path/to/project --message-file /tmp/task.md
nanoworker journal --worker write --limit 5
```

journal 是 JSONL，记录 assignment snapshot、status、iterations、files_changed、tests_run、concerns、questions，以及可选的 `role_fit`、`risk_level`、`next_recommended_roles`、`handoff`、`evidence`；不记录 provider key。

Leader 验收后可以把角色卡、skill、model 的效果写成反馈事件：

```bash
nanoworker feedback frontend-ui-card \
  --target-type role-card \
  --assignment-id frontend-a \
  --tag frontend \
  --tag ui \
  --role-fit good \
  --model-fit partial \
  --accepted \
  --reuse-when "component polish" \
  --avoid-when "backend contract design" \
  --comment "Good fit for frontend component polish and responsive layout tasks."
```

这类反馈是 Leader 写给未来自己的候选上下文，不会让 nanoworker 自动改 prompt 或自动分派。

查询反馈和统计：

```bash
nanoworker feedback list --target frontend-ui-card
nanoworker feedback list --filter-tag frontend --limit 5
nanoworker stats --target frontend-ui-card --target-type role-card
nanoworker stats --skill frontend-ui --since 2026-01-01T00:00:00+00:00 --json
nanoworker stats --skill frontend-ui --last-days 30 --json
```

`stats` 只做本地历史聚合，例如 status、risk、role_fit、常见 tag、accepted/rejected 计数和近期评语；可以用 `--since`、`--until` 或 `--last-days` 缩小时间窗口。Leader 自己决定是否采纳。

## Fallback

model profile 可以配置 `fallbacks`。运行时默认启用 fallback，只在 LLM 调用失败且没有记录到 write/edit/bash 副作用时尝试下一个模型。已经写过文件或跑过 bash 后不会自动重试，避免重复修改 workspace。

```bash
nanoworker write --workspace /path/to/project --message-file /tmp/task.md --no-fallback
```

## Worker Result

Leader 读取 stdout JSON：

```json
{
  "success": true,
  "status": "done",
  "summary": "...",
  "files_changed": [],
  "tests_run": [],
  "concerns": [],
  "questions": [],
  "role_fit": "good",
  "risk_level": "medium",
  "next_recommended_roles": ["reviewer", "tester"],
  "handoff": "Ready for review and verification.",
  "evidence": ["npm test passed"],
  "assignment": {
    "worker": "write",
    "base_role": "coder",
    "tool_policy": "product-write",
    "model": "anthropic/claude-sonnet-4-6",
    "assignment_id": "frontend-a",
    "model_profile": "claude-sonnet",
    "skills": ["coder", "frontend-ui"],
    "role_file": "/tmp/frontend-role.md"
  },
  "iterations": 4
}
```

`status` 路由：

| Status | Leader 行为 |
|--------|-------------|
| `done` | 审查变更和验收结果，继续或完成 |
| `done_with_concerns` | 检查 concerns，决定接受、补验或再分派 |
| `needs_context` | 补充上下文后重新分派 |
| `blocked` | 解决外部阻塞或询问用户 |
| `failed` | 检查失败原因，重试、派 Debug 或本地处理 |

## Worktree

worktree 是可选能力，不是默认前置。

使用场景：
- 多个 worker 并行修改相对独立的功能块。
- 需要隔离分支并逐个 merge。

注意：
- worker 必须能看到所需上下文。
- 不要依赖被 `.gitignore` 忽略的 OpenSpec/AICONTEXT 文件。
- 关键上下文优先写进 Task Packet 或显式复制/提交到 worktree。

## 旧 opsx 流程

`skills/opsx/` 是旧 OpenSpec 工作流兼容层。只有当任务明确要求 OpenSpec change 流程时再使用它。
