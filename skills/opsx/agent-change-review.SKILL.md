---
name: openspec-agent-change-review
description: 多 agent 协作审查 change 产出物。Leader 与 Coder 并行审查（全局视角 + 实现视角），各自可直接修改 change 产出物，Leader 合并后汇总判断。在 agent-apply 之前使用。
---

> **CRITICAL: 本技能中所有 Coder 调用必须用 Bash 工具执行 `nanoworker` CLI 命令。绝对禁止使用 Agent tool 创建子 agent。Agent tool 会启动 Claude Code 子进程（Sonnet），而不是 nanoworker worker。正确做法：`Bash(command="nanoworker coder-1 --workspace <path> '<msg>'", run_in_background=true)`**

# Agent Change Review（Leader + Coder 并行审查 Change）

在 Generate Change（`/opsx:ff` 或 `/opsx:new` → `/opsx:continue`）之后、`/opsx:agent-apply` 之前使用。
审查 change 产出物本身是否能安全进入实现阶段。

**核心原则：代码驱动审查。** 不能只看文档，必须独立探索项目代码，以代码现状为基准评判 change。

---

## 步骤

### 1. 选择变更

如果提供了名称，使用它。否则：
- 如果用户提到了某个变更，从对话上下文中推断
- 如果只存在一个活动变更，自动选择
- 如果不明确，运行 `openspec-cn list --json` 获取可用变更，让用户选择

### 2. 前置检查：AI-CONTEXT.md

检查目标项目根目录是否存在 AI-CONTEXT.md：

- **存在** → 跳过，进入下一步
- **不存在，但有 CLAUDE.md** → 读取 CLAUDE.md，提取项目信息（项目简介、技术栈、目录结构、架构概要、约定、注意事项），按 `templates/AI-CONTEXT.md` 格式填入，写到项目根目录
- **两者都不存在** → 提醒用户项目缺少背景信息，询问是否手动创建后再继续

### 3. 读取 change 产出物

```bash
openspec-cn instructions apply --change "<name>" --json
```

阅读 contextFiles 中列出的所有文件：

- `proposal.md` — 做什么、为什么
- `design.md` — 怎么做的决策
- `specs/` — 验收标准
- `tasks.md` — 具体任务清单

### 4. Leader 前置判断

Leader 先快速判断本次 change 的特征，决定审查策略：

- **change 规模**：小改动 / 中等特性 / 大范围重构
- **风险等级**：低风险 / 中风险 / 高风险
- **涉及模块**：单模块 / 跨模块

> 这一步的目的不是替 Coder 做判断，而是让 Leader 自己心里有数。Coder 的审查是独立的，不受 Leader 前置判断影响。

### 5. 并行审查

Leader 和 Coder **同时**审查 change，各自独立，互不影响。

#### 5a. 创建 Coder 审查用 worktree

```bash
git worktree add .worktrees/<change-name>-review -b review/<change-name>
```

#### 5b. 分派 Coder 审查

用 Bash 工具执行 nanoworker CLI，从 Agent Registry 取 Coder 调用命令：

```bash
Bash(command="nanoworker coder-1 --workspace <worktree-path> '消息内容'", run_in_background=true)
```

**消息内容：**

```
请审查以下 change 产出物，从实现者视角评估是否能安全进入实现。

项目：<worktree-path>
Change：openspec/changes/<change-name>/

请先读取：
1. AI-CONTEXT.md（项目背景）
2. change 产出物（proposal、design、specs、tasks）
3. change 涉及的现有代码（按 spec 涉及的模块自行探索）

审查重点：
- 实现可行性：技术方案在当前代码基础上是否可行
- 任务粒度：tasks 的拆分是否合理，是否遗漏步骤
- 隐性依赖：是否有未提及但实现时必须处理的依赖
- 边界条件：spec 是否覆盖了异常流程和边界情况
- 代码对齐：spec 引用的接口、类型、模块是否真实存在，是否与现有模式一致
- 术语一致：用词是否与项目现有代码一致

发现问题时：
- 如果是 change 文档本身的问题（歧义、遗漏、不合理），直接修改对应文件
- 修改后说明：改了什么、为什么改

完成后汇报：
1. 整体判断：可以进入实现 / 需要修改 / 有阻塞问题
2. 发现的问题清单（每条包含：位置、问题、影响、建议或已修改内容）
3. 你做了哪些修改
```

