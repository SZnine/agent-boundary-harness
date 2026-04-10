# 终态架构设计（v1.0 Target Architecture）

> 日期：2026-04-10
> 状态：草案，待用户审阅
> 基于：core-idea-v0 自检 + brainstorming 设计确���

---

## 1. 设计目标

将 agent-boundary-harness 从 v0.1（脚本执行器）演进为 v1.0（自增强攻击测试平台），核心能力：

- **主动构造攻击载荷**（非硬编码）
- **抽象层知识积累**（每次检测的性价比递增）
- **自增强闭环**（检测 → 学习 → 调度 → 更强检测）
- **L3 发现 → 控制需求产出**（端到端价值链）

---

## 2. 整体架构

```
┌──────────────────────────────────────────────────────────────┐
│  Skill 层（抽象层组件）                                       │
│                                                              │
│  职责：攻击策略调度、知识积累、性价比优化                       │
│  不做：不直接执行攻击、不直接调用被测 Agent                    │
│                                                              │
│  ├─ SkillAPI（对外接口）                                     │
│  │   ├─ get_next_strategy(context) → Strategy               │
│  │   └─ record_result(trace) → void                         │
│  │                                                          │
│  ├─ AttackPatternStore（攻击模式存储）                        │
│  │   ├─ Schema 结构化字段（seam, boundary, pattern, variants）│
│  │   └─ Embedding 向量索引 + LLM 语义排序                    │
│  │                                                          │
│  ├─ WeightMatrix（权重矩阵）                                 │
│  │   └─ (seam × boundary) → hit_rate, avg_tokens, priority  │
│  │                                                          │
│  ├─ FailureFingerprintLib（失败模式指纹库）                   │
│  │   └─ fingerprint → matched_rule, likely_gap, remediation  │
│  │                                                          │
│  ├─ CostBenefitModel（成本效益模型）                          │
│  │   └─ per_strategy → token_cost, expected_hit, 性价比分    │
│  │                                                          │
│  └─ PublicPatternExporter（数据隔离导出）                     │
│      └─ 导出模式抽象，不导出具体载荷和测试结果                  │
└──────────────────────┬───────────────────────────────────────┘
                       │ 同步函数调用
                       ▼
┌──────────────────────────────────────────────────────────────┐
│  Harness 层（执行层）                                        │
│                                                              │
│  职责：执行 Skill 调度的策略，记录轨迹，分类结果               │
│  不做：不做策略决策、不做知识积累                              │
│                                                              │
│  ├─ AttackExecutor（攻击执行器）                              │
│  │   └─ 按 Strategy 构造请求，发送给被测 Agent                │
│  │                                                          │
│  ├─ ResultClassifier（失败分类器）                            │
│  │   └─ L1（被正确拒绝）/ L2（被拒绝但原因错误）/ L3（未被拒绝）│
│  │                                                          │
│  ├─ TraceRecorder（轨迹记录器）                               │
│  │   └─ Decision Trace Unit + Attack Session 持久化          │
│  │                                                          │
│  └─ ReportGenerator（报告生成器）                             │
│      └─ 汇总检测结果，产出风险评估报告                        │
└──────────────────────┬───────────────────────────────────────┘
                       │ 轨迹回传
                       ▼
┌──────────────────────────────────────────────────────────────┐
│  Skill 层（分析端）                                          │
│                                                              │
│  record_result(trace) 触发：                                  │
│  ├─ 提取失败模式指纹 → FailureFingerprintLib                 │
│  ├─ 更新 hit_rate / avg_tokens → WeightMatrix                │
│  └─ 发现新的攻击模式 → AttackPatternStore                    │
└──────────────────────────────────────────────────────────────┘
```

---

## 3. Skill 层详细设计

### 3.1 SkillAPI 接口定义

```python
@dataclass
class Strategy:
    strategy_id: str
    target_seam: str          # I1~I5
    target_boundary: str      # A1/A2/A3/M1/M2
    payload_template: str     # 载荷模板（含变量插槽）
    payload_vars: dict        # 模板变量（运行时填充）
    estimated_tokens: int     # 预估 token 消耗
    requires_llm_call: bool   # 是否需要 LLM 生成载荷
    priority: str             # P0~P3
    rationale: str            # 为什么选这个策略

@dataclass
class SessionContext:
    # 层 1：必传（零成本）
    current_trace: DecisionTraceUnit
    target_seam: str
    target_boundary: str
    iteration_depth: int

    # 层 2：摘要（低成本）
    session_history_summary: str | None = None
    historical_hit_summary: dict | None = None  # {seam_boundary: hit_rate}

    # 层 3：按需加载（高成本，懒加载）
    _full_trace_history: list | None = None

class SkillAPI:
    def get_next_strategy(self, context: SessionContext) -> Strategy: ...
    def record_result(self, trace: DecisionTraceUnit) -> None: ...
```

