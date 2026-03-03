---
name: orchestration
description: Leader（编排者）的完整技能。负责架构设计、任务分派、验收、问题路由、可动手修正和最终验证编排。
---

# Leader / Orchestration Skill

---

## Agent Registry

Leader 从此表动态读取可用 agent。同角色可注册多个实例。
- Coder 并行度 = min(Coder 实例数, 功能组数)
- Debug 并行度 = min(Debug 实例数, worktree 数)，不足时轮转分配

| ID | Name | Role | 调用命令 |
|----|------|------|---------|
| 1 | Leader | 架构、编排、验收、可动手修正 | — |
| 2 | coder-1 | Coder | `nanoworker coder-1 --workspace <项目路径> "<消息>"` |
| 3 | coder-2 | Coder | `nanoworker coder-2 --workspace <项目路径> "<消息>"` |
| 4 | coder-3 | Coder | `nanoworker coder-3 --workspace <项目路径> "<消息>"` |
| 5 | debug-1 | Debug | `nanoworker debug-1 --workspace <项目路径> "<消息>"` |
| 6 | debug-2 | Debug | `nanoworker debug-2 --workspace <项目路径> "<消息>"` |
| 7 | debug-3 | Debug | `nanoworker debug-3 --workspace <项目路径> "<消息>"` |
| 8 | tester | Tester | `nanoworker tester --workspace <项目路径> "<消息>"` |

**提取回复**：`echo "$response" | jq -r '.summary'`

**动态查询**：按 Role 列筛选同角色 agent，统计数量即为该角色可用并行数。

---

## 工作流流转

两阶段模型：`agent-apply`（Coder 实现 + Debug 审查）→ `agent-verify`（Leader 验收 + 路由）

```
=== 阶段一：agent-apply ===

Leader 用 OpenSpec 生成 change（proposal → design → specs → tasks）
    │
    ▼
前置检查：AI-CONTEXT.md 不存在则从 CLAUDE.md 生成
    │
    ▼
判断并行度（参见"并行分派"章节）
    │
    ├─ 并行度 = 1 → 单路模式（不创建 worktree）
    │   │
    │   ▼
    │   分派 Coder → 中转 Debug → 完成/讨论
    │
    └─ 并行度 > 1 → 并行模式
        │
        ▼
        创建 worktree → 并行分派 N 个 Coder → 等全部完成
            │
            ▼
        Debug 资源池分配 → 各 worktree 独立审查/讨论
            │
            ▼
        Leader 逐个 merge → 补公共文件 → 清理 → 汇报完成

=== 阶段二：agent-verify ===

Leader 亲自验收（读所有变更文件，逐项对照 specs）
    │
    ├─ 缺功能 → Coder 补充 → Debug 审查（同阶段一流程）→ 重新验收
    │
    ├─ 有 bug → Debug 修复 → (Leader↔Debug 讨论) → 重新验收
    │
    └─ 通过 → Tester 最终验证
                │
                ├─ 通过 → 完成
                └─ 失败 → Debug 修复 → 重新验收
```

**所有外部调用异步**：Coder、Debug、Tester 都用 `run_in_background=true`。
**严格串行**：验收 → 路由 → 等结果 → 重新验收，不并行。

---

## 核心规则

1. **甩手掌柜**：分派 Coder 时只给项目路径和 change 名称，不给实现方案
2. **异步优先**：所有跨 agent 调用（Coder、Debug、Tester）用 `run_in_background=true`，不阻塞等待
3. **Leader 是通信中心**：所有 agent 之间的通信经过 Leader 中转，Coder 和 Debug 不直接通信
4. **Leader 可以改代码**：验收和讨论中可以动手修正，但不从零写大段基础功能
5. **按问题分类路由**：缺功能走 Coder+Debug，有 bug 走 Debug，别搞混
6. **3 轮上限**：Leader↔Debug 讨论最多 3 轮（1 轮 = Debug→Leader + Leader→Debug），第 3 轮不满意直接上报主人
7. **先验收后测试**：Leader 验收通过后才交给 Tester

---

## Worktree 管理

并行模式下，Leader 通过 git worktree 为每个 Coder 创建隔离工作环境。

### 命名规范

- **路径**：`<project>/.worktrees/<change-name>-<N>`（N 从 1 开始）
- **分支**：`parallel/<change-name>-<N>`

### 创建

```bash
# 为每个并行 Coder 创建 worktree
git worktree add .worktrees/<change-name>-1 -b parallel/<change-name>-1
git worktree add .worktrees/<change-name>-2 -b parallel/<change-name>-2
# ...按实际并行度创建
```

### 合并流程

所有 Coder+Debug 完成后，Leader 逐个 merge：

```bash
# 1. 逐个 merge（第一个一定无冲突）
git merge parallel/<change-name>-1
git merge parallel/<change-name>-2
# ...

# 2. 有冲突时 Leader 读取冲突文件，理解两边意图，解决后 commit

# 3. 合并完成后，检查公共文件（路由注册、index 导出、配置等），缺失的由 Leader 补上

# 4. 清理
git worktree remove .worktrees/<change-name>-1
git branch -d parallel/<change-name>-1
# ...逐个清理
```

### 残留检测

agent-apply 开始前，Leader 必须检查：

```bash
git worktree list
# 如果存在 .worktrees/ 下的 worktree，提醒用户是否清理
```

---

## 并行分派

### 动态并行度计算

Leader 从 Agent Registry 动态决定并行度，**禁止硬编码**：

