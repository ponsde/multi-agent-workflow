---
name: openspec-agent-apply-duel
description: 多 agent 委派模式 apply（对抗赛版）。Coder 实现 → Duel Debug 竞赛审查（环形互审 + Leader 裁决）→ 修复 → 完成。本质是 agent-apply 的 Debug 审查替代方案。
---

> **CRITICAL: 本技能中所有 Coder/Duel/Debug/Tester 调用必须用 Bash 工具执行 `nanoworker` CLI 命令。绝对禁止使用 Agent tool 创建子 agent。Agent tool 会启动 Claude Code 子进程（Sonnet），而不是 nanoworker worker。正确做法：`Bash(command="nanoworker duel-1 --workspace <path> '<msg>'", run_in_background=true)`**

# Agent Apply Duel（Coder 实现 + Duel Debug 对抗赛审查）

Coder 实现代码，然后由多个 Duel Debug agent 通过竞赛对抗审查（Round 1 并行找 bug → Round 2 环形互审 → Leader 裁决），最后修复确认的 bug。

---

## 步骤

### 1. 选择变更

如果提供了名称，使用它。否则：
- 如果用户提到了某个变更，从对话上下文中推断
- 如果只存在一个活动变更，自动选择
- 如果不明确，运行 `openspec-cn list --json` 获取可用变更，让用户选择

### 2. 前置检查

#### 2a. AI-CONTEXT.md

检查目标项目根目录是否存在 AI-CONTEXT.md：
- **存在** → 跳过
- **不存在，但有 CLAUDE.md** → 读取 CLAUDE.md，提取项目信息（项目简介、技术栈、目录结构、架构概要、约定、注意事项），按 `templates/AI-CONTEXT.md` 格式填入，写到项目根目录
- **两者都没有** → 提醒用户手动创建后再继续

#### 2b. Debug-Duel agent 数量

从 Agent Registry 按 Role=`Debug-Duel` 筛选：
- `N >= 2` → 继续
- `N < 2` → 提示用户"Debug-Duel agent 不足，对抗赛需要至少 2 个。"并退出

### 3. 读取上下文

```bash
openspec-cn instructions apply --change "<name>" --json
```

阅读 contextFiles 中列出的文件（proposal, design, specs, tasks）。

> **重要：tasks 未完成是正常状态。** 本流程的目的就是先分派 Coder 实现（步骤 5），然后再 Duel Debug 审查。不要因为 tasks 未打勾就中断流程或询问用户。直接继续步骤 4。

### 4. 判断 Coder 并行度

1. 从 Agent Registry 统计 Coder 角色 agent 数量 → coder_count
2. 将 tasks 按功能块拆分为组 → task_groups
3. **coder_parallelism = min(coder_count, task_groups)**
4. 如果 coder_parallelism = 1 → **单路模式**
5. 如果 coder_parallelism > 1 → **并行模式**

---

## 单路模式（并行度 = 1）

### 5. 分派给 Coder

用 Bash 工具执行 nanoworker CLI，从 Agent Registry 取 Coder 调用命令：

```bash
Bash(command="nanoworker coder-1 --workspace <项目路径> '消息内容'", run_in_background=true)
```

**消息内容：**

```
请实现以下 change：

项目：<项目路径>
Change：openspec/changes/<change-name>/

请先读取：
1. AI-CONTEXT.md（项目背景）
2. change 产出物（proposal、design、specs、tasks）

读完你就知道要做什么了。实现完成后跑通测试，然后汇报结果。
```

### 6. 等待 Coder 完成

- 有其他工作：继续做，系统通知完成时再处理
- 没有其他工作：`TaskOutput(task_id, block=true)` 等待

### 7. Duel Debug 对抗赛审查

#### 7a. Round 1：并行找 bug

从 Agent Registry 取所有 Debug-Duel agent（duel-1, duel-2, duel-3...），对每个 agent 分派：

```bash
Bash(command="nanoworker duel-1 --workspace <项目路径> '消息内容'", run_in_background=true)
Bash(command="nanoworker duel-2 --workspace <项目路径> '消息内容'", run_in_background=true)
Bash(command="nanoworker duel-3 --workspace <项目路径> '消息内容'", run_in_background=true)
```

**消息内容：**

