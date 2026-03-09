# Multi-Agent Workflow

> 4 角色异步协作的 AI 多 agent 工作流。

## 角色分工

| 角色 | 模型 | 平台 | 实例数 | 职责 | 不做什么 |
|------|------|------|--------|------|---------|
| **Leader** | Claude Opus 4.6 | Claude Code | 1 | 架构、编排、验收、可动手修正、通信中心 | 从零写大段基础功能 |
| **Coder** | GPT-5.4 | nanoworker | 1-N | 读需求，自主实现代码+测试，交付 | 架构决策、跨模块判断 |
| **Debug** | GPT-5.4 | nanoworker | 1-N | 审查代码、定位修复 bug、参与讨论 | 从零写功能、运行测试 |
| **Debug-Duel** | GPT-5.4 | nanoworker | 2-N | 对抗赛：独立找 bug + 环形互审 | 修复 bug、架构决策、运行测试 |
| **Tester** | GPT-5.4 | nanoworker | 1 | 最终运行验证 | 写功能代码、直接修 bug |

同一角色可注册多个实例（coder-1/2/3, debug-1/2/3, duel-1/2/3），Leader 从 Agent Registry 动态读取。

- **Leader 做甩手掌柜**：只给项目路径和任务名称，不给实现方案
- **Leader 是通信中心**：所有 agent 间通信经 Leader 中转，Coder 和 Debug 不直接对话
- **Leader 可以改代码**：验收和讨论中可以动手修正，但不从零写大段功能
- **Debug 必须修复，不只是报告**：发现问题直接修，修完告诉 Leader 改了什么、为什么改
- **Tester 不直接联系 Debug**：发现 bug 报回 Leader 路由

---

## 架构概览

```
Claude Code (Leader)
    │
    ├─ Bash: nanoworker coder-1 --workspace <path> "implement X"
    ├─ Bash: nanoworker coder-2 --workspace <path> "implement Y"
    │  (并行 run_in_background)
    ▼
Worker 进程（轻量，独立，无状态）
    1. 按名字查 ~/.nanoworker/config.json → role, model, skills
    2. 设置 LLM provider 环境变量
    3. 加载 role 工具集 (read_file, write_file, edit_file, list_dir, exec)
    4. 构建 system prompt = 身份头 + SKILL.md 全文
    5. LLM + 工具循环（直接在 workspace 改文件）
    6. stdout 输出 JSON: {"success": bool, "summary": "...", "files_changed": [...]}
    7. 退出
```

---

## 两阶段工作流

### 阶段一：agent-apply（Coder 实现 + Debug 审查）

Leader 根据可用 Coder 数量和 tasks 功能组数量动态选择单路或并行模式。

**单路模式**（并行度 = 1）：

```
前置检查：AI-CONTEXT.md → 分派 Coder → 中转 Debug → 完成
```

**并行模式**（并行度 > 1）：

```
前置检查：AI-CONTEXT.md
    │
    ▼
残留 worktree 检测 → 功能块拆分 → 公共文件标记为 Leader 后处理
    │
    ▼
创建 git worktree（每个功能组一个隔离目录+分支）
    │
    ▼
并行分派 N 个 Coder（各自在独立 worktree 中实现）
    │                          ← 全部完成后才进入下一步
    ▼
Debug 资源池分配（按需分配 worktree 给可用 Debug）
    │
    ├─ Debug 数 >= worktree 数 → 全部并行审查
    │
    └─ Debug 数 < worktree 数 → 先到先得，完成一个接下一个
    │                          ← 各 worktree 独立 Leader↔Debug 讨论
    ▼
Leader 逐个 merge 分支 → 解决冲突 → 补充公共文件 → 清理 worktree
    │
    ▼
汇报完成
```

**并行度计算**（禁止硬编码）：
- `coder_parallelism = min(coder_count, task_groups)`
- `debug_parallelism = min(debug_count, worktree_count)`
- 并行度 = 1 时自动降级为单路模式

### 阶段二：agent-verify（Leader 验收 + 路由）

```
Leader 亲自验收（读所有变更文件，逐项对照 specs）
    │
    ├─ 缺功能 → Coder 补充 + Debug 审查（同阶段一）→ 重新验收
    │
    ├─ 有 bug → Debug 修复 → Leader↔Debug 讨论 → 重新验收
    │
    └─ 通过 → Tester 运行验证（异步）
                │
                ├─ 通过 → 完成
                └─ 失败 → Debug 修复 → 重新验收
```

缺功能走 Coder+Debug，有 bug 走 Debug。不要搞混。

### 可选：agent-duel（Debug 对抗赛）