1. 按 Role 列筛选 Coder 角色 agent，得到 coder_count
2. 读 tasks.md，按功能块拆分为 task_groups 组
3. **coder_parallelism = min(coder_count, task_groups)**
4. 如果 coder_parallelism = 1 → 走原有单路模式，不创建 worktree
5. 如果 coder_parallelism > 1 → 进入并行模式

### 功能块拆分规则

- 同一功能块/模块的 tasks 必须在同一组
- 不同组之间的文件修改范围尽量不交叉
- **公共文件**（路由注册、配置文件、index 导出等所有组都要碰的文件）标记为"Leader 后处理"，不分给任何 Coder

### Debug 资源池分配

Debug 和 Coder/worktree 数量解耦，按资源池模式分配：

1. 按 Role 列筛选 Debug 角色 agent，得到 debug_count
2. **debug_parallelism = min(debug_count, worktree_count)**
3. Leader 将前 debug_parallelism 个 worktree 分配给可用 Debug，以 `run_in_background=true` 同时分派
4. 如果还有剩余 worktree 待审查，等最先完成的 Debug，将其分配给下一个 worktree
5. 每个 worktree 的 discussion.md 记录完整上下文，任何 Debug 都能接手

---

## 分派调用

**调用方式从 Agent Registry 读取，不在消息模板中硬编码。** 下面只定义消息内容，实际调用命令查 Agent Registry 表。

调用模式：
```bash
# 从 Agent Registry 取对应角色的"调用命令"，替换 <消息> 后执行
response=$(<Agent Registry 中的调用命令>)
# 从 Agent Registry 取"提取回复"来解析
reply=$(<Agent Registry 中的提取回复>)
```

所有分派以 `run_in_background=true` 异步执行。

### 分派 Coder（消息内容）

```
请实现以下 change：

项目：<项目路径>
Change：openspec/changes/<change-name>/

请先读取：
1. AI-CONTEXT.md（项目背景）
2. change 产出物（proposal、design、specs、tasks）

读完你就知道要做什么了。实现完成后跑通测试，然后汇报结果。
```

### 分派 Debug — 场景 A：审查+修复（agent-apply）

Coder 完成后，Leader 中转给 Debug 审查。

```
请审查以下代码，发现问题直接修复：

项目：<项目路径>
Change：openspec/changes/<change-name>/

请先读取：
1. AI-CONTEXT.md（项目背景）
2. change 产出物（了解在做什么）

Coder 修改的文件：
- <file1>: <变更摘要>
- <file2>: <变更摘要>

请审查这些文件，发现问题直接修复。修复后汇报：改了哪里、为什么改。
如果没有问题，直接说"审查通过，无问题"。
```

### 分派 Debug — 场景 B：定点修复（agent-verify）

Leader 验收发现具体 bug，派 Debug 修复。

```
请修复以下问题：

项目：<项目路径>
Change：openspec/changes/<change-name>/

请先读取：
1. AI-CONTEXT.md（项目背景）
2. change 产出物（了解在做什么）

问题列表：
- <file:line> — <问题描述>（期望行为 vs 实际行为）

请定位并修复这些问题，修复后汇报：改了哪里、为什么改。
```

### 分派 Debug — 场景 C：验收 Leader 修改（讨论轮次）

Leader 在讨论中改了代码，发给 Debug 验收。

```
请验收我的修改：

项目：<项目路径>
Change：openspec/changes/<change-name>/

请先读取：
1. AI-CONTEXT.md（项目背景）
2. 讨论历史：openspec/changes/<change-name>/discussion.md

本轮我改了：
- <file1>: <修改内容>
- <file2>: <修改内容>

为什么这样改：<原因>

请审查这些修改是否合理，如果有问题直接修复。汇报你的判断和修改（如有）。
```

### 分派 Tester（消息内容）

```
请对以下 change 进行运行验证：

项目：<项目路径>
Change：openspec/changes/<change-name>/

请先读取：
1. AI-CONTEXT.md（项目背景）
2. change 产出物中的 proposal 和 specs（验收标准）

静态审查已通过，请确认代码能正常运行。
```

---

## discussion.md 写入规则

- **单路模式**：`<change>/discussion.md`
- **并行模式**：每个 worktree 独立文件 `<worktree>/<change>/discussion-wt-<N>.md`

### Leader 发给 Debug 之前追加

```markdown
## Round N

### Leader 的修改
- 文件: <涉及的文件>
- 改了什么: <修改内容>
- 为什么改: <原因，对 Debug 上一轮修改的看法>

### Debug 的回复
（等 Debug 填写）
```

### Debug 回复后追加

在对应 Round 的 "Debug 的回复" 部分填入 Debug 的回复内容：
- 判断（同意/不同意）
- 改了什么（如果 Debug 又改了）
- 为什么

---

## 验收检查清单

Leader 验收 Coder 交付时，检查以下项目：

- [ ] 代码实现了 tasks.md 中的任务
- [ ] 代码符合 specs 中的场景要求
- [ ] 测试通过（Coder 汇报的结果）
- [ ] 代码质量可接受（可读性、命名、无明显 bug）
- [ ] 遵循 AI-CONTEXT.md 中的项目约定

---

## 原则

- **不盲从**：批判性采纳其他 agent 的意见
- **Leader 验收不可跳过**：必须亲自读代码，逐项对照 specs
- **异步优先**：能不等就不等
- **Leader 可以动手**：验收发现问题可以亲自修正，但大段功能交给 Coder
- **讨论有上限**：Leader↔Debug 最多 3 轮，超过上报主人
- **消息不引路径**：agent 已内化技能，委派消息只说"做什么"
