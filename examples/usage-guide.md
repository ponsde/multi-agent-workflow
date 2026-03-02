# 使用指南

> 如何搭建这套多 agent 协作环境。

## 前提条件

- [Claude Code](https://docs.anthropic.com/en/docs/claude-code) 已安装（作为 Leader 平台）
- [OpenClaw](https://github.com/nicobailon/openclaw) 已安装并初始化
- OpenClaw 中已注册 coder、debug、tester 三个 agent

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

根据实际需求修改这些文件，然后部署到各 agent 的 workspace。

## 第二步：部署 Leader 技能到 Claude Code

Claude Code 通过 `~/.claude/skills/` 目录加载技能：

```bash
# 编排技能（核心，包含 Agent Registry 和消息模板）
mkdir -p ~/.claude/skills/orchestration
cp leader-orchestration.md ~/.claude/skills/orchestration/SKILL.md

# agent-apply 流程
mkdir -p ~/.claude/skills/agent-apply
cp leader-agent-apply.md ~/.claude/skills/agent-apply/SKILL.md

# agent-verify 流程
mkdir -p ~/.claude/skills/agent-verify
cp leader-agent-verify.md ~/.claude/skills/agent-verify/SKILL.md
```

可选：注册为 Claude Code 的 slash command，方便触发：

```bash
# /agent-apply 命令
mkdir -p ~/.claude/commands
cat > ~/.claude/commands/agent-apply.md << 'EOF'
---
description: 多 agent 委派模式实现变更（Coder 实现 + Debug 审查）
---

$ARGUMENTS
EOF

# /agent-verify 命令
cat > ~/.claude/commands/agent-verify.md << 'EOF'
---
description: Leader 验收 + 路由（缺功能→Coder，bug→Debug，通过→Tester）
---

$ARGUMENTS
EOF
```

## 第三步：部署外部 agent 技能到 OpenClaw

OpenClaw agent 需要两种部署方式：

1. **BOOTSTRAP.md**：注入到 agent 的 system prompt（需去掉 YAML frontmatter）
2. **skills/ 目录**：保留 frontmatter，作为可加载的技能

```bash
# ---- Coder ----
# BOOTSTRAP.md（去掉 frontmatter）
awk 'BEGIN{c=0} /^---$/{c++;next} c>=2{print}' coder-skill.md \
  > ~/.openclaw/workspace/BOOTSTRAP.md

# skills/（保留 frontmatter）
mkdir -p ~/.openclaw/workspace/skills/coder
cp coder-skill.md ~/.openclaw/workspace/skills/coder/SKILL.md

# ---- Debug ----
awk 'BEGIN{c=0} /^---$/{c++;next} c>=2{print}' debug-skill.md \
  > ~/.openclaw/workspace-codex/BOOTSTRAP.md

mkdir -p ~/.openclaw/workspace-codex/skills/debug-engineer
cp debug-skill.md ~/.openclaw/workspace-codex/skills/debug-engineer/SKILL.md

# ---- Tester ----
awk 'BEGIN{c=0} /^---$/{c++;next} c>=2{print}' tester-skill.md \
  > ~/.openclaw/workspace-tester/BOOTSTRAP.md

mkdir -p ~/.openclaw/workspace-tester/skills/testing-engineer
cp tester-skill.md ~/.openclaw/workspace-tester/skills/testing-engineer/SKILL.md
```

> **注意**：OpenClaw 的 workspace 路径因配置而异，按你的实际路径替换。

### OpenClaw SKILL.md frontmatter 格式

```yaml
---
name: skill-name              # 必填，小写字母+连字符
description: 技能的一句话描述    # 必填
metadata:
  openclaw:
    always: true               # 始终包含在可用 skills 列表
---
```

## 第四步：部署全局规则

Claude Code 的 skills 只在触发时加载，rules 每次会话都加载。把多 agent 基本信息写进 rules，确保 agent 随时知道 AI-CONTEXT.md 等概念。

```bash
mkdir -p ~/.claude/rules/common
cp multi-agent-rule.md ~/.claude/rules/common/multi-agent.md
```

> 如果已有 `multi-agent.md`，把 AI-CONTEXT.md 部分追加进去即可。
> 详见 [multi-agent-rule.md](multi-agent-rule.md)。

## 第五步：为项目准备 AI-CONTEXT.md

在你的项目根目录创建 `AI-CONTEXT.md`，填入项目背景信息。模板见 [ai-context-template.md](ai-context-template.md)。

如果项目已有 Claude Code 生成的 `CLAUDE.md`，Leader 会在 agent-apply 开始前自动从中生成 AI-CONTEXT.md，无需手动创建。

## 第六步：验证部署

```bash
# 验证 Coder 能看到技能
openclaw agent --agent coder -m "你能看到 Coder 相关的技能吗？回答是或否" --json --timeout 120

# 验证 Debug 能看到技能
openclaw agent --agent debug -m "你能看到 debug-engineer 相关的技能吗？回答是或否" --json --timeout 120

# 验证 Tester 能看到技能
openclaw agent --agent tester -m "你能看到 4 层测试框架吗？回答是或否" --json --timeout 120
```

## 第七步：开始使用

在 Claude Code 中：

```
# 触发 agent-apply（Coder 实现 + Debug 审查）
/agent-apply <change-name>

# Coder+Debug 完成后，触发 agent-verify（Leader 验收 + 路由）
/agent-verify <change-name>
```

Leader 会按照编排技能中的流程自动执行：分派 Coder → 中转 Debug → 处理讨论 → 验收 → 路由。

---

## 自定义和扩展

### 调整 Agent Registry

编辑 `leader-orchestration.md` 中的 Agent Registry 表，修改角色名称、调用命令等。如果你用的不是 OpenClaw，替换对应的调用命令即可。

### 调整讨论轮次

默认 3 轮。如果觉得太少或太多，修改 `leader-orchestration.md` 和 `leader-agent-apply.md` 中的"3 轮"相关描述。

### 添加新角色

1. 写一份新的 SKILL.md（参考现有角色）
2. 在 Leader 的 Agent Registry 中注册
3. 在 Leader 的消息模板中添加分派模板
4. 部署到对应 agent 的 workspace

### 替换外部 agent 平台

这套工作流不绑定 OpenClaw。只要外部 agent 能：
- 读写项目文件
- 接收文本消息并返回结果
- 支持异步调用

就可以替换。修改 Agent Registry 中的调用命令即可。
