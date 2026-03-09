# Multi-Agent Rule

> 放在 `~/.claude/rules/common/multi-agent.md`，每次 Claude Code 会话自动加载。
> 确保 agent 在任何项目中都知道多 agent 协作的基本信息。

---

```markdown
# Multi-Agent Collaboration

多 agent 协作的编排流程、Agent Registry、调用方式和核心规则，
详见编排技能：`~/.claude/skills/orchestration/SKILL.md`

## AI-CONTEXT.md

每个项目根目录应有 `AI-CONTEXT.md`，是所有 agent 的共享项目背景。

- **内容**：项目简介、技术栈、目录结构、架构概要、约定、注意事项
- **来源**：从 `CLAUDE.md` 提炼生成
- **检查时机**：agent-apply 开始前，Leader 检查是否存在，不存在则从 CLAUDE.md 生成
- **使用**：所有 agent（Coder、Debug、Tester）收到任务后第一步读 AI-CONTEXT.md
- **模板**：`~/to_be_better/templates/AI-CONTEXT.md`
```

---

## 为什么需要这个规则文件？

Claude Code 的 skills 只在触发相关技能时才加载，而 `~/.claude/rules/` 下的文件每次会话都会自动加载。

如果不把 AI-CONTEXT.md 写进 rules，agent 在没有触发 agent-apply 技能时就不知道 AI-CONTEXT.md 是什么。加了这个 rule 后，任何会话都能回答"AI-CONTEXT 是什么"。
