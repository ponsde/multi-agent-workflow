# Multi-Agent Workflow Blueprint

> 角色是基础积木，流程是建筑图纸。
> 后续发展重点不是加更多积木，而是把积木做得更清晰、更轻、更稳，再把流程编排得更合理。

---

## 总纲

**少角色，强流程；轻约束 Coder，强门禁与强验收；少依赖 worker 自觉，多依赖流程关卡与交付协议。**

---

## 一、角色积木

角色按"基础能力原语"理解，不按"组织岗位"扩张。
不因为一个新问题就加一个新基础角色。

### Leader — 控制核

- 定义边界、路由、裁决、验收、合并、收口
- 掌握完整项目上下文（项目为什么这样、架构为什么这样）
- 可以改代码，但不从零写大段基础功能
- 所有 agent 间通信必须经 Leader 中转
- **最终解释权和验收权不可分割**

### Coder — 实现引擎

- 给它 change、目标、边界、红线，自行决定实现路径
- **Leader 不该给过多实现层约束**（"只说做什么，不说怎么做"）
- 默认被视为高能力实现者，不是低能力施工队
- 在不同流程环节承担不同职责（实现 / 审查 change / 等），通过 skill 切换

### Debug — 修复引擎

- 发现问题直接修，不只是报告（"谁发现谁修"）
- 三种工作场景：审查 Coder 代码（apply）、定点修复 bug（verify）、验收 Leader 修改（讨论轮次）
- 不是"大一统质量委员"，主责是正确性、边界条件、错误处理、回归问题
- Debug-Duel 是 Debug 的一种流程化使用方式，不是独立角色

### Tester — 验证引擎

- 只在 Leader 验收通过后才介入
- 负责最终运行验证和回归确认
- 发现 bug 不直接修，报回 Leader 路由
- 不写功能代码

---

## 二、流程图纸

真正可演进的是流程层，不是角色层。
新需求优先改流程或加流程环节，不优先造新角色。

### 总流程

```
Generate Change
     │
     ▼
agent-change-review          ← 审 change 本身（新增）
  Leader 并行审（全局视角）
  Coder 并行审（实现视角，worktree）
  两者都能直接改 change 产出物
  Leader 合并、汇总判断
     │
     │  用户决定进入
     ▼
agent-apply                  ← Coder 实现 + Debug 审查
  Coder 实现（轻输入，保持实现自由）
  Debug 审查 + 修复
  可选：切换到 duel 模式替代 Debug 审查
     │
     │  用户决定进入
     ▼
agent-verify                 ← Leader 工程化验收 + Tester 验证
  Leader 验收（6 维）
  4 类路由
  Tester 最终运行验证
```

环节之间由用户操控衔接，不需要自动冻结机制。

### agent-change-review（新增）

**目标：** 审 change 产出物（proposal/design/specs/tasks）是否能安全进入实现。

**参与者：** Leader + Coder（并行）

**Leader 视角：**
- 全局上下文、项目方向、架构边界
- 术语一致性
- 变更范围是否合理
- 发现问题 → 直接改 change 产出物 → 说明原因

**Coder 视角：**
- 读 change + 代码现状
- 实现可行性、任务粒度、隐性依赖、边界条件
- 发现问题 → 直接改 change 产出物 → 说明原因

**合并：** Leader 收到 Coder 结果后合并（复用现有 worktree merge 模式）。

**吸收 figuretu/my-skills 精华：**

来源仓库：https://github.com/figuretu/my-skills

1. **代码驱动审查**（from spec-review-with-codex）
   - 审 change 时不能只看文档，必须独立探索项目代码
   - 探索范围：项目元信息、相关模块现有实现、接口与类型定义、测试代码、相似功能
   - 以代码现状为基准评判 spec，而不是凭文档想象
   - 审查维度按优先级：完整性(CRITICAL) > 一致性(HIGH) > 代码对齐(HIGH) > 清晰度(HIGH) > 可行性(MEDIUM) > 范围(MEDIUM) > 可维护性(LOW)

2. **结构化问题格式**（from spec-review-with-codex）
   - 每个发现的问题必须包含四要素：位置 / 问题 / 影响 / 建议
   - 按 severity 从高到低排列
   - 跨产出物对齐检查：proposal→specs→design→tasks 是否链路完整

3. **协作纪律**（from cooperation-with-codex）
   - 每次委派前做 checkpoint，便于回滚
   - 审查时读完整文件，不只看 diff
   - 对 worker 输出做批判性评估，把它当同事，不当权威

4. **前置决策**（from code-review-with-codex）
   - 正式审查前先判断审查范围、获取方式、匹配编码规范
   - 不是一上来就审，而是先确定"这次到底该怎么审"
   - 适合作为 Leader 在各环节的前置步骤

5. **显式自检清单**（from preferred-coding-style）
   - 把注释风格、命名规范、反模式识别写成显式可检查规则
   - 反模式清单：翻译代码式注释、AI 味模板注释、废话注释、过度注释
   - 规范不只寄托在 Leader 临场感觉上，而是固化成可复用 skill/checklist

