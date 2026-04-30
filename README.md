# Multi-Agent Workflow

> **TL;DR：** 这不是又一个"多 agent 互相通信"的框架。
> Leader 就是你当前对话的那个主模型（Claude Code / Codex / 自建 TUI），
> nanoworker 是它手里的一把 CLI——每次任务起一个独立进程、跑完吐一行 JSON 就退出。
> 所有"协作"都发生在 Leader 一个人脑子里。

## 核心定位

| 概念 | 实际是什么 |
|------|------------|
| **Leader** | 当前主 session 的模型本身。通过加载 `skills/leader/SKILL.md` 进入"Leader 模式"，负责理解用户、拆任务、写 Task Packet、分派、验收、反馈。 |
| **Worker** | `nanoworker <id>` 拉起的一次性 Python 进程。无状态、不知道彼此存在、不会自己派下一步。 |
| **Worker template** | `write`、`debug`、`fix`、`review`、`verify` 是模板名，不是固定 agent。同一个模板可并发起多个，用 `--assignment-id` 区分。 |
| **协作** | 全部在 Leader 脑子里完成，worker 之间不通信。 |

和 LangChain / CrewAI 那类"多 agent 平等通信"框架的根本差异：本项目刻意不在 worker 之间加路由层，赌的是主模型能力已经够强，流程不需要烧死在配置里。

## 演化简史

- **opsx 时期**：OpenSpec 风格的重产出物（proposal / design / spec / tasks）。已留在 `skills/opsx/` 作兼容层，不是默认路径。
- **BLUEPRINT 时期**：少角色、强流程、强门禁（agent-change-review → agent-apply → agent-verify 三段闸）。已废止，仅作历史参考。
- **当前**：Leader 主模型自己控流。轻流程、重提示分层、严工具边界。

## 工作流概览

1. 用户和 Leader 沟通目标。
2. Leader 触发自己的 runtime skill，理解任务类型和质量要求。
3. Leader 阅读必要上下文，决定本地完成 / 单 worker / 拆多 assignment。
4. Leader 选择 base role、模型、tool policy、可复用 worker skill。
5. 需要专业身份时创建临时 Role Card。
6. Leader 写 Task Packet（目标、范围、上下文、验收）。
7. `nanoworker <id>` 分派 worker。
8. worker 在 workspace 里跑 LLM + tool loop，吐一行 JSON 退出。
9. Leader 按 `status` 路由：接受、补上下文、派 reviewer / fixer / tester、或自己修。
10. 有证据时记录反馈。

```text
用户
  <-> Leader（主 session 模型 + leader skill）
        ├─ 理解 / 拆分 / 选 base role / 选 model / 选 tool policy
        ├─ 写 Task Packet
        ├─ nanoworker <id> 分派（可并发）
        ├─ 读 stdout JSON，按 status 路由
        └─ 验收后记录反馈
              |
              v 每次分派起一个独立进程
          worker 进程
              ├─ 加载 base role skill
              ├─ 加载 --skill / --role-file
              ├─ 在 --workspace 内执行
              └─ stdout: 一行 JSON
```

## Worker 一次跑做了什么

`nanoworker write ...` 这一行命令背后的生命周期：

1. **启动**。起一个 Python 进程，读 `~/.nanoworker/env` 和 `~/.nanoworker/config.json`，按命令行参数（`--model` / `--skill` / `--role-file` / `--tool-policy` / `--assignment-id`）做这次 assignment 的覆盖。worker 模板本身不被改写。
2. **建提示**。`build_system_prompt` 按顺序拼出 system message：worker 头（角色名、时间、workspace 路径）→ base role skill → 每个 `--skill` 内容 → `--role-file` 内容。Task Packet（`--message-file` 内容）作为 user message。
3. **建工具**。按 tool policy 实例化 `ToolRegistry`，所有文件类工具锁在 `--workspace` 目录里。
4. **进 tool-call 循环**（最多 `max_iterations` 轮，默认 30）。每轮调一次 `litellm.acompletion`：模型返回 tool_calls 就在本地跑工具、把结果写回 messages 进入下一轮；模型不再调工具就跳出循环。
5. **拼结果**。从最后那段文本里解析 `Status:`、`Files Changed`、`Tests Run`、`role_fit` 等字段，构造 `WorkerResult`。
6. **吐 JSON**。一行 JSON 写到 stdout，进程退出。日志全部走 stderr。

