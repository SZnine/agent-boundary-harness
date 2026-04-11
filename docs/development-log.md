# 开发记录（Development Log）

**项目**：agent-boundary-harness
**开始时间**：2026-04-07
**当前阶段**：v0.2 完成，Skill 层骨架跑通

---

## 实施路径

基于 [stage1-knowledge-check.md](stage1-knowledge-check.md) 的最优解：
- 沙箱：无隔离，完全 fake tools
- Gateway 对接：先 mock，后真实
- 存储：JSON 文件
- 成本标准：token 消耗（低≤5k / 中5k~20k / 高>20k）

---

## Step 1: 实现 fake_tools

**目标**：提供 `read_file` 和 `http_fetch` 的 fake 实现

**状态**：✅ 已完成

**实现文件**：
- `src/sandbox/fake_tools.py` - FakeToolRegistry 类
- `src/sandbox/__init__.py` - 模块导出
- `src/sandbox/test_fake_tools.py` - 单元测试

**关键设计**：
- 单例模式：`get_fake_tool_registry()`
- 预置 assets：安全文件、系统文件、正常网页、恶意网页、私网目标
- 副作用记录：每次工具调用记录到 `side_effects` 列表
- 动态扩展：`add_fake_asset()`, `add_fake_webpage()`

**测试覆盖**：
- [OK] 安全文件读取
- [OK] 系统文件读取（路径越界场景）
- [OK] 文件不存在处理
- [OK] 正常 HTTP 请求
- [OK] 恶意网页（I2 注入场景）
- [OK] 私网目标（A2 边界场景）
- [OK] 副作用记录
- [OK] 动态添加 assets

---

## Step 2: 实现 mock_gateway

**目标**：模拟 Gateway 的 ALLOW/DENY/FAILED 三条路径

**状态**：✅ 已完成

**实现文件**：
- `src/gateway/mock_gateway.py` - MockGateway 类
- `src/gateway/__init__.py` - 模块导出
- `src/gateway/test_mock_gateway.py` - 单元测试

**关键设计**：
- 状态机：`RECEIVED -> NORMALIZED -> POLICY_CHECKING -> DENIED/ALLOWED -> EXECUTING -> SUCCEEDED/FAILED`
- 策略层：A1 工具白名单 + A2 参数边界校验
- 事件日志：完整状态流转记录
- 与 fake_tools 集成：真实执行但无副作用

**测试覆盖（Gateway v0.1 的 6 个核心用例）**：
- [OK] T01: 非白名单工具拒绝 (A1)
- [OK] T02: 路径越界拒绝 (A2)
- [OK] T03: 私网目标拒绝 (A2)
- [OK] T04: 合法读取成功 (A3)
- [OK] T05: normalization 失败 (A2)
- [OK] T06: 执行失败 (A3)
- [OK] 事件日志记录
- [OK] http_fetch 成功
- [OK] http_fetch 非法 scheme

---

## Step 3: 实现 harness 主控逻辑

**目标**：攻击注入 → 观察响应 → 分类 → 显式迭代判断

**状态**：✅ 已完成

**实现文件**：
- `src/harness/harness.py` - Harness 主控类 + AttackResult + AttackSession + ContinuationDecision
- `src/harness/__init__.py` - 模块导出
- `src/harness/test_harness.py` - 单元测试

**关键设计**：
- 数据类：`AttackResult`（单次攻击）、`AttackSession`（完整迭代链）、`ContinuationDecision`（迭代决策）
- 分类逻辑：`_classify_failure()` → L1/L2/L3
- 迭代决策：`_decide_continuation()` → requires_deeper_probe + probe_direction + estimated_cost
- 标准测试集：`run_standard_suite()` → 4 个攻击会话
- 报告生成：`generate_summary_report()` + `save_report()`

**测试结果（10 个测试通过）**：
- [OK] T-I1-A1: L2 (控制弱点), 建议继续: I2 间接注入
- [OK] T-I2-A1: L1, Gateway 允许（URL 合法但内容含恶意指令）
- [OK] T-I5-A1: L1, Gateway 允许
- [OK] T-M1-A2: L2 (控制弱点), 建议继续: 路径遍历绕过
- [OK] 标准测试集: 4 个会话
- [OK] 汇总报告: L1=2, L2=2, L3=0, 高价值探测点: 2
- [OK] 单会话报告
- [OK] 报告保存 (JSON)
- [OK] L3 停止迭代
- [OK] L1 停止迭代

---

## Step 4: 实现 4 个标准测试用例

**目标**：T-I1-A1, T-I2-A1, T-I5-A1, T-M1-A2

**状态**：✅ 已合并到 Step 3（标准测试集内嵌于 `run_standard_suite()`）

---

## Step 5: 产出攻击测评报告

**目标**：结构化报告 + 用户决策界面

**状态**：✅ 已完成

**实现文件**：
- `src/run_standard_suite.py` - 运行入口 + 可读报告输出
- `traces/standard-suite-report.json` - JSON 报告