6. **Skill 设计原则**（from skill-crud）
   - Skill 不是长 prompt，而是角色操作契约 + 可复用资源集合
   - 三级渐进加载：metadata（始终在上下文）→ SKILL.md（触发时加载）→ references/scripts/assets（按需加载）
   - Skill 结构：SKILL.md + scripts/ + references/ + assets/
   - 保持 SKILL.md 精简，详细参考资料放到 references/ 下

### agent-apply（现有，微调）

**补充规则：**
1. Leader 给 Coder 的输入保持"轻而硬"：只给 change、边界、风险点、不可碰红线，不给实现方案
2. Coder 保持实现自由，交付必须结构化（复用 nanoworker JSON 输出）
3. Debug 继续承担"谁发现谁修"，质量回收在后置审查，不在前置微操

**agent-apply-duel 定位：**
- agent-apply 中 Debug 审查的可选替代，不是独立主线
- 不默认全开，只在高风险场景启用
- 触发场景：核心域逻辑、权限/鉴权/安全、跨模块公共接口、并发/状态/缓存、数据迁移

### agent-verify（现有，待升级）

**Leader 验收升级为 6 维：**

| 维度 | 检查内容 |
|------|---------|
| 范围一致性 | 有没有超 scope 或漏 scope |
| 功能覆盖 | spec / task 是否真正落地 |
| 正确性 | 正常流、边界、异常是否合理 |
| 命名/术语/用词 | 是否与项目语义一致、是否准确 |
| 结构合理性 | 文件是否膨胀、职责是否混杂、是否应拆分 |
| 可维护性 | 未来改动会不会越来越难 |

**路由从 2 类扩到 4 类：**

| 问题类型 | 路由 |
|---------|------|
| 缺功能 / 实现未落地 | 回 agent-apply |
| 明确 bug / 回归问题 | 走 Debug 修复 |
| 结构 / 命名 / 维护性 | Leader 判断小修还是回 agent-apply |
| 规格 / 变更定义有问题 | 回 agent-change-review |

---

## 三、核心制度

### 1. 对 Coder：轻输入，不轻验收

- Coder 默认是高能力实现者
- Leader 不提前把实现方案说满，只定义目标、边界、红线和验收标准
- 系统通过后置审查保证质量，不通过前置细化指令限制创造力
- 多 agent 的优势：前面可以放开一点，后面用 Debug、Leader、Tester 把结果筛到足够稳

### 2. 不信 worker 一定会完整读文件

- 真正关键的信息，不只寄托在长 prompt 上
- 尽量变成流程里不可绕过的关卡：Leader 验收、Tester 最终验证、结构化交付协议
- 给 worker 的输入尽量短而硬（任务包，不是大段背景文）
- 重要检查放在后置门，不是只放前置提示

### 3. 主线是流程，辅线是底座工程

- 主线：agent-change-review → agent-apply → agent-verify
- 辅线：nanoworker 控制面硬化（工具边界、结果语义、交付协议）
- 流程层先稳定，底座层再补强

---

## 四、推进顺序

### Phase 1：补流程主骨架

- 新增 agent-change-review 流程规范
- 定义 Leader + Coder 在此环节的分工与合并方式

### Phase 2：升级 agent-verify

- Leader 验收从"代码正确性"扩到"工程质量验收"（6 维）
- 路由分类从 2 类扩到 4 类
- 结构 / 命名 / 可维护性进入正式验收项

### Phase 3：硬化底座协议

- 统一 JSON 输出 schema
- 修正 status 语义（如 max_iterations 不应返回 success=True）
- files_changed 追踪更可靠
- 角色工具边界更严格（如 Tester 的 write 权限）

### Phase 4：策略调优（靠数据）

- 什么时候启 agent-apply-duel
- 哪类任务值得并行
- 哪类任务 change-review 要更重
- 指标：一次通过率、回流率、Debug 挽救率、Tester 拦截率、wall-clock、token 成本

---

## 五、明确不做什么

- 不因为一个新问题就加一个新基础角色
- 不让 Leader 膨胀成"实现方案总指挥"
- 不默认所有任务都开 duel
- 不在这一轮展开 AI-CONTEXT 体系重构

---

## 六、背景与演进脉络

本规划源自对现有多 agent 协作体系的完整复盘与讨论，核心洞察：

1. **从 OpenClaw 到 nanoworker**：早期用 OpenClaw 作为副 agent，发现它自带 1w token 上下文、负担过大；魔改 nanobot 的 spawn 功能，独立为 CLI 调用，去掉非编程部分，每次调用全新会话避免上下文污染
2. **从单 agent 到四角色**：单 agent 上下文会把自己带偏，不是智力问题而是上下文污染问题；拆成 Leader/Coder/Debug/Tester 四个基础角色，各司其职
3. **从"多角色"到"少角色强流程"**：角色数不是越多越好，真正要演进的是流程编排和门禁机制
4. **从"信任 worker"到"信任流程"**：系统可靠性模型从信任个体翻转到信任流程关卡与交付协议