几条不变量：

- worker 不知道别的 worker 存在，也不会自己派下一步。所有路由都回到 Leader 手上。
- 工具调用直接落盘（在 workspace 内）。stdout 上不会出现工具结果。
- 当模型调用本身挂了（网络/限流），且这次 assignment 还没改过任何文件，才允许 fallback 模型重试。一旦写过盘 fallback 就不会再触发，避免半成品被覆盖。
- 跑满 `max_iterations` 直接判 `failed`，不会无限转。

## 提示分层（项目最关键的设计）

5 层提示，职责严格不重叠：

| 层 | 谁用 | 装什么 | 不装什么 |
|----|------|--------|----------|
| **Leader Runtime Skill** | Leader | Leader 自己的思考 / 规划 / 调试 / 审查 / 验证方法 | Worker 的具体任务事实 |
| **Base Role Skill** | Worker | 通用角色边界、工具习惯、报告格式、稳定行为 | 单次任务目标 |
| **Worker Persistent Skill** | Worker | 可复用专业方法（frontend-ui、security-review、migration-check） | 临时任务 scope |
| **Role Card** | Worker | 本次 assignment 的临时身份、方法焦点、模型提示 | 重复 base role 通用内容 |
| **Task Packet** | Worker | 本次具体目标、范围、上下文、验收、协作边界 | 长期角色政策 |

Superpowers 这类"自动触发 skill"机制属于 Leader runtime 层。Leader 用 runtime 原生机制或主动判断加载 skill；分派给 worker 的材料只通过 Task Packet、`--skill`、`--role-file` 传入，每次 assignment 输入可追踪。

## 角色与 worker 模板

| Base Role | 典型 worker | 适用场景 | 边界 |
|-----------|-------------|----------|------|
| `coder` | `write` | 实现功能、改代码、补测试 | 不做跨模块最终架构裁决 |
| `debug` | `debug` | 根因不明、需要诊断和修复 | 不做泛化审查或大段新功能 |
| `fixer` | `fix` | 已接受 findings、已知失败、定点修复 | 不重新设计、不扩大 scope |
| `reviewer` | `review` | 只读审查、找 bug、输出 findings | 不直接改代码、不做最终验收 |
| `tester` | `verify` | 运行验证、测试、构建、复现 | 不修产品代码 |
| `debug-duel` *(legacy)* | — | 旧 opsx 对抗赛 Debug 变体 | 仅在显式启用 duel 流程时使用 |

**worker 模板不可变。** Per-assignment 覆盖（`--model` / `--skill` / `--role-file` / `--tool-policy` / `--assignment-id`）只活在这次调用里，不会写回模板。

## Task Packet

每次 assignment 写一份。

```markdown
# Task Packet

Goal:
- <用户要达成的结果>

Scope:
- Owned files: <允许修改的文件/目录>
- Out of scope: <不要做什么>

Context:
- <必要背景、链接、错误日志、相关文件路径>

Acceptance:
- <验收标准或必须通过的命令>

Coordination:
- <并行边界、合并注意事项、依赖顺序>

Role Notes:
- <本次角色、模型、skill、Role Card 提示>
```

规则：
- 关键上下文直接放包里，不要假设 worker 会去翻 ignored 文件。
- 必须读的文件，明确写出路径。
- 引用 OpenSpec / AI-CONTEXT 时显式放在 `Context` 字段。

## Worker 输出契约