```
请参加 Bug 猎人竞赛，执行任务 A：找 bug。

🎮 Bug 猎人竞赛

你正在参加一场 Bug 猎人竞赛。规则如下：

**评分规则：**
- 发现低影响 bug：+1 分
- 发现中影响 bug：+5 分
- 发现致命 bug：+10 分

**两种任务类型：**
- 任务 A — 找 bug：从 spec 出发独立探索代码，尽可能多地找到真实 bug
- 任务 B — 审对手：逐条验证对手的 bug 清单，推翻对手得该 bug 的分数，推翻错了扣 2 倍分数

裁判（Leader）会告诉你本次执行哪种任务。

📋 本次任务：任务 A — 找 bug

项目：<项目路径>
Change：openspec/changes/<change-name>/
Spec 路径：openspec/changes/<change-name>/specs/

请先读取：
1. AI-CONTEXT.md（项目背景）
2. change 的 spec（了解需求）

然后从 spec 出发，自行探索项目代码，找到尽可能多的真实 bug。
不限于任何特定文件——你决定审查范围。

完成后返回结构化 bug 清单（格式见你的技能说明）。
```

- **不给 Coder 修改清单**（避免锚定）
- 所有分派使用 `run_in_background=true` 并行执行
- 等待所有完成，收集每个 agent 的结构化 bug 清单

#### 7b. Round 2：环形互审

按环形拓扑分配互审对象：`agent[i]` 审 `agent[(i-1) % N]` 的清单。

具体映射（以 N=3 为例）：
- duel-1 审 duel-3 的清单
- duel-2 审 duel-1 的清单
- duel-3 审 duel-2 的清单

对每个 agent 发起**新的 nanoworker 调用**（新会话，禁止复用 Round 1 会话）：

```bash
Bash(command="nanoworker duel-1 --workspace <项目路径> '消息内容'", run_in_background=true)
# ...对每个 duel agent 都发
```

**消息内容：**

```
请参加 Bug 猎人竞赛，执行任务 B：审查对手清单。

🎮 Bug 猎人竞赛

你正在参加一场 Bug 猎人竞赛。规则如下：

**评分规则：**
- 发现低影响 bug：+1 分
- 发现中影响 bug：+5 分
- 发现致命 bug：+10 分

**两种任务类型：**
- 任务 A — 找 bug：从 spec 出发独立探索代码，尽可能多地找到真实 bug
- 任务 B — 审对手：逐条验证对手的 bug 清单，推翻对手得该 bug 的分数，推翻错了扣 2 倍分数

裁判（Leader）会告诉你本次执行哪种任务。

📋 本次任务：任务 B — 审查对手清单

项目：<项目路径>
Change：openspec/changes/<change-name>/
Spec 路径：openspec/changes/<change-name>/specs/

**对抗评分规则：**
- 成功推翻对手的 bug：得该 bug 的分数
- 推翻错了（该 bug 确实存在）：扣 2 倍分数

请先读取：
1. AI-CONTEXT.md（项目背景）
2. change 的 spec（了解需求）

**对手的 bug 清单：**
<对手 bug 清单——仅结论，不含推理过程>

请逐条去代码中独立验证，标注推翻/认同及理由。
完成后返回结构化对抗报告（格式见你的技能说明）。
```

- 将对手清单（**仅结论，去掉推理过程**）填入 `<对手 bug 清单>` 占位符
- 所有分派使用 `run_in_background=true` 并行执行
- 等待所有完成，收集每个 agent 的对抗报告

#### 7c. Leader 裁决

汇总所有 Round 1 清单和 Round 2 对抗报告，按以下规则逐条判定：

| 情况 | 裁决 |
|------|------|
| 多人找到 + 未被推翻 | **确认**为 bug |
| 被推翻 + 推翻理由充分 | **排除**（非 bug） |
| 推翻理由不充分 / 双方各执一词 | Leader **亲自读代码**判断 |
| 单人独有 + 未被环形对手审到 | Leader **验证**后决定 |

生成最终 bug 清单：

```markdown
## 对抗赛裁决结果

### 确认的 bug

| # | 文件路径 | 问题描述 | 严重程度 | 来源 | 裁决理由 |
|---|---------|---------|---------|------|---------|
| 1 | <path> | <desc> | 致命/中影响/低影响 | duel-1, duel-2 | 多人发现且未被推翻 |

### 排除的条目

| # | 原始描述 | 排除理由 |
|---|---------|---------|
| 1 | <desc> | 被 duel-2 推翻，理由充分：<reason> |

### Leader 亲自判定

| # | 文件路径 | 问题描述 | 判定结果 | 判定理由 |
|---|---------|---------|---------|---------|
| 1 | <path> | <desc> | 确认/排除 | <reason> |
```

#### 7d. 修复确认的 bug

将裁决确认的 bug 整理为问题列表，分派给 Debug（普通 debug-1/2/3）或 Coder 修复：

```bash
Bash(command="nanoworker debug-1 --workspace <项目路径> '消息内容'", run_in_background=true)
```

**消息内容：**

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

### 8. Leader 代码优化

对抗赛修复完成后，Leader **亲自**阅读所有变更文件的完整内容，按自身验收检查清单（详见 Leader SKILL.md）优化代码质量。

