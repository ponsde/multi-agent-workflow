# Multi-Agent Workflow：我的多 AI Agent 协作实践

> 从单 agent vibe coding 到 4 角色异步协作的演进记录。

## 背景

在单单使用 Claude Code 来 vibe coding 时，在把大 max 用到周限的过程中，发现了很多问题——硬编码过多、bug 不断、实现不清晰等。单个 AI 写代码时容易产生幻觉，自己写的 bug 自己很难发现，和人一样。于是我试图让多 agent 参与进来，用不同的"视角"互相校验。

## 演进过程

### 第一阶段：聊天式协作（失败）

最初想法很简单：让另一个 AI 帮忙审查代码。但如果直接通过聊天的形式沟通，协作 agent 无法共通代码——需要主 agent 把代码片段发过去，但对方看不到完整的项目上下文，审查质量很差，反而降低效率。

### 第二阶段：OpenClaw + 同步调用（能用但慢）

后来我发现了 [OpenClaw](https://github.com/nicobailon/openclaw)，AI 可以拥有自己独立的 memory，同时能观看完整的项目代码并直接修改。我接入了 Codex 5.3（GPT-5.3），它的长任务执行较好且 debug 能力强，能较好地帮助 Claude 进行代码审查。

多 agent 协作的核心价值：**降低单一模型的幻觉概率**。两个不同的模型互相审查，能提出不同的视角和建议，比一个模型自己写自己查靠谱得多。

但这一版还是基础的同步调用——主 agent 发出任务后阻塞等待协作 agent 执行完毕，效率不高。

### 第三阶段：异步调用 + 两阶段模型（当前）

把所有外部 agent 调用改成异步（`run_in_background=true`），主 agent 发出任务后不阻塞，继续做自己的事，等系统通知完成时再处理回调。

同时把工作流重新设计为两阶段模型，角色也从 3 个拆分为 4 个。

## 当前架构

### 角色分工

| 角色 | 模型 | 平台 | 职责 | 不做什么 |
|------|------|------|------|---------|
| **Leader** | Claude Opus 4.6 | Claude Code | 架构、编排、验收、可动手修正、通信中心 | 从零写大段基础功能 |
| **Coder** | GPT-5.3 Codex | OpenClaw | 读需求，自主实现代码+测试，交付 | 架构决策、跨模块判断 |
| **Debug** | GPT-5.3 Codex | OpenClaw | 审查代码、定位修复 bug、参与讨论 | 从零写功能、运行测试 |
| **Tester** | GPT-5.3 Codex | OpenClaw | 最终运行验证 | 写功能代码、直接修 bug |

**为什么这样分？**

- **Leader 做甩手掌柜**：分派任务时只给项目路径和任务名称，不给具体实现方案。让 Coder 自己决定怎么实现——这样如果实现有问题，是 Coder 自己的理解问题，Leader 验收时更容易发现偏差。
- **Leader 是通信中心**：所有 agent 之间的通信必须经过 Leader 中转。Coder 和 Debug 不直接对话。这样 Leader 可以作为中间管控，了解全局进展。
- **Leader 可以改代码**：Leader 不是纯管理者，验收和讨论中可以亲自动手修正，但不从零写大段功能（那是 Coder 的活）。
- **Debug 必须修复，不只是报告**：早期版本 Debug 只报告问题让别人修，效率太低。现在要求发现问题直接修，修完告诉 Leader 改了什么、为什么改。
- **Tester 不直接联系 Debug**：发现 bug 报回 Leader，由 Leader 路由，保持通信中心的一致性。

### 两阶段工作流

#### 阶段一：agent-apply（Coder 实现 + Debug 审查）

```
Leader 生成任务（用 OpenSpec 规划：proposal → design → specs → tasks）
    │
    ▼
前置检查：项目是否有 AI-CONTEXT.md？没有则从 CLAUDE.md 生成
    │
    ▼
Leader 把任务甩给 Coder（异步，只给项目路径 + 任务名称）
    │
    ▼
Coder 完成 → Leader 中转给 Debug 审查（异步）
    │
    ├─ Debug 无问题 → 汇报完成
    │
    └─ Debug 发现问题并修复 → Leader 审查 Debug 的修复
         │
         ├─ Leader 满意 → 汇报完成
         │
         └─ Leader 不满意 → Leader 改代码 → 发给 Debug 验收
              │
              └─ Leader↔Debug 讨论（最多 3 轮）
                   └─ 第 3 轮还不行 → 上报用户决策
```

**讨论机制**：Leader 和 Debug 之间的讨论记录在 `discussion.md` 里，每轮记录谁改了什么、为什么改。1 轮 = Debug→Leader + Leader→Debug，最多 3 轮，超过则上报用户——避免两个 AI 无限争论。

#### 阶段二：agent-verify（Leader 验收 + 路由）

```
Leader 亲自验收（读所有代码，逐项对照 specs）
    │
    ├─ 缺功能 → Coder 补充 + Debug 审查（同阶段一）→ 重新验收
    │
    ├─ 有 bug → Debug 修复 → Leader↔Debug 讨论 → 重新验收
    │
    └─ 通过 → Tester 最终运行验证
                │
                ├─ 通过 → 完成 🎉
                └─ 失败 → Debug 修复 → 重新验收
```

**路由逻辑**：缺功能走 Coder+Debug，有 bug 走 Debug。不要搞混——缺功能让 Debug 修是修不好的，Debug 擅长的是在已有代码中找问题和修 bug。

### 项目上下文共享

每个项目里有一个 `AI-CONTEXT.md`，是从 Claude Code 生成的 `CLAUDE.md` 提炼出来的项目全景——项目简介、技术栈、目录结构、架构概要、约定、注意事项。

Leader 在开始工作前会检查：没有 AI-CONTEXT.md 就从 CLAUDE.md 生成一份。所有 agent 收到任务后第一件事就是读它，确保每个 agent 有相同的项目背景，不会因为缺乏上下文而产生幻觉。

### 技能内化

每个角色有自己的 SKILL.md，是自包含的技能文件，定义了：

- **角色职责和边界**（做什么、不做什么）
- **工作流程**（收到任务后一步步怎么做）
- **审查/测试框架**（Debug 的 3 层审查模型、Tester 的 4 层测试模型）
- **汇报格式**（标准化的输出格式，方便 Leader 解析）
- **讨论规则**（怎么写 discussion.md、怎么回复）

部署方式：把 SKILL.md 放到对应 agent 的 workspace 里，平台原生加载。委派消息里只说"做什么"，不说"怎么做"——agent 的技能是内化的，不需要在消息里引用任何技能文件路径。

### Debug 的三种工作场景

Debug 不是只有一种工作模式，根据被调用的阶段不同，有三种场景：

| 场景 | 触发阶段 | 做什么 |
|------|---------|--------|
| **A：审查+修复** | agent-apply | Coder 完成后，审查全部代码，发现问题直接修 |
| **B：定点修复** | agent-verify | Leader 验收发现具体 bug，给问题列表让你修 |
| **C：验收 Leader 修改** | 讨论轮次 | Leader 改了代码，审查修改是否合理 |

### Tester 的 4 层测试框架

| 层级 | 内容 | 何时执行 |
|------|------|---------|
| **第 1 层：功能正确性** | Happy path、边界值、类型边界 | 始终执行 |
| **第 2 层：错误处理** | 异常类型、错误消息、状态一致性 | 始终执行 |
| **第 3 层：集成点** | 外部依赖 mock、模块间接口 | 有外部依赖时 |
| **第 4 层：回归** | 原始 bug 不复现、相邻功能不受影响 | bug 修复后 |

## 核心设计原则

1. **异步优先**：所有跨 agent 调用异步执行，不阻塞等待
2. **Leader 是通信中心**：所有通信经 Leader 中转，保持全局可控
3. **甩手掌柜式委派**：只说做什么，不说怎么做
4. **谁发现谁修**：Debug 发现问题直接修复，不只是报告
5. **讨论有上限**：Leader↔Debug 最多 3 轮，避免 AI 无限争论
6. **先验收后测试**：Leader 验收通过才交 Tester，不浪费测试资源
7. **文件是记忆**：discussion.md 和 AI-CONTEXT.md 是跨轮次/跨 agent 的上下文来源

## 使用的工具

| 工具 | 用途 |
|------|------|
| [Claude Code](https://docs.anthropic.com/en/docs/claude-code) | Leader 平台，Claude Opus 4.6 |
| [OpenClaw](https://github.com/nicobailon/openclaw) | 外部 agent 平台，运行 GPT-5.3 Codex |
| [OpenSpec](https://github.com/nicobailon/openspec) | 规范驱动的变更管理（我自己改的中文版） |

## 反思

OpenClaw 能用，但**太重了**。启动慢、配置复杂、消息队列偶尔抽风。理想状态是有一个更轻量的方式让不同 AI 模型共享同一个代码仓库并异步协作。

多 agent 的核心价值不在于"更多人干活"，而在于**不同视角的交叉验证**。一个模型写的代码，另一个模型来审查，比同一个模型自审靠谱得多。这和人类团队的代码审查是一样的道理。

## 目录结构

```
.
├── README.md                     # 本文
├── docs/
│   └── workflow-detail.md        # 详细工作流说明
└── examples/
    ├── leader-orchestration.md   # Leader 编排技能示例
    ├── leader-agent-apply.md     # agent-apply 流程技能示例
    ├── leader-agent-verify.md    # agent-verify 流程技能示例
    ├── coder-skill.md            # Coder 技能示例
    ├── debug-skill.md            # Debug 技能示例
    └── tester-skill.md           # Tester 技能示例
```

## License

MIT