对抗赛是 agent-apply 中 Debug 审查的可选替代，利用竞赛框架让多个 Debug agent 互相对抗，通过交叉过滤提高审查准确度。

```
前置检查：Debug agent >= 2？AI-CONTEXT.md 存在？
    │
    ├─ N < 2 → 提示退化为原有 Debug 流程
    │
    ▼
Round 1：并行找 bug
    │  所有 Debug agent 同时分派
    │  每个收到：竞赛背景 + spec 路径 + 项目路径
    │  不给 Coder 修改清单（避免锚定）
    │
    ▼
Round 2：环形互审
    │  agent[i] 审 agent[(i-1) % N] 的清单
    │  新会话，只给对手结论不给推理
    │
    ▼
Leader 裁决
    │  多人找到+未被推翻 → 确认
    │  被推翻+理由充分 → 排除
    │  各执一词 → Leader 亲自读代码判
    │
    ▼
修复路由：确认的 bug 派给 Coder/Debug，复用现有流程
```

**评分规则**（prompt 激励，无真实计分后端）：
- 低影响 bug +1，中影响 +5，致命 +10
- 推翻对手成功得该 bug 的分数，推翻错了扣 2 倍

**何时使用**：重要变更、需要更高审查质量时选用。常规变更用原有 agent-apply 即可。

---

## 异步调用模型

所有外部 agent 调用以 `run_in_background=true` 异步执行，Leader 不阻塞等待。

**单路模式**：
```
Leader ──异步──→ Coder ──完成──→ Leader ──异步──→ Debug ──完成──→ Leader
```

**并行模式**：
```
Leader ──异步──→ Coder-1 ─┐
       ──异步──→ Coder-2 ─┤ 全部完成
       ──异步──→ Coder-3 ─┘
                           │
Leader ──异步──→ Debug-1(wt-1) ─┐
       ──异步──→ Debug-2(wt-2) ─┤ 全部完成（不够则轮转）
       等 Debug 空闲 → Debug-1(wt-3) ─┘
                           │
Leader: merge → 公共文件 → 清理 → 汇报
```

---

## Git Worktree 隔离

并行模式通过 git worktree 为每个 Coder 创建隔离工作环境：

| 项目 | 规则 |
|------|------|
| **路径** | `<project>/.worktrees/<change-name>-<N>` |
| **分支** | `parallel/<change-name>-<N>` |
| **创建** | Leader 在分派 Coder 前创建 |
| **合并** | 所有 Coder+Debug 完成后，Leader 逐个 `git merge` |
| **冲突** | Leader 读取冲突文件，理解两边意图，解决后 commit |
| **公共文件** | 路由注册、配置、index 导出等 → 不分给 Coder，Leader 合并后补 |
| **清理** | `git worktree remove` + `git branch -d` |
| **残留检测** | agent-apply 开始前检查 `.worktrees/` 是否有上次残留 |

Coder 无需知道 worktree 的存在 — Leader 在分派消息中将项目路径替换为 worktree 路径。

---

## Leader↔Debug 讨论机制

```
1 轮 = Debug→Leader + Leader→Debug

第 1 轮：Debug 修复 → Leader 不满意 → Leader 改代码发回 Debug
第 2 轮：Debug 审查 → Leader 不满意 → Leader 改代码发回 Debug
第 3 轮：Debug 审查 → Leader 还不满意 → 停止，上报用户
```

每轮记录在讨论文件中：
- **单路模式**：`<change>/discussion.md`
- **并行模式**：每个 worktree 独立 `<worktree>/<change>/discussion-wt-<N>.md`

```markdown
## Round 1

### Leader 的修改
- 文件: src/utils.ts
- 改了什么: 把 forEach 改成 map，返回新数组
- 为什么改: Debug 用了 push 修改原数组，违反不可变原则

### Debug 的回复
- 判断: 同意
- 改了什么: 无额外修改
- 为什么: Leader 的改法确实更符合项目约定
```

---

## AI-CONTEXT.md

每个项目根目录应有 `AI-CONTEXT.md`，是所有 agent 的共享项目背景。

| 字段 | 内容 |
|------|------|
| 项目简介 | 一两句话说明项目是什么、做什么 |
| 技术栈 | 语言、框架、关键依赖 |
| 目录结构 | 核心目录说明 |
| 架构概要 | 模块关系 |
| 约定 | 命名、代码风格、测试方式 |
| 注意事项 | 踩过的坑、不能动的东西、特殊限制 |

**生成方式**：