Leader 在这个环节自己动手改——因为此时 Leader 的上下文最全，适合做全局优化和拆分。

### 9. 汇报完成（单路）

```
## Agent Apply Duel 完成

**变更：** <change-name>
**模式：** 单路 + 对抗赛审查

**Coder 产出：**
- <file1>: <变更摘要>

**对抗赛审查：**
- 参赛 agent：duel-1, duel-2, duel-3 (N=3)
- Round 1 发现：X 条 bug
- Round 2 互审：Y 条被推翻，Z 条被认同
- 裁决结果：A 条确认，B 条排除，C 条 Leader 亲自判定

**修复：** <无需修复 / 修复了 N 个 bug>

**Leader 优化：** <优化摘要 / 无需优化>

下一步：运行 `/opsx:agent-verify` 进行 Leader 验收。
```

**不要自动进入验收。** 让用户决定何时验收。

---

## 并行模式（并行度 > 1）

### P1. 残留 worktree 检测

```bash
git worktree list
# 如果存在 .worktrees/ 下的 worktree，提醒用户是否清理
```

### P2. 功能块拆分

将 tasks 按功能块拆分为 coder_parallelism 组：
- 同一功能块/模块的 tasks 必须在同一组
- 不同组之间的文件修改范围尽量不交叉
- **公共文件**（路由注册、配置文件、index 导出等所有组都要碰的文件）标记为"Leader 后处理"，不分给任何 Coder

### P3. 创建 Worktree

```bash
git worktree add .worktrees/<change-name>-1 -b parallel/<change-name>-1
git worktree add .worktrees/<change-name>-2 -b parallel/<change-name>-2
# ...按 coder_parallelism 创建
```

### P4. 并行分派 Coder

从 Agent Registry 取前 coder_parallelism 个 Coder agent，每个分配一个 worktree：

- 消息中 **项目路径替换为 worktree 路径**（Coder 无需知道 worktree 存在）
- 消息中 **只包含该组的 tasks**（而非全部 tasks）
- 全部以 `run_in_background=true` **同时发出**

消息内容同单路模式步骤 5 的 Coder 消息模板，项目路径换为 worktree 路径。

### P5. 等待所有 Coder 完成

**必须等全部完成后才进入下一步**，禁止部分完成就开始。

### P6. 合并 Worktree

**先合并再做对抗赛。**

1. 逐个 `git merge parallel/<change-name>-N`
2. 有冲突 → Leader 读取冲突文件，理解两边意图，解决后 commit
3. 检查公共文件（路由注册、index 导出、配置等），缺失的由 Leader 补上
4. 清理：`git worktree remove .worktrees/<change-name>-N` + `git branch -d parallel/<change-name>-N`

### P7. Duel Debug 对抗赛审查

在合并后的主分支上执行对抗赛。流程与单路模式步骤 7 完全一致：

1. Round 1：并行找 bug（7a）
2. Round 2：环形互审（7b）
3. Leader 裁决（7c）
4. 修复确认的 bug（7d）

### P8. Leader 代码优化

对抗赛修复完成后，Leader **亲自**阅读所有变更文件的完整内容，按自身验收检查清单（详见 Leader SKILL.md）优化代码质量。

合并后 Leader 是唯一看到全貌的人，适合做跨模块优化、文件拆分等全局性改进。

### P9. 汇报完成（并行）

```
## Agent Apply Duel 完成

**变更：** <change-name>
**模式：** 并行（N 路）+ 对抗赛审查

**各 worktree 产出：**
- worktree-1（Coder: <name>）: <文件清单摘要>
- worktree-2（Coder: <name>）: <文件清单摘要>

**合并结果：** <无冲突 / 解决了 N 个冲突>

**对抗赛审查：**
- 参赛 agent：duel-1, duel-2, duel-3 (N=3)
- 裁决结果：A 条确认，B 条排除

**修复：** <无需修复 / 修复了 N 个 bug>

**Leader 优化：** <优化摘要 / 无需优化>

下一步：运行 `/opsx:agent-verify` 进行 Leader 验收。
```

**不要自动进入验收。**

---

## 原则

- **所有通信经过 Leader** — Coder 和 Duel Debug 不直接通信
- **异步调用** — Coder 和 Duel Debug 都用 `run_in_background=true`
- **Round 1 和 Round 2 必须是不同的会话** — 新 nanoworker 调用
- **Round 2 只转交结论** — 禁止泄露推理过程
- **Leader 裁决时遇争议必须亲自读代码** — 不能只看双方论据
- **评分是 prompt 激励** — 不实现真实计分后端
- **不要自动验收** — 完成后停下，等用户决定
