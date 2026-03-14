---
name: openspec-agent-verify
description: Leader 验收 Coder+Debug 交付，按问题类型路由。缺功能走 Coder+Debug，有 bug 走 Debug，通过走 Tester。
---

> **CRITICAL: 本技能中所有 Coder/Debug/Tester 调用必须用 Bash 工具执行 `nanoworker` CLI 命令。绝对禁止使用 Agent tool 创建子 agent。Agent tool 会启动 Claude Code 子进程（Sonnet），而不是 nanoworker worker。正确做法：`Bash(command="nanoworker debug-1 --workspace <path> '<msg>'", run_in_background=true)`**

# Agent Verify（Leader 验收 + 路由）

在 `/opsx:agent-apply`（Coder 实现 + Debug 审查）之后使用。Leader 亲自验收代码，然后按问题类型路由。

---

## 步骤

### 1. 选择变更

与原版相同：从参数、上下文或列表中确定变更名称。

### 2. Leader 验收

Leader **亲自**阅读 Coder/Debug 修改的**所有文件的完整内容**（不只看 diff），以老练程序员的标准做工程化验收。

**6 维检查清单（详见 Leader SKILL.md 验收检查清单）：**

1. **范围一致性** — 所有 tasks/specs 都实现了，没有超 scope
2. **正确性** — 正常流、边界、错误处理、并发安全
3. **代码优雅性** — 简洁直接、无绕弯、无重复、无 dead code
4. **命名与术语** — 准确表达意图、与项目一致、无 AI 味注释
5. **架构与结构** — 符合现有模式、函数单一职责、文件不膨胀（>800 行必须评估拆分）
6. **可维护性** — 未来改动不会越来越难、无硬编码、嵌套合理、数据不可变

### 3. 分类问题并路由

验收结果分四种情况，**严格串行，不可并行**：

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

#### 情况 C：结构 / 命名 / 维护性问题

代码能跑但工程质量不达标：文件过大、命名不准确、术语漂移、结构混杂、可维护性差。

→ Leader 判断：
- **小修**（命名修正、注释调整、小范围重构）→ Leader 自己改，改完回到步骤 2 重新验收
- **大改**（文件拆分、模块重组、接口重新设计）→ 回 agent-apply，给 Coder 明确的重构目标

#### 情况 D：规格 / 变更定义有问题

实现过程中暴露出 change 产出物本身的歧义、遗漏或不合理。

→ 回 agent-change-review。告知用户发现了什么问题，建议重新审查 change。

#### 情况 E：验收通过

所有 6 维检查项通过，无功能缺失，无 bug，工程质量达标。

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
