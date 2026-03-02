# Multi-Agent Workflow

> 4 角色异步协作的 AI 多 agent 工作流。

## 角色分工

| 角色 | 模型 | 平台 | 职责 | 不做什么 |
|------|------|------|------|---------|
| **Leader** | Claude Opus 4.6 | Claude Code | 架构、编排、验收、可动手修正、通信中心 | 从零写大段基础功能 |
| **Coder** | GPT-5.3 Codex | OpenClaw | 读需求，自主实现代码+测试，交付 | 架构决策、跨模块判断 |
| **Debug** | GPT-5.3 Codex | OpenClaw | 审查代码、定位修复 bug、参与讨论 | 从零写功能、运行测试 |
| **Tester** | GPT-5.3 Codex | OpenClaw | 最终运行验证 | 写功能代码、直接修 bug |

- **Leader 做甩手掌柜**：只给项目路径和任务名称，不给实现方案
- **Leader 是通信中心**：所有 agent 间通信经 Leader 中转，Coder 和 Debug 不直接对话
- **Leader 可以改代码**：验收和讨论中可以动手修正，但不从零写大段功能
- **Debug 必须修复，不只是报告**：发现问题直接修，修完告诉 Leader 改了什么、为什么改
- **Tester 不直接联系 Debug**：发现 bug 报回 Leader 路由

---

## 两阶段工作流

### 阶段一：agent-apply（Coder 实现 + Debug 审查）

```
Leader 规划任务（proposal → design → specs → tasks）
    │
    ▼
前置检查：AI-CONTEXT.md
┌──────────────────────────┐
│ 存在？ ─── 是 ──→ 跳过    │
│    │                     │
│   否                     │
│    │                     │
│ 有 CLAUDE.md？           │
│  ├─ 是 → 从中生成        │
│  └─ 否 → 提醒用户        │
└──────────────────────────┘
    │
    ▼
异步分派 Coder（甩手掌柜：只给路径+名称）
    │
    ▼
Coder 完成 → Leader 中转给 Debug（异步）
    │
    ├─ Debug: 无问题 ──────→ 汇报完成
    │
    └─ Debug: 修复了问题 → Leader 审查
         │
         ├─ 满意 ──────→ 汇报完成
         │
         └─ 不满意 → Leader↔Debug 讨论（最多 3 轮）
              └─ 第 3 轮还不行 → 上报用户
```

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

---

## 异步调用模型

所有外部 agent 调用以 `run_in_background=true` 异步执行，Leader 不阻塞等待。

```
Leader                     Coder                    Debug
  │                          │                        │
  ├── 异步分派 ─────────────→│                        │
  │                          │                        │
  │   继续做其他事...          │ 执行中...               │
  │                          │                        │
  │←── 系统通知完成 ─────────┤                        │
  │                          │                        │
  ├── 异步中转 ─────────────────────────────────────→│
  │                          │                        │
  │   继续做其他事...          │                        │ 审查中...
  │                          │                        │
  │←── 系统通知完成 ─────────────────────────────────┤
  ▼
```

---

## Leader↔Debug 讨论机制

```
1 轮 = Debug→Leader + Leader→Debug

第 1 轮：Debug 修复 → Leader 不满意 → Leader 改代码发回 Debug
第 2 轮：Debug 审查 → Leader 不满意 → Leader 改代码发回 Debug
第 3 轮：Debug 审查 → Leader 还不满意 → 停止，上报用户
```

每轮记录在 `discussion.md`：

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

模板见 [examples/ai-context-template.md](examples/ai-context-template.md)。

---

## Debug 三种工作场景

| 场景 | 触发阶段 | 做什么 |
|------|---------|--------|
| **A：审查+修复** | agent-apply | Coder 完成后，审查全部代码，发现问题直接修 |
| **B：定点修复** | agent-verify | Leader 验收发现具体 bug，给问题列表让你修 |
| **C：验收 Leader 修改** | 讨论轮次 | Leader 改了代码，审查修改是否合理 |

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

## 使用的工具

| 工具 | 用途 |
|------|------|
| [Claude Code](https://docs.anthropic.com/en/docs/claude-code) | Leader 平台，Claude Opus 4.6 |
| [OpenClaw](https://github.com/nicobailon/openclaw) | 外部 agent 平台，运行 GPT-5.3 Codex |

---

## 目录结构

```
.
├── README.md                       # 本文
└── examples/
    ├── usage-guide.md              # 使用指南：搭建和部署
    ├── ai-context-template.md      # AI-CONTEXT.md 模板
    ├── leader-orchestration.md     # Leader 编排技能示例
    ├── leader-agent-apply.md       # agent-apply 流程示例
    ├── leader-agent-verify.md      # agent-verify 流程示例
    ├── coder-skill.md              # Coder 技能示例
    ├── debug-skill.md              # Debug 技能示例
    └── tester-skill.md             # Tester 技能示例
```

## License

MIT
