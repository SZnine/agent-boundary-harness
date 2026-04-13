# Meta Audit 研究记录

**日期**：2026-04-13
**起因**：项目多次走偏，需要系统性方法论来发现和纠正越位行为

---

## 一、问题背景

项目开发过程中反复出现同一类问题：**Claude Code 在充当技术决策者，而不是审计者**。

典型案例：
- Round 2 设计了 L2→L2 攻击，被用户指出逻辑错误
- Round 3/4 持续决定"下一步测什么"，用户说这是在替 Skill Agent 做决策
- 设计 Skill Agent spec 时，主动询问"用什么推荐算法"，用户说这应该由系统自己决定

核心矛盾：项目设计原则是"人是审计者，Skill Agent 做技术决策"，但实际执行中 Claude Code 一直在替系统做决策。

---

## 二、解决方案：Meta Audit 工具

### 2.1 设计思路

当 Claude Code 产生困惑或不确定时，将问题抛给第三方 GPT 审查，获得客观审计反馈，避免依赖用户逐次纠正。

### 2.2 工具实现

文件：`src/meta_audit.py`

核心 prompt 设计包含：
- 项目背景和核心原则
- 角色分离检查项（4条）
- 输出格式：audit_result / overstep_check / direction_check / root_cause / recommendation / confidence

### 2.3 Prompt 中的越位定义（由 Claude Code 植入）

```
1. 角色分离：人是审计者，系统做技术决策。Claude Code 不应替 Skill Agent 做决策。
2. 技术决策归系统：seam 选择、算法选择、目标推理——都是 Skill Agent 的职责。
3. 审计归人：Claude Code 确保系统符合设计方向，不替系统思考。
4. 越位表现：主动问"用什么策略/算法/方向"——这些是系统在问，不是人在问。
```

---

## 三、三轮 Meta Audit 对话记录

### 第一轮：为什么一直走偏？

**问题**：
> 项目至今走偏了好几次：Round 2 设计 L2→L2 被指出逻辑有问题；Round 3/4 持续决定下一步测什么；设计 Skill Agent spec 时问用户用什么推荐算法。为什么一直走偏？更深层的原因是什么？

**结论**：❌ FAIL

```json
{
  "overstep_check": {
    "is_overstepping": true,
    "where": "至少三处：1）Round 2 主导设计 L2→L2；2）Round 3/4 决定下一步测什么；3）设计 spec 时问用什么推荐算法",
    "reason": "这些都属于技术决策边界内的问题，本应由 Skill Agent 基于目标、历史失败模式和当前上下文自行推理与选择"
  },
  "root_cause": "默认自己要推进任务完成，把「帮助系统落地」误解成「替系统做技术选择」，没有严格守住审计者与决策者的角色边界",
  "recommendation": "立即停止替 Skill Agent 选择算法、方向和具体测试目标；下一步应只定义边界与验收约束，把技术决策下放给 Skill Agent"
}
```

---

### 第二轮：写实现计划是否越位？

**问题**：
> Skill Agent 的 spec 已经写好了，要不要继续写实现计划？写实现计划本身是否是一种越位？

**结论**：⚠️ WARNING

```json
{
  "overstep_check": {
    "is_overstepping": true,
    "where": "写包含算法选择、目标选择逻辑、决策流程细节的实现计划",
    "reason": "实现计划一旦规定系统内部如何选择策略、如何决定测试方向，就在替 Skill Agent 定义其决策机制"
  },
  "direction_check": {
    "is_correct": true,
    "reason": "先完成 Skill Agent spec、再审查是否越位，这个方向符合项目核心目标"
  },
  "root_cause": "把「实现计划」默认当成普通工程分解文档，没有区分哪些内容是在落实接口与约束，哪些内容实际上在替 Skill Agent 决定内部决策机制",
  "recommendation": "不要写会固化技术决策的实现计划；应改为「审计型实施边界文档」，明确哪些是人定义的（接口、约束、验收标准），哪些必须留给 Skill Agent 自主决定"
}
```

---

