# Multi-Agent Workflow

> 4 角色异步协作的 AI 多 agent 工作流。

## 角色分工

| 角色 | 模型 | 平台 | 实例数 | 职责 | 不做什么 |
|------|------|------|--------|------|---------|
| **Leader** | Claude Opus 4.6 | Claude Code | 1 | 架构、编排、验收、可动手修正、通信中心 | 从零写大段基础功能 |
| **Coder** | GPT-5.3 Codex | OpenClaw | 1-N | 读需求，自主实现代码+测试，交付 | 架构决策、跨模块判断 |
| **Debug** | GPT-5.3 Codex | OpenClaw | 1-N | 审查代码、定位修复 bug、参与讨论 | 从零写功能、运行测试 |
| **Tester** | GPT-5.3 Codex | OpenClaw | 1 | 最终运行验证 | 写功能代码、直接修 bug |

同一角色可注册多个实例（coder-1/2/3, debug-1/2/3），Leader 从 Agent Registry 动态读取。旧的单实例 `coder`/`debug` 保留向后兼容。

- **Leader 做甩手掌柜**：只给项目路径和任务名称，不给实现方案
- **Leader 是通信中心**：所有 agent 间通信经 Leader 中转，Coder 和 Debug 不直接对话
- **Leader 可以改代码**：验收和讨论中可以动手修正，但不从零写大段功能
- **Debug 必须修复，不只是报告**：发现问题直接修，修完告诉 Leader 改了什么、为什么改
- **Tester 不直接联系 Debug**：发现 bug 报回 Leader 路由

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
    ├── multi-agent-rule.md         # 全局规则（~/.claude/rules/ 每次会话加载）
    ├── leader-orchestration.md     # Leader 编排技能示例
    ├── leader-agent-apply.md       # agent-apply 流程示例
    ├── leader-agent-verify.md      # agent-verify 流程示例
    ├── coder-skill.md              # Coder 技能示例
    ├── debug-skill.md              # Debug 技能示例
    └── tester-skill.md             # Tester 技能示例
```

## License

MIT
