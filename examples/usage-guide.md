# 使用指南

> 如何搭建这套多 agent 协作环境。

## 前提条件

- [Claude Code](https://docs.anthropic.com/en/docs/claude-code) 已安装（作为 Leader 平台）
- Python 3.12+（用于 nanoworker）
- nanoworker 已安装（详见 [nanoworker-setup.md](nanoworker-setup.md)）

## 第一步：准备角色技能文件

每个角色需要一份 SKILL.md，定义其职责、工作流、汇报格式。本仓库的 examples 目录提供了完整示例：

| 文件 | 角色 | 说明 |
|------|------|------|
| `leader-orchestration.md` | Leader | 编排技能：Agent Registry、消息模板、核心规则 |
| `leader-agent-apply.md` | Leader | agent-apply 流程：Coder 实现 + Debug 审查 |
| `leader-agent-verify.md` | Leader | agent-verify 流程：验收 + 路由 |
| `coder-skill.md` | Coder | 接收任务、自主实现、汇报 |
| `debug-skill.md` | Debug | 3 层审查框架、3 种工作场景 |
| `tester-skill.md` | Tester | 4 层测试框架、bug 报告格式 |

根据实际需求修改这些文件，然后部署。

## 第二步：安装和配置 nanoworker

详见 [nanoworker-setup.md](nanoworker-setup.md)。

简要步骤：

```bash
# 安装
pipx install /path/to/nanoworker/

# 配置 ~/.nanoworker/config.json
# 设置 OpenAI-compatible API 端点和 worker 定义
```

## 第三步：部署 Leader 技能到 Claude Code

Claude Code 通过 `~/.claude/skills/` 目录加载技能：

```bash
# 编排技能（核心，包含 Agent Registry 和消息模板）
mkdir -p ~/.claude/skills/orchestration
cp leader-orchestration.md ~/.claude/skills/orchestration/SKILL.md

# agent-apply 流程
mkdir -p ~/.claude/skills/openspec-agent-apply
cp leader-agent-apply.md ~/.claude/skills/openspec-agent-apply/SKILL.md

# agent-verify 流程
mkdir -p ~/.claude/skills/openspec-agent-verify
cp leader-agent-verify.md ~/.claude/skills/openspec-agent-verify/SKILL.md
```

可选：注册为 Claude Code 的 slash command，方便触发：

```bash
mkdir -p ~/.claude/commands/opsx

# /opsx:agent-apply 命令
cat > ~/.claude/commands/opsx/agent-apply.md << 'EOF'
---
description: 多 agent 委派模式实现变更（Coder 实现 + Debug 审查）
---

$ARGUMENTS
EOF

# /opsx:agent-verify 命令
cat > ~/.claude/commands/opsx/agent-verify.md << 'EOF'
---
description: Leader 验收 + 路由（缺功能→Coder，bug→Debug，通过→Tester）
---

$ARGUMENTS
EOF
```

## 第四步：部署 Worker 技能

nanoworker 从 skills 目录加载角色 SKILL.md：

```bash
# 在 nanoworker 项目目录下
mkdir -p skills/coder skills/debug-engineer skills/testing-engineer

cp coder-skill.md skills/coder/SKILL.md
cp debug-skill.md skills/debug-engineer/SKILL.md
cp tester-skill.md skills/testing-engineer/SKILL.md
```

## 第五步：部署全局规则

Claude Code 的 skills 只在触发时加载，rules 每次会话都加载。把多 agent 基本信息写进 rules：

```bash
mkdir -p ~/.claude/rules/common
cp multi-agent-rule.md ~/.claude/rules/common/multi-agent.md
```

> 详见 [multi-agent-rule.md](multi-agent-rule.md)。

## 第六步：为项目准备 AI-CONTEXT.md

在你的项目根目录创建 `AI-CONTEXT.md`，填入项目背景信息。模板见 [ai-context-template.md](ai-context-template.md)。

如果项目已有 `CLAUDE.md`，Leader 会在 agent-apply 开始前自动从中生成 AI-CONTEXT.md，无需手动创建。

## 第七步：验证部署

```bash
# 验证 nanoworker 可用
nanoworker --help

# 验证各角色能响应
nanoworker coder-1 --workspace /tmp "回答：你是什么角色？"
nanoworker debug-1 --workspace /tmp "回答：你是什么角色？"
nanoworker tester --workspace /tmp "回答：你是什么角色？"
```

## 第八步：开始使用

在 Claude Code 中：

```
# 触发 agent-apply（Coder 实现 + Debug 审查）
/opsx:agent-apply <change-name>

# Coder+Debug 完成后，触发 agent-verify（Leader 验收 + 路由）
/opsx:agent-verify <change-name>
```

Leader 会按照编排技能中的流程自动执行：分派 Coder → 中转 Debug → 处理讨论 → 验收 → 路由。

---

## 自定义和扩展

### 调整 Agent Registry

编辑 `leader-orchestration.md` 中的 Agent Registry 表，修改角色名称、调用命令等。

### 调整 Worker 数量

修改 `~/.nanoworker/config.json` 中的 workers 定义。Leader 的 Agent Registry 需同步更新。

### 调整讨论轮次

默认 3 轮。修改 `leader-orchestration.md` 和 `leader-agent-apply.md` 中的"3 轮"相关描述。

### 添加新角色

1. 写一份新的 SKILL.md（参考现有角色）
2. 在 nanoworker config 中注册 worker
3. 在 Leader 的 Agent Registry 中注册
4. 在 Leader 的消息模板中添加分派模板

### 替换 Worker 平台

这套工作流不绑定 nanoworker。只要外部 agent 能：
- 读写项目文件
- 接收文本消息并返回 JSON 结果
- 支持异步调用

就可以替换。修改 Agent Registry 中的调用命令即可。