每个 worker stdout 输出**恰好一行 JSON**，所有日志走 stderr。Leader 必须靠这行 JSON 决定下一步。

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
  "evidence": ["pytest tests/test_backend.py passed"],
  "assignment": {
    "worker": "write",
    "base_role": "coder",
    "model": "...",
    "assignment_id": "backend-a"
  },
  "iterations": 4
}
```

### Status 路由

`status` 词表封闭，Leader 按它决定下一步：

| status | Leader 动作 |
|--------|-------------|
| `done` | 检查改动和验收，继续或收尾 |
| `done_with_concerns` | 看 concerns，决定接受、补验证、还是派 follow-up |
| `needs_context` | 回答 questions，补 Task Packet 后重派 |
| `blocked` | 解决外部阻塞或问用户 |
| `failed` | 看 summary 和部分改动，决定 retry / debug / 自己修 |

`success` 由 status 派生（`done` / `done_with_concerns` 即成功），不是独立字段。`role_fit`、`risk_level`、`next_recommended_roles` 是 worker 自评，**永远不是最终判定**——和你的检查冲突时以你的检查为准。

## Tool policies

Tool policy 控制 worker 能用哪些工具。5 个 primary policy：

| Policy | 工具 | 适用 |
|--------|------|------|
| `product-write` | read / write / edit / ls / grep / find / bash | 默认实现型 worker |
| `read-only-review` | read / ls / grep / find | 只读审查 |
| `test-write-only` | read / 受限 write·edit（仅 test/spec 路径）/ ls / grep / find / bash | tester |
| `no-shell` | read / write / edit / ls / grep / find（无 bash） | 高风险任务禁 shell |
| `read-only-no-shell` | read / ls / grep / find（无 bash 无 write） | 最严格只读 |

文件类工具都被锁在 `--workspace` 里。**`bash` 工具固定 cwd 但不做 OS 级 sandbox**——真正高风险的任务用 `*-no-shell` 系列。

老的"按角色命名"的 policy 名（`coder` / `reviewer` / ...）作为兼容别名保留。

## 分派与并发

```bash
# 最小调用
nanoworker write --workspace /repo --message-file /tmp/task.md

# 带 Role Card / persistent skill / 模型覆盖
nanoworker write \
  --workspace /repo \
  --message-file /tmp/task.md \
  --skill frontend-ui \
  --role-file /tmp/frontend-role.md \
  --model claude-sonnet \
  --assignment-id frontend-a

# 只读审查
nanoworker review --workspace /repo --message-file /tmp/review.md --tool-policy read-only-review

# 定点修复
nanoworker fix --workspace /repo --message-file /tmp/accepted-findings.md

# 验证
nanoworker verify --workspace /repo --message-file /tmp/verify.md
```

**并发：** 同一个模板可并发起多个 worker，每次独立进程，用 `--assignment-id` 区分。Leader 怎么并发是 runtime-specific——Claude Code 后台任务、shell `&`、自建 runtime 的进程池都行。**只有当文件所有权、验收标准、合并边界都能拆清楚时才拆并发**，否则交给一个 worker 串行。

诊断：

```bash
nanoworker list --json
nanoworker doctor
nanoworker smoke write --workspace /tmp --tool
nanoworker journal --limit 10
```

## 给 worker 的三种材料：怎么选

提示分层那张表里跨了 5 层，但 worker 这一侧实际能加的就 3 种：base role skill、persistent skill、role card。三者经常被混。下面这张表更直白：

| | Base Role Skill | Worker Persistent Skill | Role Card |
|---|---|---|---|
| 是什么 | 角色底盘（"我是 coder"） | 可复用领域方法（"前端组件该怎么打磨"） | 一次性身份卡（"这次你是 X 项目的前端实现者"） |
| 寿命 | 长期，几乎不改 | 长期，偶尔补充 | 一次性，跑完就丢 |
| Leader 怎么传 | worker 模板自带（`config.workers.<id>.skills`） | `--skill <name>` | `--role-file <path>` |
| 注册位置 | `~/.nanoworker/roles/` | `~/.nanoworker/roles/` | 临时 markdown 文件 |
| 典型内容 | "报告格式""不直接改代码" | "frontend-ui：响应式 + 设计系统 token 检查" | "用 Tailwind v4，避开 motion 库" |
| 是否绑定具体任务 | 不绑定 | 不绑定 | 完全绑定 |

判断 tip：

- **连续三次写出大同小异的 Role Card** → 该把共性抽成 persistent skill。
- **想改 base role 的报告格式** → 先 `nanoworker role copy <id> <new-id>` 再改，别直接污染原 base role。
- **persistent skill 越写越具体、开始包含任务事实** → 越界了。skill 只该说"怎么做"，"这次做什么"放回 Task Packet。

## Role Cards 和持久 Skills

一次性专业身份用 Role Card：

```bash
nanoworker role create "Frontend Implementer" \
  --task-file /tmp/task.md \
  --output /tmp/frontend-role.md \
  --preferred-model claude-sonnet
