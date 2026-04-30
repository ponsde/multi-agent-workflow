# AI-CONTEXT.md 模板

> 可选的项目背景文件。新流程优先使用 Task Packet；只有当多个 worker 需要复用同一份稳定项目背景时，才需要 AI-CONTEXT.md。

```markdown
# AI Context

## 项目简介

<!-- 一两句话说明这个项目是什么、做什么 -->

## 技术栈

<!-- 语言、框架、关键依赖 -->

## 目录结构

<!-- 核心目录说明 -->

project/
├── src/          ← 源码
├── tests/        ← 测试
└── ...

## 架构概要

<!-- 核心模块关系，可用 ASCII 图 -->

## 约定

<!-- 命名、代码风格、测试方式等 -->

## 注意事项

<!-- 踩过的坑、不能动的东西、特殊限制 -->
```

## 使用方式

| 情况 | 建议 |
|------|------|
| Task Packet 已包含足够上下文 | 不需要 AI-CONTEXT.md |
| 多个 worker 会反复用到同一项目背景 | 创建 AI-CONTEXT.md，并在 Task Packet 中显式引用 |
| 使用 worktree 或打包上下文 | 确保文件可见，或把关键内容直接写入 Task Packet |
| 项目已有 CLAUDE.md、AGENTS.md 等说明 | 可从这些文件提炼 AI-CONTEXT.md |

## 注意

- Worker 不应默认第一步读取 AI-CONTEXT.md。
- 被 `.gitignore` 忽略的 AI-CONTEXT.md 不一定能进入 worktree 或打包上下文。
- 关键需求、验收标准、错误日志优先写入 Task Packet。
