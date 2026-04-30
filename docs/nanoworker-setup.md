# nanoworker 安装和配置

nanoworker 是用于运行 worker assignment 的轻量级 Python CLI。Leader 与用户交流、理解目标、写 Task Packet，并为每次 assignment 指定 worker、base role、Role Card、skill、model 和工具边界；nanoworker 按这份分派输入运行 Worker agent（Coder、Debug、Fixer、Reviewer、Tester）并返回结构化结果。

## 安装

```bash
# 方式一：pipx（推荐）
pipx install /path/to/nanoworker/

# 方式二：pip + venv
cd /path/to/nanoworker/
python3 -m venv .venv
source .venv/bin/activate
pip install -e .
```

## 配置

密钥优先放在环境变量或 GitHub Actions secrets，不写进 config：

```bash
# OpenAI-compatible endpoint
export LLM_API_KEY="..."
export LLM_API_BASE="https://xianyutoken.com/v1"

# Anthropic native endpoint：同一组 key 可用，但 base 通常不是 /v1
export LLM_API_KEY="..."
export LLM_ANTHROPIC_API_BASE="https://xianyutoken.com"
```

本机也可以把同样的 export 写进 `~/.nanoworker/env`。nanoworker 启动时会读取这个文件，但不会覆盖当前进程已经存在的环境变量；GitHub Actions secrets 或 shell 里显式 export 的值优先。

推荐先生成样例配置：

```bash
nanoworker init --provider openai-compatible

# 或使用 Anthropic native 格式
nanoworker init --provider anthropic-native

# 如果同一套配置同时保留两种格式，需要不同 base URL：
nanoworker init --provider both
export LLM_OPENAI_API_BASE="https://xianyutoken.com/v1"
export LLM_ANTHROPIC_API_BASE="https://xianyutoken.com"
```