```

可复用专业方法沉淀为持久 skill：

```bash
nanoworker role skill "Security Reviewer" \
  --description "Reusable security review role" \
  --base-role reviewer \
  --tag security \
  --preferred-model claude-sonnet
```

管理已注册角色：

```bash
nanoworker role import /path/to/SKILL.md --id reviewer --base-role reviewer --tag review
nanoworker role import-dir /path/to/roles
nanoworker role list --json
nanoworker role show reviewer
nanoworker role copy reviewer style-reviewer  # 改之前先 copy
nanoworker role edit style-reviewer
nanoworker role doctor
```

## skills/ 和 ~/.nanoworker/roles/ 的关系（重要）

仓库 `skills/` 是**模板源码**。运行时 worker 实际读的是 `~/.nanoworker/roles/`，由 `~/.nanoworker/roles/index.json` 索引。

**改 repo 里的 skill 不会自动生效**，需要重新导入：

```bash
nanoworker role import-dir skills    # 一次同步整个 skills/
```

`role list` 会把 hash 漂移过的条目标记为 `modified`。修改 base role 推荐先 `role copy <id> <new-id>` 再调，而不是直接覆盖原 base role。

## 候选数据和反馈

Leader 可查询本地历史辅助判断：

```bash
nanoworker suggest "实现响应式设置页 UI" --workspace /repo --candidates --json
nanoworker feedback list --target frontend-ui-card
nanoworker stats --target frontend-ui-card --target-type role-card --last-days 30
```

`suggest` 是局部启发式 + 候选数据提供器，不是调度器。最终选择结合当前任务、上下文、验收风险。

验收后记录反馈：

```bash
nanoworker feedback frontend-ui-card \
  --target-type role-card \
  --assignment-id frontend-a \
  --tag frontend --tag ui \
  --role-fit good --accepted \
  --comment "Good fit for frontend component polish."
