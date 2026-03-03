---
name: openspec-agent-apply
description: 多 agent 委派模式 apply。Coder 实现 → Leader 中转 → Debug 审查+修复 → Leader↔Debug 讨论 → 完成/上报。
---

# Agent Apply（Coder 实现 + Debug 审查）

与原版 `/opsx:apply` 互补。原版由 Leader 自己实现，本技能将任务委派给 Coder，并经过 Debug 审查保障质量。

---

## 步骤

### 1. 选择变更

与原版相同：从参数、上下文或列表中确定变更名称。

### 2. 前置检查：AI-CONTEXT.md

检查目标项目根目录是否存在 AI-CONTEXT.md：

- **存在** → 跳过，进入下一步
- **不存在，但有 CLAUDE.md** → 读取 CLAUDE.md，提取项目信息（项目简介、技术栈、目录结构、架构概要、约定、注意事项），按 `templates/AI-CONTEXT.md` 格式填入，写到项目根目录
- **两者都不存在** → 提醒用户项目缺少背景信息，询问是否手动创建后再继续

### 3. 读取上下文

```bash
openspec-cn instructions apply --change "<name>" --json
```

阅读 contextFiles 中列出的文件（proposal, design, specs, tasks）。

### 4. 判断并行度

参见 orchestration SKILL.md "并行分派" 章节：

1. 从 Agent Registry 统计 Coder 角色 agent 数量 → coder_count
2. 将 tasks 按功能块拆分为组 → task_groups
3. **coder_parallelism = min(coder_count, task_groups)**
4. 如果 coder_parallelism = 1 → **单路模式**（步骤 5-9）
5. 如果 coder_parallelism > 1 → **并行模式**（步骤 P1-P8）

---

## 单路模式（并行度 = 1）

原有流程，不创建 worktree。

### 5. 分派给 Coder

使用 orchestration SKILL.md 的 Agent Registry 中 Coder 的调用命令，以 `run_in_background=true` 异步发送。

**消息内容**（参见 orchestration SKILL.md "分派 Coder" 模板）：要求先读 AI-CONTEXT.md，再读 change 产出物，然后实现并汇报。

### 6. 等待 Coder 完成

- 有其他工作：继续做，系统通知完成时再处理
- 没有其他工作：`TaskOutput(task_id, block=true)` 等待

### 7. Leader 中转给 Debug

Coder 完成后，Leader 将 Coder 的产出转交 Debug 审查。使用 Agent Registry 中 Debug 的调用命令，以 `run_in_background=true` 异步发送。

**消息内容**（参见 orchestration SKILL.md "分派 Debug — 场景 A" 模板）：给 Coder 修改的文件清单和 change 上下文，要求 Debug 先读 AI-CONTEXT.md，审查代码，发现问题直接修复，修复后汇报改了哪里、为什么改。

### 8. 等待 Debug 完成 + 处理结果

**Debug 报告无问题** → 进入步骤 9 汇报完成。

**Debug 修复了问题** → Leader 审查 Debug 的修复：
- **Leader 满意** → 进入步骤 9 汇报完成
- **Leader 不满意** → 进入 Leader↔Debug 讨论（步骤 8a）

#### 8a. Leader↔Debug 讨论（最多 3 轮）

1 轮 = Debug→Leader + Leader→Debug。

**每轮流程：**

1. Leader 修改代码
2. 将修改信息追加到 `<change>/discussion.md`（参见下方写入规则）
3. 发给 Debug 验收（参见 orchestration SKILL.md "分派 Debug — 场景 C" 模板），以 `run_in_background=true` 异步发送
4. 等待 Debug 回复
5. Leader 将 Debug 回复追加到 discussion.md
6. Leader 审查 Debug 的回复

**第 3 轮特殊处理：**

第 3 轮只有 Debug→Leader。如果 Leader 仍不满意：
- **停止讨论**，禁止继续发回 Debug
- 汇总 discussion.md 完整上下文
- **上报主人**决策

### 9. 汇报完成（单路）