创建 `~/.nanoworker/config.json`：

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
      "fallbacks": ["claude-sonnet"]
    },
    "claude-sonnet": {
      "model": "anthropic/claude-sonnet-4-6",
      "strengths": ["frontend", "ui", "review", "code"],
      "preferred_roles": ["coder", "debug", "fixer", "reviewer"],
      "fallbacks": ["gpt-5.4"]
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

Worker id 更像执行模板。同一个 `write` 模板可以被 Leader 并发调用多次；需要区分并发 assignment 时传 `--assignment-id`。`role` 决定基础身份和底座 skill，`tool_policy` 决定工具权限，临时职责用 `--role-file` 注入。`model` 可以是 `models` 里的 profile 名，也可以直接写 litellm 模型 id。

## 使用

```bash
# 基本调用
nanoworker <worker-name> "<task-message>" --workspace <project-path>

# Task Packet 文件调用（推荐）
nanoworker <worker-name> --workspace <project-path> --message-file /tmp/task.md

# 临时追加 Role Card / role skill
nanoworker <worker-name> --workspace <project-path> --message-file /tmp/task.md --role-file /tmp/frontend-role.md

# 本次 assignment 追加持久 skill、覆盖模型画像，并标记 assignment id
nanoworker <worker-name> --workspace <project-path> --message-file /tmp/task.md --skill frontend-ui --model claude-sonnet --assignment-id frontend-a

# 单次覆盖工具策略，不写回 worker 配置
nanoworker write --workspace <project-path> --message-file /tmp/task.md --tool-policy no-shell

# 关闭模型 fallback（默认开启，仅在无副作用 LLM 失败时重试）
nanoworker write --workspace <project-path> --message-file /tmp/task.md --no-fallback

# 显式 run 子命令也可用，和直接写 worker-name 等价
nanoworker run write --workspace <project-path> --message-file /tmp/task.md

# 示例
nanoworker write --workspace /path/to/project "实现用户认证功能"
nanoworker debug --workspace /path/to/project "审查 src/auth.py 的代码"
nanoworker review --workspace /path/to/project "只读审查这次改动"
nanoworker fix --workspace /path/to/project "修复 reviewer 接受的 findings"
nanoworker verify --workspace /path/to/project "运行验证测试"

# 覆盖模型
nanoworker write --workspace /path/to/project --model openai/gpt-4o "quick task"
nanoworker write --workspace /path/to/project --model claude-sonnet "quick Claude native task"

# 开启 debug 日志
nanoworker write --workspace /path/to/project -v "task"
```

## 诊断命令

```bash
# 创建 env-first 配置
nanoworker init
nanoworker init --provider anthropic-native
nanoworker init --provider both --output /tmp/config.json

# 迁移旧配置：默认只输出到 stdout，不覆盖原文件
nanoworker migrate-config
nanoworker migrate-config --output /tmp/config.json
nanoworker migrate-config --force

# 根据任务描述给 Leader 候选 worker/model/tool_policy 数据
nanoworker suggest "实现响应式设置页 UI" --workspace /path/to/project --candidates
nanoworker suggest --message-file /tmp/task.md --json

# 生成临时 Role Card 或持久 skill
nanoworker role create "Frontend Implementer" --task-file /tmp/task.md --output /tmp/frontend-role.md
nanoworker role skill "Security Reviewer" --description "Reusable security review role" --base-role reviewer --tag security --preferred-model claude-sonnet
nanoworker role import /path/to/reviewer/SKILL.md --id reviewer --base-role reviewer --tag review
nanoworker role import-dir /path/to/roles
nanoworker role register reviewer --path ~/.nanoworker/roles/reviewer/SKILL.md
nanoworker role remove reviewer
nanoworker role doctor
nanoworker role list
nanoworker role show reviewer
nanoworker role path reviewer
nanoworker role copy reviewer style-reviewer
nanoworker role edit style-reviewer

# 列出 worker templates 和 model profiles
nanoworker list
nanoworker list --json

# 查看 assignment journal
nanoworker journal
nanoworker journal --worker write --limit 5
nanoworker journal --json
nanoworker feedback frontend-ui-card --target-type role-card --assignment-id frontend-a --tag frontend --comment "Good fit for frontend component polish."
nanoworker feedback list --target frontend-ui-card
nanoworker stats --target frontend-ui-card --target-type role-card

# 检查 config、PATH、env、skill 是否可用
nanoworker doctor
nanoworker doctor --json

# 最小 LLM 连通性测试
nanoworker smoke write --workspace /tmp

# 带 write/read 工具调用的测试
nanoworker smoke write --workspace /tmp --tool
```

## 输出格式

nanoworker 输出 JSON 到 stdout，日志到 stderr：

```json
{
  "success": true,
  "status": "done",
  "summary": "实现了用户认证功能，修改了 3 个文件",
  "files_changed": ["src/auth.py", "src/middleware.py", "tests/test_auth.py"],
  "tests_run": ["pytest tests/test_auth.py"],
  "concerns": [],
  "questions": [],
  "role_fit": "good",
  "risk_level": "medium",
  "next_recommended_roles": ["reviewer", "tester"],
  "handoff": "Ready for review and verification.",
  "evidence": ["pytest tests/test_auth.py passed"],
  "assignment": {
    "worker": "write",
    "base_role": "coder",
    "tool_policy": "product-write",
    "model": "openai/gpt-5.3-codex",
    "assignment_id": "auth-a",
    "model_profile": "gpt-backend",
    "skills": ["coder"],
    "role_file": null
  },
  "iterations": 8
}
```

Leader 通过 `jq -r '.summary'` 提取回复。

`status` 取值：

| status | 含义 |
|--------|------|
| `done` | 已完成，相关验证通过 |
| `done_with_concerns` | 已完成，但有非阻塞风险或验证缺口 |
| `needs_context` | 缺少关键上下文，Leader 需要补充 |
| `blocked` | 被外部条件阻塞 |
| `failed` | 已尝试但结果不可用 |

## Tool Policy

| tool_policy | 工具 | 用途 |
|-------------|------|------|
| product-write | read, write, edit, ls, grep, find, bash | 功能实现或修复 |
| read-only-review | read, ls, grep, find, bash | 独立审查、找 bug |
| test-write-only | read, write, edit, ls, grep, find, bash | 验证任务；write/edit 只允许 test/spec 路径 |
| no-shell | read, write, edit, ls, grep, find | 不给 shell 的实现任务 |
| read-only-no-shell | read, ls, grep, find | 不给 shell 的只读审查 |

如果 worker 没有写 `tool_policy`，会按 `role` 给默认策略：`coder/debug/fixer -> product-write`，`reviewer/debug-duel -> read-only-review`，`tester -> test-write-only`。所有文件工具都把路径限制在 `--workspace` 内。`bash` 固定 cwd 到 workspace，但不是 OS 级沙箱；高风险任务应选择无 shell policy。

## Role Store

nanoworker 运行时不从项目里的任意目录猜角色文件。它使用自己的托管角色库：

```text
~/.nanoworker/roles/
├── index.json
├── coder/SKILL.md
├── debug/SKILL.md
├── fixer/SKILL.md
├── reviewer/SKILL.md
└── tester/SKILL.md
```

仓库里的 `skills/` 是出厂模板。运行时不会扫描项目目录或自动安装这些模板；需要显式 `role import`、`role import-dir` 或 `role register`，才能把角色写入 `~/.nanoworker/roles/index.json`。index 会记录 `tags`、`base_role`、`preferred_models` 等候选元数据。之后 worker config 里的 `skills` 只写角色 id：

```
nanoworker review --workspace /repo --message-file /tmp/review.md
```

解析过程是：

1. `review` worker 默认带 `skills: ["reviewer"]`。
2. nanoworker 通过 `~/.nanoworker/roles/index.json` 找到 `reviewer` 的托管路径。
3. 读取该 `SKILL.md` 并注入 system prompt。
4. 再把 Task Packet 作为 user message 发给模型。

可以显式导入或注册角色：

```bash
nanoworker role import /path/to/reviewer/SKILL.md --id reviewer --base-role reviewer --tag review
nanoworker role import-dir /path/to/roles
nanoworker role register reviewer --path ~/.nanoworker/roles/reviewer/SKILL.md
nanoworker role doctor
nanoworker role list --json
```

`role install-defaults` 仍保留为隐藏的开发/bootstrap 兼容入口，但不在常规 help 和正常用户路径中暴露。

Leader 可以在验收后为 Role Card、skill、model 记录评语，例如“适合前端组件打磨”“适合后端数据库迁移”“适合后端 API 合同修复”。这些评语会在 `suggest --candidates` 中按需附加并汇总为 `feedback_summary`，供后续分派时结合当前任务一起判断。

Leader 调整长期提示词时也走这个托管库：

```bash
nanoworker role show reviewer
nanoworker role path reviewer
nanoworker role copy reviewer style-reviewer
nanoworker role edit style-reviewer
```

`role list` 会标记 registry hash 与当前文件不一致的角色为 `modified`。常规项目上下文仍然放在 Task Packet 或 Role Card，不放进托管基础角色里。

## Task Packet 模板

```markdown
# Task Packet

Goal:
- <要完成什么>

Scope:
- Owned files: <允许修改的文件/目录>
- Out of scope: <不要做什么>

Context:
- <必要背景、相关文件、日志、错误信息>

Acceptance:
- <验收标准或必须通过的命令>

Role Notes:
- <本次临时角色约束，可留空>
```

## Role Card 模板

Role Card 是单次任务的临时角色 skill，通过 `--role-file` 注入。优先使用临时 Role Card，只有重复使用的角色才沉淀成持久 `SKILL.md`。

CLI 可以先生成一个可编辑起点：

```bash
nanoworker role create "Frontend Implementer" \
  --task-file /tmp/task.md \
  --preferred-model claude-sonnet \
  --output /tmp/frontend-role.md
```

```markdown
# Role Card: <角色名>

Use With:
- Base role: <coder|debug|fixer|tester|reviewer|debug-duel>
- Preferred model: <可选模型或模型偏好>

Mission:
- <本次角色负责什么>

Scope:
- Owns: <负责的文件、模块或检查范围>
- Avoids: <不做什么>

Method:
- <领域工作法或质量标准>

Acceptance Focus:
- <完成前必须验证什么>

Report:
- Use the base worker status format.
```

## 验证

```bash
# 确认安装
which nanoworker
nanoworker --help

# 快速测试
nanoworker write --workspace /tmp "回答：你是什么角色？"
```
