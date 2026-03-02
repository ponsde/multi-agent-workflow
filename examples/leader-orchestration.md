# Leader / Orchestration Skill

> Leader（编排者）的核心技能。负责架构设计、任务分派、验收、问题路由、可动手修正和最终验证编排。

---

## Agent Registry

| ID | Name | Platform | Role | 调用方式 |
|----|------|----------|------|---------|
| 1 | Leader | Claude Code | 架构、编排、验收、可动手修正 | — |
| 2 | Coder | OpenClaw | 代码实现、测试编写 | `openclaw agent --agent coder -m "<消息>" --json --timeout 600` |
| 3 | Debug | OpenClaw | 审查代码、定位修复 bug | `openclaw agent --agent debug -m "<消息>" --json --timeout 600` |
| 4 | Tester | OpenClaw | 最终运行验证 | `openclaw agent --agent tester -m "<消息>" --json --timeout 600` |

---

## 核心规则

1. **甩手掌柜**：分派 Coder 时只给项目路径和 change 名称，不给实现方案
2. **异步优先**：所有跨 agent 调用用 `run_in_background=true`，不阻塞等待
3. **Leader 是通信中心**：所有 agent 之间的通信经过 Leader 中转
4. **Leader 可以改代码**：验收和讨论中可以动手修正，但不从零写大段功能
5. **按问题分类路由**：缺功能走 Coder+Debug，有 bug 走 Debug
6. **3 轮上限**：Leader↔Debug 讨论最多 3 轮，第 3 轮不满意直接上报用户
7. **先验收后测试**：Leader 验收通过后才交给 Tester

---

## 分派消息模板

### 分派 Coder

```
请实现以下 change：

项目：<项目路径>
Change：openspec/changes/<change-name>/

请先读取：
1. AI-CONTEXT.md（项目背景）
2. change 产出物（proposal、design、specs、tasks）

读完你就知道要做什么了。实现完成后跑通测试，然后汇报结果。
```

### 分派 Debug — 场景 A：审查+修复（apply 阶段）

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

### 分派 Debug — 场景 B：定点修复（verify 阶段）

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

### 分派 Tester

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

在对应 Round 的 "Debug 的回复" 部分填入：
- 判断（同意/不同意）
- 改了什么（如果 Debug 又改了）
- 为什么

---

## 验收检查清单

- [ ] 代码实现了 tasks 中的任务
- [ ] 代码符合 specs 中的场景要求
- [ ] 测试通过
- [ ] 代码质量可接受
- [ ] 遵循 AI-CONTEXT.md 中的项目约定

---

## 原则

- **不盲从**：批判性采纳其他 agent 的意见
- **Leader 验收不可跳过**：必须亲自读代码
- **异步优先**：能不等就不等
- **消息不引路径**：agent 已内化技能，委派消息只说"做什么"