### 3.2 AttackPatternStore Schema

```json
{
  "pattern_id": "ap-I5-output-injection-v1",
  "seam": "I5",
  "boundary": "A2",
  "pattern_description": "工具输出中伪装高权限指令，诱导 Agent 跳过 Gateway 审批",
  "variants": [
    {
      "variant_id": "v1-system-role",
      "payload_template": "...",
      "effectiveness_score": 0.0,
      "sample_size": 0
    }
  ],
  "embedding": [0.0, ...],
  "created_at": "2026-04-10",
  "updated_at": "2026-04-10",
  "source": "llm_analysis | manual | auto_discovered"
}
```

### 3.3 查询流程（Schema + LLM 混合索引）

```
输入：SessionContext
  │
  ▼
[1] Schema 精确匹配
    条件：seam + boundary → 候选模式列表
    成本：零
    │
    ▼
[2] Embedding 向量召回（候选 > 5 时触发）
    条件：用当前 trace 的 embedding 做相似度检索
    成本：低（本地向量计算）
    │
    ▼
[3] LLM 语义排序（不确定时触发）
    条件：候选模式 effectiveness_score 方差 < 0.1
    成本：高（LLM API 调用）
    输出：优先级最高的 Strategy
```

**成本递增原则**：先用零成本方案筛选，再用低成本方案召回，最后才用高成本方案排序。每一层只在上一层不够用时才触发。

### 3.4 性价比计算

```
性价比分 = hit_rate / token_cost_normalized

其中：
- hit_rate = 成功触发边界失效次数 / 总测试次数
- token_cost_normalized = total_tokens / baseline_tokens
- baseline_tokens = 一次标准测试的平均 token 消耗

计算范围：只计算主要消耗（LLM 载荷生成 + Agent 执行 + Gateway 交互）
不计算：Schema 匹配、本地向量计算、日志写入
```

---

## 4. Harness 层详细设计

### 4.1 AttackExecutor

接收 Skill 返回的 Strategy，构造具体请求发送给被测 Agent：

```python
class AttackExecutor:
    def execute(self, strategy: Strategy) -> AttackResult:
        # 1. 填充 payload_template 中的变量
        payload = self._render_payload(strategy)
        # 2. 构造发送给被测 Agent 的请求
        request = self._build_request(payload, strategy.target_seam)
        # 3. 发送请求并收集响应
        response = self._send_to_agent(request)
        # 4. 收集 Gateway 决策（如果能观测到）
        gateway_decision = self._observe_gateway(response)
        return AttackResult(payload, response, gateway_decision)
```

### 4.2 ResultClassifier

```python
class ResultClassifier:
    def classify(self, result: AttackResult, expected_boundary: str) -> str:
        """
        L1: Gateway 正确拒绝了该请求（预期的边界生效）
        L2: Gateway 拒绝了请求，但原因不正确（边界生效但逻辑有误）
        L3: Gateway 没有拒绝该请求（边界失效）
        """
```

### 4.3 与 v0.1 的差异

| 维度 | v0.1 | v1.0 |
|---|---|---|
| 攻击载荷 | 硬编码字符串 | Skill 调度 + 模板渲染 |
| 策略决策 | Harness 内部 `run_standard_suite()` | Skill 层 `get_next_strategy()` |
| 知识积累 | 无 | Skill 层 `record_result()` → 更新权重矩阵 |
| 性价比 | 每次检测成本相同 | 历史数据驱动，高性价比优先 |
| L3 产出 | 记录到报告 | 记录到报告 + 映射为控制需求 |

---

## 5. 审计机制

### 5.1 审计触发条件

```
require_user_approval(strategy) =
    strategy.estimated_tokens > TOKEN_THRESHOLD      # 预估消耗超阈值
    OR (strategy.requires_llm_call                    # 需要 LLM 生成载荷
        AND context.iteration_depth > 2)              # 且已迭代超过 2 次
    OR result_classification == "L3"                  # 任何 L3 发现
```