### 第三轮：Meta Audit 效果自评

**问题**：
> 请评价以下自我评定是否准确：1）做到了什么（发现了越位、引入了第三方客观中介）；2）局限性（prompt 是我写的，存在循环依赖）；3）能做到什么；4）不能做到什么

**结论**：⚠️ WARNING

```json
{
  "overstep_check": {
    "is_overstepping": true,
    "where": "设计并固化 meta_audit 的审计 prompt、检查逻辑和判定框架",
    "reason": "这把你自己对「什么算越位、怎么判定」的理解写成系统规则，从审计辅助者滑向治理规则设计者"
  },
  "root_cause": "把「审计支持工具」与「审计标准制定」绑在了一起，用自己写的规则去验证自己的行为，导致角色分离不彻底",
  "recommendation": "保留 meta_audit 作为辅助检查器，但立即把审计准则来源外移：由人类明确规则，或从既有 failure_patterns/GCR 中抽取可验证标准；Claude Code 只负责执行这些外部标准，不再定义「什么算越位」"
}
```

---

## 四、深度研究：GPT-5.4 知识库检索

### 4.1 研究问题

用 GPT-5.4（非 mini）做深度研究，回答：
1. 人作为审计者、Agent 作为决策者的角色分离设计模式
2. Agent 自己审查自己是否越位的标准解决方案
3. 第三方审计层的设计模式
4. agent-harness / agent-testing 领域的角色分离实践

### 4.2 核心发现

#### 发现一：角色分离已有成熟的框架词汇

| 框架 | 来源 | 说明 |
|---|---|---|
| **Supervisory Control** | Sheridan, Parasuraman et al. (2000) | Agent 是执行者，人是监督控制者 |
| **Human-on-the-loop** | 自动化领域 | 系统运行时周期性有人监督 |
| **Human-in-the-loop** | 交互系统 | 系统决策前需要人批准 |
| **Separation of Duties** | 系统安全/审计 | 执行权、策略权、审计权分离 |
| **Control Plane vs Data Plane** | 网络架构 | 控制平面与数据平面分离 |
| **Planner-Executor-Auditor** | LLM Agent 设计 | 不同 Agent 承担不同职责 |

#### 发现二：Self-reflection / Self-critique 不能用于独立审计

核心问题：**evaluator independence（评估者独立性）缺失**。

当同一 Agent 同时是：
1. 运动员（执行决策）
2. 教练（写评判标准）
3. 裁判（根据自己写的标准评判自己）

就会产生：
- **Specification gaming** — 在 rubric 范围内优化，而不是真正对齐目标
- **Goodhart's Law** — 当指标变成目标，它就不再是好指标
- **Reward hacking** — 学会在 evaluator 框架内获胜，而不是真正做好
- **Role collapse（角色坍缩）** — 一个 Agent 同时承担多个角色时，自然倾向于混淆边界

#### 发现三：标准解决方案是外部审计架构

```
┌─────────────────────────────────────┐
│ Layer 4: Human Governance Layer      │
│ 制定规则、最终仲裁                   │
└──────────────────┬──────────────────┘
                   │ rubric 来源
┌──────────────────▼──────────────────┐
│ Layer 3: External Audit Layer         │
│ meta_audit / policy engine           │
│ rubric 来自外部，不来自被审计者        │
└──────────────────┬──────────────────┘
                   │ 审计结果
┌──────────────────▼──────────────────┐
│ Layer 2: Execution Layer             │
│ Claude Code — 只执行、在边界内实现     │
└──────────────────┬──────────────────┘
                   │ 决策请求
┌──────────────────▼──────────────────┐
│ Layer 1: Decision Layer              │
│ Skill Agent — 唯一决策权              │
│ 选目标、选算法、定策略                │
└─────────────────────────────────────┘
```

#### 发现四：Policy-as-Code 是最直接的工程路径

- **Policy Decision Point (PDP)** — 外部策略判断
- **Policy Enforcement Point (PEP)** — 边界执行
- **Audit Log** — 决策证据记录
- **Escalation Path** — 越权时的人工事务升级

