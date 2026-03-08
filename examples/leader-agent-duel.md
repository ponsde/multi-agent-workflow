---
name: openspec-agent-duel
description: Debug 对抗赛模式。N 个 Debug agent 环形互审，Leader 裁决，提高审查准确度。
---

# Debug 对抗赛 Skill

对抗赛是现有 Debug 审查的可选替代，利用竞赛框架让多个 Debug agent 互相对抗，通过交叉过滤提高审查质量。

---

## 前置条件

- 已有一个 OpenSpec change（含 specs）
- Agent Registry 中有 >= 2 个 Debug agent

---

## 完整流程

```
选择变更
    │
    ▼
前置检查（Debug agent 数量 >= 2？AI-CONTEXT.md 存在？）
    │
    ├─ N < 2 → 提示用户退化为原有 Debug 流程，结束
    │
    ▼
Round 1：并行找 bug
    │  所有 Debug agent 同时分派（run_in_background=true）
    │  每个收到：竞赛背景 + 任务 A + spec 路径 + 项目路径
    │  不给 Coder 修改清单
    │
    ▼
收集 Round 1 清单
    │  等待所有 Debug agent 完成
    │  收集每个 agent 的结构化 bug 清单
    │
    ▼
Round 2：环形互审
    │  按环形拓扑分配：agent[i] 审 agent[(i-1) % N]
    │  每个 agent 发起新会话（新 nanoworker 调用）
    │  收到：竞赛背景 + 任务 B + 对手清单（仅结论）
    │
    ▼
收集 Round 2 对抗报告
    │  等待所有 Debug agent 完成
    │  收集每个 agent 的结构化对抗报告
    │
    ▼
Leader 裁决
    │  汇总所有清单和对抗报告
    │  按裁决分类规则逐条判定
    │  生成最终 bug 清单
    │
    ▼
修复路由
    确认的 bug 派给 Coder/Debug 修复
    复用现有修复流程
```

---

## 步骤详解

### 1. 选择变更

与 `agent-apply` 相同：从参数、上下文或 CLI 列表中确定变更名称。

### 2. 前置检查

```bash
# 检查 AI-CONTEXT.md
# 不存在则从 CLAUDE.md 生成

# 统计 Debug agent 数量
# 从 leader SKILL.md 的 Agent Registry 中按 Role=Debug 筛选
# N < 2 → 提示并退出
```

宣布参赛阵容："对抗赛启动，N 个 Debug agent 参赛：debug-1, debug-2, ..."

### 3. Round 1：并行找 bug

使用 leader SKILL.md 中的**场景 D：对抗赛 Round 1（找 bug）**消息模板。

- 对每个 Debug agent，用 `nanoworker <agent-id> --workspace <项目路径> '<消息>'` 分派
- 所有分派使用 `run_in_background=true` 并行执行
- 等待所有完成，收集每个 agent 的 bug 清单

### 4. Round 2：环形互审

使用 leader SKILL.md 中的**场景 E：对抗赛 Round 2（审对手）**消息模板。

- 按环形拓扑（参见 leader SKILL.md "环形拓扑生成"章节）确定每个 agent 审查谁的清单
- 将对手清单（仅结论，去掉推理过程）填入消息模板
- 对每个 Debug agent 发起**新的 nanoworker 调用**（新会话，禁止复用 Round 1 会话）
- 所有分派使用 `run_in_background=true` 并行执行
- 等待所有完成，收集每个 agent 的对抗报告

### 5. Leader 裁决

按 leader SKILL.md 中的**对抗赛裁决**章节执行：

- 汇总所有 Round 1 清单和 Round 2 对抗报告
- 按裁决分类规则逐条判定
- 需要 Leader 亲自判的条目：读代码验证
- 生成最终 bug 清单（裁决产出格式）

### 6. 修复路由

按 leader SKILL.md 中的**裁决后修复路由**执行：

- 将确认的 bug 整理为问题列表
- 分派给 Coder 或 Debug 修复
- 修复完成后走正常验收流程

---

## 输出格式

### 对抗赛启动

```
## Debug 对抗赛启动

**变更：** <change-name>
**参赛 Debug agent：** debug-1, debug-2, debug-3 (N=3)

### Round 1：并行找 bug
正在分派所有 Debug agent...
```

### 对抗赛完成

```
## Debug 对抗赛完成

**变更：** <change-name>
**参赛 Debug agent：** N 个

### 裁决结果摘要
- 确认的 bug：X 个
- 排除的条目：Y 个
- Leader 亲自判定：Z 个

### 确认的 bug
<最终 bug 清单>

### 下一步
确认的 bug 已派给 <agent> 修复。
```

---

## 护栏

- 对抗赛是可选模式，不替代原有 Debug 流程
- N < 2 时必须提示用户，不能勉强运行
- Round 1 和 Round 2 必须是不同的会话（新 nanoworker 调用）
- Round 2 只转交对手的结论，禁止泄露推理过程
- Leader 裁决时遇到争议条目必须亲自读代码，不能只看双方论据
- 评分是 prompt 激励手段，不实现真实计分后端