| 情况 | Leader 行为 |
|------|------------|
| 项目有 AI-CONTEXT.md | 跳过，直接开始 |
| 没有 AI-CONTEXT.md，有 CLAUDE.md | 从 CLAUDE.md 自动提炼生成 |
| 两者都没有 | 提醒用户手动创建 |

**为什么需要**：所有 agent 读同一份背景信息，减少因信息缺失产生的幻觉。与 CLAUDE.md 分离——CLAUDE.md 是 Claude Code 专属配置，AI-CONTEXT.md 是跨平台共享的。

模板见 [docs/ai-context-template.md](docs/ai-context-template.md)。

---

## Debug 工作场景

### 普通模式（agent-apply / agent-verify）

| 场景 | 触发阶段 | 做什么 |
|------|---------|--------|
| **A：审查+修复** | agent-apply | Coder 完成后，审查全部代码，发现问题直接修 |
| **B：定点修复** | agent-verify | Leader 验收发现具体 bug，给问题列表让你修 |
| **C：验收 Leader 修改** | 讨论轮次 | Leader 改了代码，审查修改是否合理 |

### 对抗赛模式（agent-duel）

| 场景 | 触发阶段 | 做什么 |
|------|---------|--------|
| **D：找 bug** | Round 1 | 从 spec 出发独立探索代码找 bug，返回结构化清单 |
| **E：审对手** | Round 2 | 逐条验证对手 bug 清单，推翻/认同并说明理由 |

普通 Debug 和对抗赛 Debug 是**不同的角色技能**（`debug-engineer` vs `debug-duel`），Leader 根据使用的流程（agent-apply vs agent-duel）选择分派哪种。

## Tester 4 层测试框架

| 层级 | 内容 | 何时执行 |
|------|------|---------|
| **第 1 层：功能正确性** | Happy path、边界值、类型边界 | 始终执行 |
| **第 2 层：错误处理** | 异常类型、错误消息、状态一致性 | 始终执行 |
| **第 3 层：集成点** | 外部依赖 mock、模块间接口 | 有外部依赖时 |
| **第 4 层：回归** | 原始 bug 不复现、相邻功能不受影响 | bug 修复后 |

---

## 核心原则

1. **异步优先**：所有跨 agent 调用异步执行，不阻塞等待
2. **Leader 是通信中心**：所有通信经 Leader 中转
3. **甩手掌柜式委派**：只说做什么，不说怎么做
4. **谁发现谁修**：Debug 发现问题直接修复，不只是报告
5. **讨论有上限**：Leader↔Debug 最多 3 轮，避免无限争论
6. **先验收后测试**：Leader 验收通过才交 Tester
7. **文件是记忆**：discussion.md 和 AI-CONTEXT.md 是跨轮次/跨 agent 的上下文来源

---

## 为什么自建 nanoworker

### 问题：通用 agent 框架的上下文膨胀

之前的 Worker 平台使用通用 agent 框架（OpenClaw），遇到的核心问题：

- **system prompt 臃肿**：框架自带队列协议、状态管理、通信格式等大段约定，每次调用都注入到上下文，大部分内容 Worker 根本用不到
- **工具集过载**：框架注册了网络请求、数据库、消息发送等通用工具，Worker 只需要读写文件和执行命令
- **启动开销大**：Node.js 运行时 + npm 依赖加载 + 队列分派，一次简单调用的启动时间就不短
- **输出格式复杂**：回复嵌套在 `result.payloads[0].text` 里，解析麻烦且脆弱

本质上，Worker 的需求极其明确——在指定目录里读写文件、执行命令、完成编程任务。通用框架为此背负了太多不相关的上下文成本。

### 做了什么：从零写一个专注编程的 Worker CLI

nanoworker 是一个 783 行的 Python CLI，只做一件事：接收任务 → LLM + 工具循环 → 返回结果。

**核心设计决策：**

| 决策 | 做法 | 理由 |
|------|------|------|
| **极简工具集** | 每个角色只注册必需的工具（4-5 个） | 工具 schema 是上下文成本，多一个就多一份 token 消耗 |
| **无状态进程模型** | 每次调用启动独立进程，完成即退出 | 不维护队列、不管理连接池，不存在状态泄漏 |
| **stdout/stderr 分离** | JSON 结果走 stdout，日志走 stderr | Leader 用 `jq -r '.summary'` 一行解析，不怕日志污染 |
| **SKILL.md 注入** | system prompt = 身份头 + 角色 SKILL.md | 上下文只包含当前角色需要的信息，没有框架废话 |
| **按角色裁剪工具** | Tester 没有 edit_file（不该改功能代码） | 从工具层面约束角色边界，不靠 prompt 劝 |
| **litellm 多模型支持** | 通过 litellm 对接任意 OpenAI-compatible API | 换模型只改 config，代码不动 |