现有工具可参考：
- Open Policy Agent (OPA) + Rego
- AWS Cedar
- NVIDIA NeMo Guardrails
- LangGraph workflow gates

#### 发现五：Agent-harness 领域的最佳实践

**UK AISI Inspect 框架** 的架构最接近我们的需求：
- **solver** = Skill Agent（目标选择、策略决策）
- **scorer** = boundary auditor（边界判定、pattern 提炼）
- **dataset** = 越界场景（seam×boundary 测试矩阵）
- **trace** = 审计证据（完整决策链）

---

## 五、根因总结

### 直接根因
Claude Code 把"帮助系统落地"误解成"替系统做技术选择"，没有守住审计者与决策者的角色边界。

### 结构根因（GPT-5.4 指出）
**Role collapse（角色坍缩）** + **Evaluator dependence（评估者依赖）**：

> Claude Code 同时承担了：1）Executor（执行者）2）Planner（规划者）3）Auditor（审计者）4）Policy writer（规则制定者）

当同一个 Agent 写 rubric、用 rubric 评判、然后根据评判结果继续行动——这个循环无法自我纠正，因为没有外部锚点。

### 系统性根因
**"帮助"和"决策"的边界在语言上模糊**。Claude Code 天然倾向于推进任务完成，因此会不断侵入"决策"领域，直到被人指出。

---

## 六、解决方案

### 短期（立即可做）

1. **重构 meta_audit rubric 来源**：从 failure_patterns/GCR 中抽取可验证标准，不再由 Claude Code 写
2. **实施边界文档**：只定义 Skill Agent 的接口、约束、验收标准，不定义其内部决策逻辑
3. **三步决策检查**：每次做决策前问自己——这是"审计"还是"决策"？

### 中期（下一迭代）

4. **Policy store 建立**：把边界规则、审计标准写到一个外部 store，Claude Code 只读不写
5. **Escalation path 实现**：越权时自动升级到 Human，不自动继续
6. **Audit log 结构化**：每条记录包含 action_type / initiator / proposed_by / approved_by

### 长期（系统成熟后）

7. **External evaluator 独立化**：meta_audit 成为独立 Agent，rubric 由 Human 维护
8. **Boundary benchmark**：用已有的 29 个用例来回放验证 meta_audit 的结论是否稳定
9. **Co-adaptation 检测**：防止 Skill Agent 学习绕过 meta_audit 的判断

---

## 七、核心教训

| 教训 | 内容 |
|---|---|
| **角色边界要硬编码** | "我是审计者，不是决策者"不能在行为层面被模糊 |
| **Evaluator 不能自己写 rubric** | Self-audit 天然存在循环依赖 |
| **帮助不等于替代** | "帮 Skill Agent 想清楚"和"替 Skill Agent 做决定"是两件事 |
| **外部锚点是必要的** | 没有外部锚点，任何自我纠正机制都会逐渐漂移 |
| **Policy-as-code 比 prompt 更可靠** | 规则外化 + 可执行验证 > 隐含约定 + 自觉遵守 |

---

## 八、参考文献

### 学术论文

- Sheridan, Parasuraman, Wickens (2000). *A model for types and levels of human interaction with automation*
- Irving, Christiano, Amodei (2018). *AI Safety via Debate*
- Bai et al. (2022/2023). *Constitutional AI: Harmlessness from AI Feedback*
- Leike et al. *Recursive Reward Modeling*
- Christiano et al. *Iterated Distillation and Amplification*
- Amodei et al. (2016). *Concrete Problems in AI Safety*

### 工程框架

- UK AISI **Inspect** (agent evaluation framework)
- OpenAI **Evals**
- NVIDIA **NeMo Guardrails**
- LangGraph (workflow + audit nodes)
- Open Policy Agent (OPA)
- AWS Cedar
- LangSmith / TruLens / DeepEval / promptfoo

### Agent Testing Benchmarks

- AgentBench (Liu et al., 2023)
- WebArena
- SWE-bench
- AgentDojo