```

worker 自评是证据，不是最终结论；不要让 worker 自动改长期 prompt 或角色 metadata。

## 配置

### 安装

```bash
pip install -e .
nanoworker init --provider openai-compatible
nanoworker doctor
```

`nanoworker init` 在 `~/.nanoworker/config.json` 写入默认 providers、models、workers 模板。`doctor` 告诉你哪些 env 变量还没设、哪些 worker 模板能跑、哪些 skill 注册过。

### 凭据：`~/.nanoworker/env`

凭据全部走环境变量，**不要**写到 `config.json` 的字面值里。仓库根有一份 `nanoworker.env.example`：

```bash
cp nanoworker.env.example ~/.nanoworker/env
# 编辑 ~/.nanoworker/env，填入真实 key 和 base URL
```

加载顺序（高优先级覆盖低优先级）：

1. **进程已有 env** —— shell `export` 或 CI secrets。最高优先级。
2. **`~/.nanoworker/env`** —— 启动时由 `load_local_env_file` 读取，**不会覆盖**进程已有 env。
3. **`config.json` 里的 literal `api_key`** —— 已 deprecated，`doctor` 会标红。`nanoworker migrate-config` 把老配置升级成 env-name 形式。

worker 启动时 `setup_provider_env` 会按这次要调的 model 前缀（`openai/...` 或 `anthropic/...`），把 `LLM_API_KEY` / `LLM_API_BASE` 镜像成 litellm 实际识别的变量名（`OPENAI_API_KEY`、`OPENAI_API_BASE`、`ANTHROPIC_API_BASE` 等），不需要你手动镜像。

跑一遍最小烟测确认连通：

```bash
nanoworker smoke write --workspace /tmp --tool
```

### `config.json` 形态

```json
{
  "models": {
    "gpt-5.4": {
      "model": "openai/gpt-5.4",
      "strengths": ["backend", "reasoning", "tests"],
      "preferred_roles": ["coder", "debug", "fixer", "tester"]
    },
    "claude-sonnet": {
      "model": "anthropic/claude-sonnet-4-6",
      "strengths": ["frontend", "ui", "review"],
      "preferred_roles": ["coder", "reviewer"]
    }
  },
  "workers": {
    "write":  { "role": "coder",    "tool_policy": "product-write",    "model": "gpt-5.4",       "skills": ["coder"] },
    "debug":  { "role": "debug",    "tool_policy": "product-write",    "model": "gpt-5.4",       "skills": ["debug"] },
    "fix":    { "role": "fixer",    "tool_policy": "product-write",    "model": "gpt-5.4",       "skills": ["fixer"] },
    "review": { "role": "reviewer", "tool_policy": "read-only-review", "model": "claude-sonnet", "skills": ["reviewer"] },
    "verify": { "role": "tester",   "tool_policy": "test-write-only",  "model": "gpt-5.4",       "skills": ["tester"] }
  },
  "journal": { "enabled": true, "path": "~/.nanoworker/journal.jsonl" }
}
```

模型 id 仅作配置形态示例，按你能访问的模型替换。providers 配置（指定每个 provider 用哪个 env 名）`init` 已经写好了，一般不用动。

更多细节：

- [docs/usage-guide.md](docs/usage-guide.md)
- [docs/nanoworker-setup.md](docs/nanoworker-setup.md)
- [docs/nanoworker-plan.md](docs/nanoworker-plan.md)

## 旧流程兼容

`skills/opsx/` 是旧 OpenSpec 工作流的兼容层。当前默认路径更轻：

```text
用户目标 -> Leader 理解 -> Leader skill -> Task Packet -> 分派 -> 按 status 路由 -> 验收
```

明确需要 proposal / design / spec / tasks 时再进 `skills/opsx/`。

## 目录结构

```text
.
├── README.md             # 当前路线（本文件）
├── CLAUDE.md             # Claude Code 在本仓库工作时的项目指南
├── BLUEPRINT.md          # 旧 opsx 路线遗留，已废止
├── pyproject.toml        # nanoworker 包定义（Python 3.11+）
├── skills/
│   ├── leader/           # Leader 编排 skill
│   ├── role-creator/     # Role Card / 持久 skill 创建方法
│   ├── coder/            # Worker base role
│   ├── debug/            # Worker base role
│   ├── fixer/            # Worker base role
│   ├── reviewer/         # Worker base role
│   ├── tester/           # Worker base role
│   ├── debug-duel/       # 旧 opsx 对抗赛 Debug 变体（legacy）
│   └── opsx/             # 旧 OpenSpec 工作流兼容层
├── nanoworker/           # worker runner CLI
├── docs/                 # 操作手册与示例
├── rules/
│   └── multi-agent.md    # 可被 Leader runtime 当作常驻规则的简短片段
└── tests/                # nanoworker CLI 烟测（开发期临时产物）
```

## License

MIT
