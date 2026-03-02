# Agent Apply（Coder 实现 + Debug 审查）

> 将任务委派给 Coder 实现，经过 Debug 审查保障质量。

---

## 步骤

### 1. 选择变更

确定要实现的变更名称。

### 2. 前置检查：AI-CONTEXT.md

检查目标项目根目录是否存在 AI-CONTEXT.md：

- **存在** → 跳过
- **不存在，但有 CLAUDE.md** → 从 CLAUDE.md 生成（提取项目简介、技术栈、目录结构、架构概要、约定、注意事项）
- **两者都不存在** → 提醒用户

### 3. 读取上下文

阅读 change 产出物（proposal, design, specs, tasks），了解任务全貌。

### 4. 异步分派 Coder

以 `run_in_background=true` 异步发送。消息要求 Coder 先读 AI-CONTEXT.md，再读 change 产出物，然后实现并汇报。

### 5. 等待 Coder 完成

有其他工作就继续做，没有就等系统通知。

### 6. Leader 中转给 Debug

Coder 完成后，以 `run_in_background=true` 异步发送给 Debug。消息给出 Coder 修改的文件清单和 change 上下文，要求 Debug 审查代码，发现问题直接修复。

### 7. 等待 Debug 完成

同步骤 5。

### 8. 处理 Debug 结果

**Debug 无问题** → 汇报完成。

**Debug 修复了问题** → Leader 审查：
- 满意 → 汇报完成
- 不满意 → 进入讨论

#### 8a. Leader↔Debug 讨论（最多 3 轮）

每轮：
1. Leader 修改代码
2. 追加到 discussion.md
3. 异步发给 Debug 验收
4. 等待 Debug 回复
5. 追加 Debug 回复到 discussion.md
6. Leader 审查

**第 3 轮特殊处理**：Leader 仍不满意 → 停止讨论 → 汇总上下文 → 上报用户。

### 9. 汇报完成

```
## Agent Apply 完成

**变更：** <change-name>
**Coder 产出：** <文件列表>
**Debug 审查：** <无问题 / 修复了 N 个问题>
**讨论轮次：** <0 / N 轮>

下一步：运行 agent-verify 进行 Leader 验收。
```

不自动进入验收，让用户决定。

---

## 原则

- **所有通信经过 Leader** — Coder 和 Debug 不直接通信
- **Debug 要动手改** — 发现问题直接修复
- **异步调用** — Coder 和 Debug 都用 `run_in_background=true`
- **3 轮上限** — 讨论超过 3 轮上报用户
- **不要自动验收** — 完成后停下，等用户决定
