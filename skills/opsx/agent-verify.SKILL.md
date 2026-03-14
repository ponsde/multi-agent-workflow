---
name: openspec-agent-verify
description: Leader 验收实现完整性（代码质量已在 apply 阶段优化）。缺功能走 Coder+Debug，有 bug 走 Debug，通过走 Tester。
---

> **CRITICAL: 本技能中所有 Coder/Debug/Tester 调用必须用 Bash 工具执行 `nanoworker` CLI 命令。绝对禁止使用 Agent tool 创建子 agent。Agent tool 会启动 Claude Code 子进程（Sonnet），而不是 nanoworker worker。正确做法：`Bash(command="nanoworker debug-1 --workspace <path> '<msg>'", run_in_background=true)`**

# Agent Verify（Leader 验收 + 路由）

在 `/opsx:agent-apply`（Coder 实现 + Debug 审查 + Leader 优化）之后使用。代码质量已在 apply 阶段由 Leader 优化，本阶段检查实现完整性并路由问题。

---

## 步骤

### 1. 选择变更

与原版相同：从参数、上下文或列表中确定变更名称。

### 2. Leader 验收实现完整性

代码质量已在 agent-apply 阶段由 Leader 优化完成。本阶段只检查**实现是否完整落地**。

Leader **亲自**阅读所有变更文件的完整内容（不只看 diff），对照 specs 和 tasks 逐项检查：

**检查清单：**
- [ ] tasks.md 中的所有任务都有对应实现
- [ ] specs 中的每个场景都已覆盖
- [ ] 没有遗漏的需求（对照 proposal 和 design）
- [ ] 代码逻辑正确，无明显 bug
- [ ] 测试通过且覆盖关键场景

### 3. 分类问题并路由

验收结果分三种情况，**严格串行，不可并行**：

#### 情况 A：缺少功能

Coder 漏了需求或实现不完整。

→ **走 Coder+Debug 流程**（同 agent-apply）：

1. **用 Bash 工具执行 nanoworker CLI**（禁止用 Agent tool）派 Coder 补充（从 Agent Registry 取命令），以 `run_in_background=true` 异步发送，消息说明缺了什么
2. Coder 完成后，Leader **用 Bash 工具执行 nanoworker CLI** 中转给 Debug 审查（从 Agent Registry 取命令），以 `run_in_background=true` 异步发送
3. 如有问题，进入 Leader↔Debug 讨论（参见 agent-apply 步骤 8a，最多 3 轮）
4. 完成后 → 回到步骤 2 重新验收

#### 情况 B：有 Bug

代码有逻辑错误、边界问题等。

→ **用 Bash 工具执行 nanoworker CLI**（禁止用 Agent tool）派 Debug 修复（从 Agent Registry 取命令），以 `run_in_background=true` 异步发送，消息包含具体问题列表。

Debug 完成后 Leader 审查：
- **Leader 满意** → 回到步骤 2 重新验收
- **Leader 不满意** → 进入 Leader↔Debug 讨论（同 agent-apply 步骤 8a，最多 3 轮）

#### 情况 C：验收通过

所有任务已实现，无功能缺失，无 bug。

→ **用 Bash 工具执行 nanoworker CLI**（禁止用 Agent tool）派 Tester 运行验证（从 Agent Registry 取命令），以 `run_in_background=true` 异步发送。

### 4. 处理 Tester 结果

**Tester 通过**：

```
## 验收完成

**变更：** <change-name>
**Leader 验收：** 通过 ✓
**Tester 验证：** 通过 ✓

所有任务已完成！运行 `/opsx:archive` 归档此变更。
```

在 tasks.md 中标记对应任务为 `[x]`。

**Tester 发现问题**：

Tester 报告的是运行时问题（有具体错误信息和复现步骤）。

→ 回到步骤 3 情况 B，派 Debug 修复（这次有运行时错误信息，定位更准）。

---

## 路由决策树

```
Leader 验收
    │
    ├─ 缺功能 → Coder 补充 → Debug 审查 → 重新验收
    │
    ├─ 有 bug → Debug 修复 → (Leader↔Debug 讨论) → 重新验收
    │
    └─ 通过 → Tester 验证
                │
                ├─ 通过 → 完成
                └─ 失败 → Debug 修复 → 重新验收
```

---

## 原则

- **Leader 必须亲自看代码** — 不能跳过验收直接派 Debug 或 Tester
- **Leader 可以改代码** — 发现问题可以亲自修正，但不从零写大段功能
- **严格串行** — 验收 → 路由 → 等结果 → 重新验收，不并行
- **所有调用异步** — Coder、Debug、Tester 都用 `run_in_background=true`
- **问题分类要准确** — 缺功能走 Coder+Debug，有 bug 走 Debug，别搞混
- **Tester 最后才上** — 只有 Leader 验收通过后才派 Tester