**角色工具集：**

| 角色 | 工具 | 为什么这样配 |
|------|------|-------------|
| Coder | read_file, write_file, edit_file, list_dir, exec | 全套读写 + 执行，自主实现功能 |
| Debug | read_file, write_file, edit_file, list_dir, exec | 同 Coder（要能修代码） |
| Tester | read_file, write_file, list_dir, exec | 没有 edit_file，只验证不改功能 |

**代码结构（783 行，6 个模块）：**

```
nanoworker/
├── cli.py       (100 行)  入口：解析参数 → 加载配置 → 构建工具 → 构建 prompt → 运行 → 输出
├── config.py     (67 行)  读 ~/.nanoworker/config.json，全部 frozen dataclass
├── prompt.py     (57 行)  构建 system prompt：身份头 + SKILL.md
├── llm.py        (80 行)  litellm 封装：chat() → LLMResponse(content, tool_calls)
├── runner.py    (150 行)  核心循环：LLM 调用 → 工具执行 → 追踪文件变更 → 返回结果
└── tools/
    ├── base.py       (37 行)  Tool 基类
    ├── __init__.py   (68 行)  ToolRegistry + 角色工具预设
    ├── filesystem.py (158 行)  read_file, write_file, edit_file, list_dir
    └── shell.py       (63 行)  exec（固定 cwd 到 workspace）
```

### 效果

**上下文对比：**

| 指标 | 通用框架 (OpenClaw) | nanoworker |
|------|---------------------|------------|
| system prompt | 大量框架约定 + 协议说明 | **~278 字符**身份头 + SKILL.md 内容 |
| 工具 schema | 通用工具集（含网络、数据库等） | **1.3-1.8 KB**（4-5 个编程工具） |
| 每次调用总上下文 | 未精确测量，预估 15-30 KB | **4-7 KB**（视角色 SKILL.md 大小） |
| 输出解析 | `jq -r '.result.payloads[0].text'` | `jq -r '.summary'` |

**执行性能：**

| 指标 | 数值 |
|------|------|
| 进程启动到首次 LLM 请求 | < 0.1 秒 |
| 简单任务（一问一答） | ~12 秒（取决于 LLM API） |
| 文件创建任务 | ~15-20 秒（2 次迭代） |
| 代码审查任务 | ~15-20 秒（1-3 次迭代） |
| 并行调用 | 多进程独立运行，无锁竞争 |

**代码质量：**

| 指标 | 数值 |
|------|------|
| 总代码量 | 783 行 Python |
| 核心依赖 | 3 个（litellm, typer, loguru） |
| 可变状态 | 0（全部 frozen dataclass） |
| 守护进程/队列 | 无 |

---

## 使用的工具

| 工具 | 用途 |
|------|------|
| [Claude Code](https://docs.anthropic.com/en/docs/claude-code) | Leader 平台，Claude Opus 4.6 |
| [nanoworker](docs/nanoworker-setup.md) | 轻量 Worker agent CLI，运行 GPT-5.4 |

---

## 目录结构

```
.
├── README.md
├── skills/                         # 角色技能文件
│   ├── leader/                     # Leader（编排者）
│   │   ├── orchestration.md        #   核心编排：Agent Registry、消息模板、规则
│   │   ├── agent-apply.md          #   agent-apply 流程（Coder 实现 + Debug 审查）
│   │   ├── agent-duel.md           #   agent-duel 流程（对抗赛审查）
│   │   └── agent-verify.md         #   agent-verify 流程（验收 + 路由）
│   ├── coder/
│   │   └── SKILL.md                # Coder 技能
│   ├── debug/
│   │   └── SKILL.md                # Debug 技能（普通模式）
│   ├── debug-duel/
│   │   └── SKILL.md                # Debug-Duel 技能（对抗赛模式）
│   └── tester/
│       └── SKILL.md                # Tester 技能
├── nanoworker/                     # 轻量 Worker agent CLI 源码
│   ├── cli.py                      #   入口
│   ├── config.py                   #   配置加载
│   ├── prompt.py                   #   system prompt 构建
│   ├── llm.py                      #   LLM 调用封装
│   ├── runner.py                   #   核心工具循环
│   └── tools/                      #   工具实现
└── docs/                           # 文档
    ├── usage-guide.md              #   搭建和部署指南
    ├── nanoworker-setup.md         #   nanoworker 安装配置
    ├── ai-context-template.md      #   AI-CONTEXT.md 模板
    └── multi-agent-rule.md         #   全局规则文件示例
```

## License

MIT
