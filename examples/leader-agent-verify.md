# Agent Verify（Leader 验收 + 路由）

> 在 agent-apply 之后使用。Leader 亲自验收代码，按问题类型路由到对应角色。

---

## 步骤

### 1. 选择变更

确定要验收的变更名称。

### 2. Leader 验收

Leader **亲自**阅读所有变更文件，对照 specs 逐项检查：

- [ ] 代码实现了 tasks 中的所有任务
- [ ] 代码符合 specs 中的场景要求
- [ ] 测试通过
- [ ] 代码质量可接受
- [ ] 遵循项目约定

### 3. 分类问题并路由

验收结果分三种情况，**严格串行**：

#### 情况 A：缺少功能

→ 走 Coder+Debug 流程（同 agent-apply）：
1. 异步派 Coder 补充
2. Leader 中转给 Debug 审查
3. 如有问题，Leader↔Debug 讨论（最多 3 轮）
4. 回到步骤 2 重新验收

#### 情况 B：有 Bug

→ 异步派 Debug 修复（给具体问题列表）

Debug 完成后 Leader 审查：
- 满意 → 回到步骤 2 重新验收
- 不满意 → Leader↔Debug 讨论（最多 3 轮）

#### 情况 C：验收通过

→ 异步派 Tester 运行验证

### 4. 处理 Tester 结果

**通过**：任务完成。

**失败**：Tester 报告 bug → 回到步骤 3 情况 B，派 Debug 修复。

---

## 路由决策树

```
Leader 验收
    │
    ├─ 缺功能 → Coder 补充 → Debug 审查 → 重新验收
    │
    ├─ 有 bug → Debug 修复 → (讨论) → 重新验收
    │
    └─ 通过 → Tester 验证
                │
                ├─ 通过 → 完成
                └─ 失败 → Debug 修复 → 重新验收
```

---

## 原则

- **Leader 必须亲自看代码** — 不能跳过验收
- **Leader 可以改代码** — 发现问题可以亲自修正
- **严格串行** — 验收 → 路由 → 等结果 → 重新验收，不并行
- **所有调用异步** — 都用 `run_in_background=true`
- **问题分类要准确** — 缺功能走 Coder+Debug，有 bug 走 Debug
- **Tester 最后才上** — 只有验收通过后才派 Tester
