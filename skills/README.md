# Agent Role Templates

多 agent 协作的角色模板。四个角色各有自包含的 SKILL.md，可部署到对应 agent。

## 目录结构

```
agent-roles/
├── opsx/
│   ├── agent-change-review.SKILL.md  # agent-change-review 技能：Leader+Coder 并行审查 change（部署到 Claude Code）
│   ├── agent-apply.SKILL.md          # agent-apply 技能：Coder 实现 + Debug 审查（部署到 Claude Code）
│   ├── agent-apply-duel.SKILL.md     # agent-apply-duel 技能：Debug 对抗赛编排（部署到 Claude Code）
│   └── agent-verify.SKILL.md         # agent-verify 技能：Leader 验收 + 路由（部署到 Claude Code）
├── leader/
│   └── SKILL.md               # 编排技能（部署到 Claude Code）
├── coder/
│   └── SKILL.md               # Coder 技能（nanoworker coder 角色）
├── debug/
│   └── SKILL.md               # Debug 技能（nanoworker debug 角色，agent-apply 用）
├── debug-duel/
│   └── SKILL.md               # Debug 对抗赛技能（nanoworker debug-duel 角色，agent-apply-duel 用）
├── tester/
│   └── SKILL.md               # Tester 技能（nanoworker tester 角色）
├── rules/
│   └── multi-agent.md         # 全局规则（部署到 ~/.claude/rules/common/）
templates/
├── AI-CONTEXT.md              # 项目级共享上下文模板
└── CLAUDE.md                  # Claude Code 项目配置模板
```

## 角色说明

| 角色 | 职责 | 不做什么 |
|------|------|---------|
| Leader (江江) | 架构设计、任务编排（OpenSpec）、验收、可动手修正、通信中心 | 从零写大段基础功能 |
| Coder | 读 change 产出物、自主实现代码+测试、交付 | 架构决策、跨模块判断 |
| Debug | 审查代码、定位修复 bug、参与 Leader↔Debug 讨论 | 从零写功能、运行测试 |
| Debug (Duel) | 对抗赛模式：独立找 bug（Round 1）、审查对手清单（Round 2） | 修复 bug、架构决策、运行测试 |
| Tester | 最终运行验证（Leader 验收通过后） | 写功能代码、直接修 bug |

## 部署

### 前提

- Claude Code 已安装
- nanoworker 已安装（`pip install` 或 `pipx install`）
- `~/.nanoworker/config.json` 已配置（providers + workers）

### 步骤一：配置 nanoworker

`~/.nanoworker/config.json`：

```json
{
  "providers": {
    "openai": {
      "api_key": "sk-...",
      "api_base": "https://your-openai-compatible-endpoint/v1"
    }
  },
  "workers": {
    "coder-1": { "role": "coder", "model": "openai/gpt-5.3-codex", "skills": ["coder"], "max_iterations": 30 },
    "coder-2": { "role": "coder", "model": "openai/gpt-5.3-codex", "skills": ["coder"], "max_iterations": 30 },
    "coder-3": { "role": "coder", "model": "openai/gpt-5.3-codex", "skills": ["coder"], "max_iterations": 30 },
    "debug-1": { "role": "debug", "model": "openai/gpt-5.3-codex", "skills": ["debug-engineer"], "max_iterations": 30 },
    "debug-2": { "role": "debug", "model": "openai/gpt-5.3-codex", "skills": ["debug-engineer"], "max_iterations": 30 },
    "debug-3": { "role": "debug", "model": "openai/gpt-5.3-codex", "skills": ["debug-engineer"], "max_iterations": 30 },
    "tester":  { "role": "tester", "model": "openai/gpt-5.3-codex", "skills": ["testing-engineer"], "max_iterations": 30 }
  }
}
```

Worker 数量可按需调整。Leader 的 Agent Registry 从此配置动态读取。

### 步骤二：部署 Leader 技能到 Claude Code