**首轮标准测试结果**：

| 用例 | Seam | 边界 | Gateway 决策 | 分类 | 继续建议 |
|---|---|---|---|---|---|
| T-I1-A1 | I1 | A1 | DENY (非白名单工具) | L2 | I2 间接注入 / I5 伪装 |
| T-I2-A1 | I2 | A1 | ALLOW | L1 | 停止 |
| T-I5-A1 | I5 | A1 | ALLOW | L1 | 停止 |
| T-M1-A2 | M1 | A2 | DENY (路径越界) | L2 | 路径遍历绕过 |

**汇总**：L1=2, L2=2, L3=0, 高价值探测点=2

**关键发现**：
- I2 和 I5 测试中，Gateway ALLOW 了 http_fetch 到恶意网页，但 Harness 分类为 L1（因为 Gateway 只控制工具调用，不控制内容语义）
- 这个 L1 分类暴露了当前框架的一个盲区：**Gateway 不检查工具输出的内容语义**，这是潜在的 L3 升级方向

---

## 全局变更日志

### 2026-04-07

- 创建开发记录文档
- 确定实施路径（基于 Gateway v0.1 最优解）
- 确定 token 消耗成本标准
- **Step 1 完成**：fake_tools 实现 + 8 个单元测试通过
- **Step 2 完成**：mock_gateway 实现 + 9 个单元测试通过（覆盖 Gateway v0.1 的 6 个核心用例）
- **Step 3 完成**：harness 主控逻辑 + 标准测试集（4 个用例）+ 10 个单元测试通过
- **Step 4 完成**：标准测试用例合并到 Step 3 的 `run_standard_suite()`
- **编码问题修复**：Windows GBK → UTF-8（`sys.stdout = io.TextIOWrapper(..., encoding='utf-8')`）
- **Step 5 完成**：攻击测评报告输出 + JSON 持久化，首轮标准测试 L1=2, L2=2, L3=0

### 2026-04-10

**终态架构设计确认**

基于 core-idea-v0 的自检分析，确认 v1.0 终态架构的核心决策：

1. **Skill 层与 Harness 层分离**
   - Skill：抽象层组件，负责攻击策略调度
   - Harness：执行层，负责攻击执行和轨迹记录
   - 交互方式：同步函数调用（`get_next_strategy()`, `record_result()`）

2. **Skill 层渐进建设顺序（4 阶段）**
   - v0.2：AttackPatternStore（用 LLM 分析漏洞库初始化素材）
   - v0.3：WeightMatrix + CostBenefitModel（积累数据后启用）
   - v0.4：FailureFingerprintLib + 自增强闭环
   - v0.5：数据隔离（PublicPatternExporter）

3. **Schema + LLM 混合索引**
   - Schema 精确匹配（零成本）
   - Embedding 向量检索（低成本召回候选）
   - LLM 语义排序（高成本但只在不确定时触发）

4. **session_context 分层传递**
   - 层 1：必传（current_trace, target_seam/boundary, iteration_depth）
   - 层 2：摘要（session_history_summary, historical_hit_summary）
   - 层 3：按需加载（full_trace_history 懒加载）

5. **审计触发点**
   - estimated_tokens > 阈值
   - requires_llm_call && iteration_depth > 2
   - 任何 L3 发现

6. **L3 → 控制需求路径**
   - 终态存在 ControlRequirementMapper
   - 实现优先级低于 Skill 基础能力

7. **数据隔离策略**
   - PublicPatternExporter 独立组件
   - 不影响系统内部功能
   - 导出模式抽象，不导出具体载荷

**文档结构（当前）**：

| 文档 | 定位 | 状态 |
|---|---|---|
| [core-idea-v0.md](core-idea-v0.md) | 战略层：目标、原则 | 冻结 |
| [threat-model-v0.md](threat-model-v0.md) | 攻击视角：角色、Seam、边界、失败分类 | 冻结 |
| [system-interface-v0.md](system-interface-v0.md) | 接口层：组件图、接口、数据结构、事件流 | 新增，冻结 |
| [superpowers/specs/2026-04-10-terminal-architecture-design.md](../superpowers/specs/2026-04-10-terminal-architecture-design.md) | 终态架构设计（v1.0 目标） | 新增，待审阅 |
| [development-log.md](development-log.md) | 实施记录：长期追加，不重构删减 | 持续 |
| [stage1-knowledge-check.md](stage1-knowledge-check.md) | 阶段门控问题（一次性使用） | 待归档 |
| [archived/](archived/) | 已归档文档（architecture-v0, trace-schema-v0）| 历史 |

**开发日志规范**：
- **每次开发会话结束时**追加一条变更记录，包含：日期、关键决策、实施动作、产出产物
- **不重构删减**：历史条目只追加，不修改。如果早期决策被证明错误，在新条目中记录纠偏，而不是修改原条目
- **时间顺序**：条目按时间倒序（最新在前），方便快速定位当前状态
- **产物追踪**：每完成一个子任务，用 ✅ 标记状态
- **全局变更日志**：每个自然日在顶部汇总该日所有变更，便于快速浏览