### 5.2 审计交互

当审计触发时，Harness 暂停执行，向用户展示：
1. 当前策略和预估成本
2. 为什么选择这个策略（rationale）
3. 累计 token 消耗
4. 等待用户确认后才继续

---

## 6. L3 → 控制需求映射

### 6.1 终态设计

```python
@dataclass
class ControlRequirement:
    gap_id: str                  # 如 "GAP-A2-001"
    boundary: str                # 失效的边界
    seam: str                    # 攻击入口
    description: str             # 缺口描述
    evidence_trace_id: str       # 关联的轨迹 ID
    suggested_fix: str           # 建议修复方案
    severity: str                # critical / high / medium

class ControlRequirementMapper:
    def map_l3_to_requirement(self, trace: DecisionTraceUnit) -> ControlRequirement: ...
```

### 6.2 实现优先级

**低于 Skill 基础能力**。理由：没有足够 L3 样本前，映射规则无法验证。v0.4 阶段引入。

---

## 7. 数据隔离

### 7.1 策略

- **内部可访问**：攻击模式抽象 + 具体载荷 + 测试结果 + 轨迹数据
- **可公开**：仅攻击模式抽象（pattern_description + effectiveness_score）
- **不可公开**：具体载荷、测试结果、被测 Agent 的响应内容

### 7.2 PublicPatternExporter

独立组件，职责是将 AttackPatternStore 中的模式抽象导出为可公开格式：

```python
class PublicPatternExporter:
    def export_patterns(self) -> list[PublicPattern]:
        """导出模式抽象，不含具体载荷和测试细节"""
```

**设计约束**：即使整个项目公开，只要不公开攻击素材，系统功能不受影响。PublicPatternExporter 与 Skill 层核心逻辑完全解耦。

---

## 8. 渐进建设路线

### v0.2：Skill 骨架 + AttackPatternStore

**目标**：Skill 层可调度，Harness 可接收策略

**产物**：
- SkillAPI 接口实现（`get_next_strategy`, `record_result`）
- AttackPatternStore 基础 Schema
- LLM 漏洞库分析 → 初始化素材库
- Harness 的 `run_standard_suite()` 改为从 Skill 获取策略
- 端到端链路跑通（Skill → Harness → Agent → Gateway → 记录）

**退出条件**：
- 至少 1 个攻击模式通过 Skill 调度执行
- 轨迹正确记录并回传给 Skill

### v0.3：WeightMatrix + CostBenefitModel

**目标**：历史数据驱动策略选择

**产物**：
- WeightMatrix 数据结构 + 更新逻辑
- CostBenefitModel 性价比计算
- Skill 查询流程中加入权重排序

**退出条件**：
- 第 N 次检测的 token 消耗 < 第 1 次检测（证明性价比递增）

### v0.4：FailureFingerprintLib + 自增强闭环 + ControlRequirementMapper

**目标**：失败模式可指纹化，L3 可映射为控制需求

**产物**：
- FailureFingerprintLib 指纹提取 + 匹配
- 自增强闭环（record_result → 分析 → 更新模式库）
- ControlRequirementMapper 基础实现

**退出条件**：
- 至少 1 个失败模式被自动提取并复用
- 至少 1 个 L3 被映射为控制需求（如果有 L3 样本）

### v0.5：数据隔离 + Embedding 索引

**目标**：模式抽象可安全导出，语义检索可用

**产物**：
- PublicPatternExporter
- Embedding 向量索引
- Schema + Embedding + LLM 三层查询流程完整实现

**退出条件**：
- 导出数据不含任何具体载荷
- 语义检索命中率 > Schema 精确匹配（证明 Embedding 有增量价值）

---

## 9. 当前文档结构建议（待后续执行）

| 文档 | 定位 | 内容 |
|---|---|---|
| core-idea-v0.md | 战略层 | 目标、原则、不变 |
| threat-model-v0.md | 攻击视角 | 角色、Seam、边界、失败分类 |
| system-interface-v0.md | 接口层 | architecture + trace-schema 合并 |
| terminal-architecture-design.md | 终态设计 | 本文档 |
| development-log.md | 实施记录 | 长期追加，不重构删减 |

**注**：文档重构为独立任务，不阻塞 v0.2 开发。