```bash
# 编排技能
mkdir -p ~/.claude/skills/orchestration
cp agent-roles/leader/SKILL.md ~/.claude/skills/orchestration/SKILL.md

# Agent Apply（Coder 实现 + Debug 审查）
mkdir -p ~/.claude/skills/openspec-agent-apply
cp agent-roles/leader/agent-apply.SKILL.md ~/.claude/skills/openspec-agent-apply/SKILL.md

# 注册 /opsx:agent-apply 命令
cat > ~/.claude/commands/opsx/agent-apply.md << 'CMDEOF'
---
name: "OPSX: Agent Apply"
description: 多 agent 委派模式实现变更（Coder 实现 + Debug 审查，完成后提示运行 agent-verify）
category: 工作流
tags: [workflow, multi-agent, delegation]
---

$ARGUMENTS
CMDEOF

# Agent Change Review（Leader + Coder 并行审查 change，在 agent-apply 之前使用）
mkdir -p ~/.claude/skills/openspec-agent-change-review
cp agent-roles/opsx/agent-change-review.SKILL.md ~/.claude/skills/openspec-agent-change-review/SKILL.md

# 注册 /opsx:agent-change-review 命令
cat > ~/.claude/commands/opsx/agent-change-review.md << 'CMDEOF'
---
name: "OPSX: Agent Change Review"
description: Leader + Coder 并行审查 change 产出物（全局视角 + 实现视角），在 agent-apply 之前使用
category: 工作流
tags: [workflow, multi-agent, review]
---

$ARGUMENTS
CMDEOF

# Agent Apply Duel（Debug 对抗赛编排，agent-apply 的 Debug 审查替代方案）
mkdir -p ~/.claude/skills/openspec-agent-apply-duel
cp agent-roles/opsx/agent-apply-duel.SKILL.md ~/.claude/skills/openspec-agent-apply-duel/SKILL.md

# 注册 /opsx:agent-apply-duel 命令
cat > ~/.claude/commands/opsx/agent-apply-duel.md << 'CMDEOF'
---
name: "OPSX: Agent Apply Duel"
description: agent-apply 的对抗赛变体（Coder 实现 + N 个 Debug agent 环形互审 + Leader 裁决）
category: 工作流
tags: [workflow, multi-agent, duel]
---

$ARGUMENTS
CMDEOF

# Agent Verify（Leader 验收 + 路由）
mkdir -p ~/.claude/skills/openspec-agent-verify
cp agent-roles/leader/agent-verify.SKILL.md ~/.claude/skills/openspec-agent-verify/SKILL.md

# 注册 /opsx:agent-verify 命令
cat > ~/.claude/commands/opsx/agent-verify.md << 'CMDEOF'
---
name: "OPSX: Agent Verify"
description: Leader 验收 Coder 交付，按问题类型路由（缺功能→Coder，bug→Debug，通过→Tester）
category: 工作流
tags: [workflow, multi-agent, verification]
---

$ARGUMENTS
CMDEOF
```

### 步骤三：部署 Worker 技能

nanoworker 的 skills 目录默认在 `new_bot/skills/`：

```bash
# 确保 skills 目录存在
mkdir -p new_bot/skills/coder new_bot/skills/debug-engineer new_bot/skills/debug-duel new_bot/skills/testing-engineer

# 部署角色 SKILL.md
cp agent-roles/coder/SKILL.md new_bot/skills/coder/SKILL.md
cp agent-roles/debug/SKILL.md new_bot/skills/debug-engineer/SKILL.md
cp agent-roles/debug-duel/SKILL.md new_bot/skills/debug-duel/SKILL.md
cp agent-roles/tester/SKILL.md new_bot/skills/testing-engineer/SKILL.md
```

### 步骤四：部署全局规则

```bash
mkdir -p ~/.claude/rules/common
cp agent-roles/rules/multi-agent.md ~/.claude/rules/common/multi-agent.md
```

### 步骤五：为项目配置共享上下文

```bash
# 在项目根目录创建 AI-CONTEXT.md
cp templates/AI-CONTEXT.md <项目路径>/AI-CONTEXT.md
# 编辑填入项目信息

# 创建或更新 CLAUDE.md
cp templates/CLAUDE.md <项目路径>/CLAUDE.md
```

### 验证

```bash
# 验证 nanoworker 可用
nanoworker --help

# 验证 Coder 能响应
nanoworker coder-1 --workspace /tmp/test "回答：你是什么角色？"

# 验证 Debug 能响应
nanoworker debug-1 --workspace /tmp/test "回答：你是什么角色？"

# 验证 Tester 能响应
nanoworker tester --workspace /tmp/test "回答：你是什么角色？"
```