```
## Agent Apply 完成

**变更：** <change-name>
**模式：** 单路

**Coder 产出：**
- <file1>: <变更摘要>

**Debug 审查：** <无问题 / 修复了 N 个问题>

**讨论轮次：** <0 / N 轮>

下一步：运行 `/opsx:agent-verify` 进行 Leader 验收。
```

**不要自动进入验收。** 让用户决定何时验收。

---

## 并行模式（并行度 > 1）

### P1. 残留 worktree 检测

参见 orchestration SKILL.md "Worktree 管理 — 残留检测"。有残留则提醒用户是否清理。

### P2. 功能块拆分

参见 orchestration SKILL.md "并行分派 — 功能块拆分规则"：

- 将 tasks 拆为 coder_parallelism 组
- 同模块 tasks 在同一组，不同组文件范围尽量不交叉
- 公共文件标记为"Leader 后处理"

### P3. 创建 Worktree

参见 orchestration SKILL.md "Worktree 管理 — 创建"：

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

### P5. 等待所有 Coder 完成

**必须等全部完成后才进入 Debug 阶段**，禁止部分完成就开始 Debug。

### P6. Debug 资源池分配

参见 orchestration SKILL.md "并行分派 — Debug 资源池分配"：

1. 从 Agent Registry 统计 Debug 角色 agent 数量 → debug_count
2. debug_parallelism = min(debug_count, coder_parallelism)
3. 将前 debug_parallelism 个 worktree 分配给可用 Debug，以 `run_in_background=true` 同时分派
4. 每个 Debug 收到对应 worktree 路径 + 该 Coder 修改的文件清单
5. 如果还有剩余 worktree 待审查 → 等最先完成的 Debug，分配下一个 worktree
6. 每个 worktree 的讨论记录在 `<worktree>/<change>/discussion-wt-<N>.md`

### P6a. 各 worktree 独立的 Leader↔Debug 讨论

每个 worktree 的 Debug 结果独立处理，流程与单路模式步骤 8 相同：

- Debug 无问题 → 该 worktree 完成
- Debug 修复了问题 → Leader 审查，满意则完成，不满意则讨论
- 讨论最多 3 轮，超过上报主人
- 讨论记录写入该 worktree 的 `discussion-wt-<N>.md`

### P7. 合并 Worktree

参见 orchestration SKILL.md "Worktree 管理 — 合并流程"：

1. 逐个 `git merge parallel/<change-name>-N`
2. 有冲突 → Leader 解决
3. 检查公共文件（路由注册、index 导出、配置等），缺失的由 Leader 补上
4. 清理 worktree 和分支

### P8. 汇报完成（并行）

```
## Agent Apply 完成

**变更：** <change-name>
**模式：** 并行（N 路）

**各 worktree 产出：**
- worktree-1（Coder: <name>, Debug: <name>）: <文件清单摘要>
- worktree-2（Coder: <name>, Debug: <name>）: <文件清单摘要>
- ...

**合并结果：** <无冲突 / 解决了 N 个冲突>
**公共文件补充：** <无 / 补充了 N 个文件>

下一步：运行 `/opsx:agent-verify` 进行 Leader 验收。
```

**不要自动进入验收。** 让用户决定何时验收。

---

## discussion.md 写入规则

讨论文件位于 `<change>/discussion.md`，记录 Leader↔Debug 每轮上下文。

### Leader 发给 Debug 时追加

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

在对应 Round 的 "Debug 的回复" 部分填入：

```markdown
### Debug 的回复
- 判断: <同意 / 不同意 Leader 的修改>
- 改了什么: <如果 Debug 又改了什么>
- 为什么: <原因>
```

---

## 原则

- **所有通信经过 Leader** — Coder 和 Debug 不直接通信
- **Debug 要动手改** — 发现问题直接修复，不只是报告
- **异步调用** — Coder 和 Debug 都用 `run_in_background=true`
- **3 轮上限** — 讨论超过 3 轮上报主人
- **不要自动验收** — 完成后停下，等用户决定