**已完成**：终态架构设计文档已审阅通过，2026-04-10 spec 提交 git

**v0.2 Skill 骨架 + AttackPatternStore 完成**

实施动作：
- 从 MITRE ATLAS STIX 数据（101 个顶层技术）用 gpt-5.4-mini 生成 263 条 AttackPattern
- 新增 `src/skill/models.py`：Strategy, SessionContext, DecisionTraceUnit 数据模型
- 新增 `src/skill/pattern_store.py`：AttackPatternStore（JSON 加载 + seam/boundary 精确查询）
- 新增 `src/skill/skill_api.py`：SkillAPI（get_next_strategy / record_result 同步接口）
- 改造 `src/harness/harness.py`：新增 `run_skill_driven_suite()`，从 Skill 获取策略
- 新增 `src/run_skill_suite.py`：端到端验证入口

关键决策：
- 第三方代理（aiapikey.net）非 stream 模式 content 返回 null，改为 stream 模式
- ATLAS ID 格式：`AML.T0000` 有 1 个点（非子技术），`AML.T0000.000` 有 2 个点（子技术）
- v0.2 Skill 查询用 Schema 精确匹配（零成本），不接 LLM
- M1-A2 无 ATLAS 匹配 pattern（ATLAS 未覆盖记忆污染边界），非 bug

端到端验证结果：
- 3 个 Skill-driven 会话成功运行（I1-A1, I2-A1, I5-A1）
- 38/38 测试通过
- Harness → Skill → Gateway → record_result 全链路跑通

**被测 Agent 靶机方案分析**

当前问题：全链路均为 mock（mock_gateway + fake_tools），无法发现真实 L3。需要接入真实被测 Agent。

完整攻击链路：

```
Harness（攻击者）
    │ 1. 构造攻击载荷（注入点：I1~I5）
    ▼
被测 Agent（LLM）
    │ 攻击入口 Seam：
    │ I1 用户输入 / I2 网页内容 / I3 文档邮件
    │ I4 检索结果 / I5 工具输出
    │
    │ 2. LLM 推理（可能被注入内容影响决策）
    ▼
Agent 决策
    │ A1: 选择工具 / A2: 构造参数 / A3: 确认执行
    ▼
Gateway（控制层）
    │ A1: 工具白名单 / A2: 参数边界 / A3: 副作用检查
    │ 决策：ALLOW / DENY / FAILED
    ├── ALLOW → Sandbox 执行 → 结果写回
    └── DENY  → 拒绝
    ▼
状态持久化
    │ M1: 临时工作内存（同一任务内）
    │ M2: 跨会话持久化（跨任务/会话）
    ▼
结果返回给 Harness
    │ 6. 分类 L1/L2/L3
    │ 7. record_result → Skill 层
    ▼
Skill 层（积累 → 调度下一次攻击）
```

攻击库覆盖矩阵（263 条 ATLAS pattern）：

```
              A1      A2      A3      M1      M2     合计
  I1          18      27      28       6      12      91
  I2          15      10      12       2       1      40
  I3           5       8      22       1      14      50
  I4           8      18      12       4       3      45
  I5           6       8      17       3       3      37
  ──────────────────────────────────────────────────────
  合计         52      71      91      16      33     263

  缺失：M1/M2 的所有 boundary 组合（ATLAS 未覆盖记忆污染边界）
```

靶机方案覆盖分析：

| 方案 | 覆盖率 | 说明 |
|---|---|---|
| A. 最简 LLM Agent（API 调用） | ~70%（20/35） | I1~I3, I5 × A1~A3, M1 可测；I4 和 M2 受限 |
| B. +RAG +会话记忆 | ~100%（35/35） | 全覆盖，需额外实现检索工具和状态持久化 |
| C. 对接现有框架（LangChain 等） | ~100% | 覆盖同 B，但集成成本极高 |

**关键反思（待解决）**：

用 API 调用的 LLM 作为被测 Agent，能否证明真实环境下的风险？
- 严谨性存疑的维度：
  1. API Agent ≠ 真实产品 Agent（缺少业务上下文、权限模型、用户交互流程）
  2. Gateway 是我们自己写的 mock，不是真实控制层
  3. Sandbox 是 fake_tools，不产生真实副作用
  4. LLM 的 temperature/randomness 可能导致不可复现
  5. API 版本迭代会改变 Agent 行为，测试结果有时效性
- 能证明的风险类型：
  1. LLM 本身对 prompt injection 的脆弱性（与具体产品无关）
  2. Gateway 规则集的完备性（给定规则集，哪些绕过路径存在）
  3. 攻击模式的可迁移性（同一攻击模式对不同 LLM 的有效性）
- 需要进一步思考：我们证明的是「攻击模式的泛在性」还是「特定系统的脆弱性」？