#### 5c. Leader 同步审查（前台）

Leader 同时执行自己的审查，不等 Coder。

**Leader 探索项目代码：** 按 change 涉及的模块，读取相关代码理解现状。

**Leader 审查检查清单（按优先级）：**

**CRITICAL — 完整性**
- 需求是否覆盖所有场景（正常流 + 异常流）？
- 错误处理和边界条件是否有对应需求？
- 并发和竞态场景是否被考虑？

**HIGH — 一致性**
- proposal 范围与 specs 需求列表是否对齐？
- design 的技术决策是否满足 specs 中的所有需求？
- tasks 是否覆盖 specs 和 design 中的所有要求？
- 术语使用是否一致（同一概念是否用了不同名称）？

**HIGH — 代码对齐**
- spec 提出的模式是否与项目现有架构一致？
- 项目中是否已有可复用的组件/工具？spec 是否利用了它们？
- spec 涉及的修改影响面是否被完整识别？
- spec 中引用的接口、类型、模块是否真实存在？

**HIGH — 清晰度**
- 每条需求是否可验证（有明确的通过/失败标准）？
- 是否存在模糊用语（"适当的"、"合理的"、"尽可能"）？
- 接口契约（输入/输出/错误）是否明确定义？

**MEDIUM — 可行性**
- 技术方案在当前代码基础上是否可行？
- 是否有更简单的实现路径被忽略？
- 复杂度评估是否合理？是否有过度工程化？

**MEDIUM — 范围**
- 变更边界是否清晰？是否有范围蔓延？
- 是否有需求超出 proposal 定义的范围？

**LOW — 可维护性**
- 设计是否过度工程化？
- 是否为未来扩展留了合理空间（但不过度设计）？

**跨产出物对齐检查：**
- proposal 定义的 capabilities 是否都有对应 specs
- specs 中的需求是否都在 design 中有技术方案
- design 中的决策是否都在 tasks 中有实现步骤
- tasks 是否有"孤立任务"（无法追溯到 specs 中的需求）

**Leader 发现问题时：** 直接修改 change 产出物，记录改了什么、为什么改。

### 6. 合并与汇总

等待 Coder 完成后：

#### 6a. 合并 Coder 的修改

```bash
git merge review/<change-name>
```

- **无冲突** → 直接合并
- **有冲突** → Leader 读取冲突文件，理解双方意图，取舍后解决

#### 6b. 清理 worktree

```bash
git worktree remove .worktrees/<change-name>-review
git branch -d review/<change-name>
```

#### 6c. 综合判断

Leader 综合自己的审查结果和 Coder 的审查报告：

- **Coder 和 Leader 都发现的问题** → 可信度最高，优先处理
- **仅 Coder 发现的问题** → Leader 验证后决定是否采纳（批判性评估，把 Coder 当同事不当权威）
- **仅 Leader 发现的问题** → 已在步骤 5c 中处理
- **Coder 做的修改 Leader 不认同** → Leader 可以回退或再改

### 7. 汇报完成

```
## Agent Change Review 完成

**变更：** <change-name>

**审查参与：** Leader + Coder（并行）

**Leader 审查：**
- 修改了 N 处 change 产出物
- 关键修改：<摘要>

**Coder 审查：**
- 整体判断：<可以进入实现 / 需要修改 / 有阻塞问题>
- 发现 N 个问题
- 修改了 M 处 change 产出物

**合并结果：** <无冲突 / 解决了 N 个冲突>

**综合判断：** <可以进入 agent-apply / 建议用户先看看>

**被修改的文件：**
- <file1>: <修改摘要>
- <file2>: <修改摘要>

下一步：确认 change 无误后，运行 `/opsx:agent-apply` 进入实现。
```

**不要自动进入 agent-apply。** 让用户决定何时进入实现。

---

## 原则

- **代码驱动** — 审 change 时必须探索项目代码现状，不能只看文档
- **并行独立** — Leader 和 Coder 各自独立审查，互不影响
- **都能动手改** — 发现问题直接改 change 产出物，不只是报告
- **Leader 最终合并** — Coder 的修改经 Leader 合并取舍，最终解释权在 Leader
- **批判性评估** — 对 Coder 的输出做独立判断，不盲信
- **结构化问题** — 每个问题包含：位置、问题、影响、建议
- **不要自动进入实现** — 完成后停下，等用户决定
