# Skill Agent 设计规范

**日期**：2026-04-13
**状态**：设计完成，待实现
**版本**：v0.1

---

## 一、目标

将 Skill 从"调度模块"升级为**自主 Skill Agent**。

Skill Agent 是一个能自主驱动完整测试闭环的智能体：接收高层目标 → 自主做技术决策 → 执行测试 → 提炼产出 → 向人汇报，全程在 token 约束内，只在关键节点向人请求授权。

**核心原则**：人的角色是审计者，不是技术决策者。所有推理过程由 Skill Agent 完成，推理结果向人显式，人只判断是否同意。

---

## 二、整体架构

```
┌─────────────────────────────────────────────────────────────┐
│                      Skill Agent                             │
│                                                              │
│  ┌─────────────┐    ┌─────────────┐    ┌─────────────┐    │
│  │  审计级别   │───▶│  循环体     │───▶│  抽象层     │    │
│  │  配置器     │    │  (5阶段)    │    │  (记忆)     │    │
│  └─────────────┘    └──────┬──────┘    └──────┬──────┘    │
│                            │                   │             │
│                            ▼                   │             │
│                     ┌─────────────┐            │             │
│                     │  弹框输出   │◀───────────┘             │
│                     │  (人审计)  │                         │
│                     └──────┬──────┘                         │
└────────────────────────────┼────────────────────────────────┘
                             │
                             ▼
              ┌──────────────────────────────┐
              │         Harness 执行层          │
              │  TargetAgent + MockGateway    │
              │         + FakeTools            │
              └──────────────────────────────┘
```

---

## 三、循环体（5阶段）

Skill Agent 自主循环执行以下 5 个阶段：

```
[选择目标] → [执行测试] → [分析结果] → [提炼产出] → [决定下一步]
     ▲                                                          │
     └──────────────────────────────────────────────────────────┘
```

### 阶段 1：选择目标

**Skill Agent 做的事**：
- 读取抽象层（覆盖矩阵、权重矩阵、历史测试记录）
- 自主推理"下一个最优目标"（seam × boundary × 攻击策略）
- 自主选择推荐逻辑（覆盖率优先 or 靶向优先 or 平衡）
- 输出弹框：**推荐目标 + 推荐理由 + 预估 token 消耗**

**人的审计点**：是否同意这个推荐

### 阶段 2：执行测试

**Skill Agent 做的事**：
- 构造/渲染攻击载荷
- 调用 Harness 执行测试
- 记录每次工具调用的 Gateway 决策
- 收集分类结果（L1/L2/L3）

**弹框触发**：按 seam×boundary 组合跑完**一组**后汇报，不逐用例弹框

**弹框内容**：本次组测试汇总（用例数、L1/L2/L3 分布、实际 token 消耗）

**人的审计点**：同意继续 / 要求终止 / 修改预算

### 阶段 3：分析结果

**Skill Agent 做的事**：
- 对 L2 结果调用 LLM 提炼 failure pattern
- 对 L1 结果调用 LLM 提炼 defense pattern
- 如有 L3，标记为强制审计项
- 将提炼结果与经验库已有 pattern 对比（新增/去重/更新）
- 更新权重矩阵（自动，无需审计）

**弹框内容（必须项）**：
- 本次分析 token 消耗
- 下一个推荐目标 + 理由
- L3 特殊标记（如有）

**弹框触发**：一组测试分析完成后

**人的审计点**：L3 强制审计；下一目标推荐是否合理

### 阶段 4：提炼产出

**Skill Agent 做的事**：
- 基于提炼出的 failure pattern，生成 Gateway Control Requirements
- 追加 pattern 到 failure_patterns.json（需审计）
- 追加 GCR 到 gateway_control_requirements.json（需审计）

**审计规则**：
- pattern 追加 → 必须审计
- GCR 产出 → 必须审计

### 阶段 5：决定下一步

**Skill Agent 做的事**：
- 根据审计级别决定下一步动作
- 读取人的审计决策
- 返回阶段 1 继续循环，或终止并输出最终报告

---

## 四、审计级别

Skill Agent 初始化时，人选择审计级别，之后全程按该级别执行：

| 级别 | 名称 | 弹框频率 | 说明 |
|---|---|---|---|
| 1 | 极简 | 仅 L3 发现和超预算时 | 人干预最少，Skill Agent 自主跑完整个目标 |
| 2 | 标准 | 每组结束时 + L3 + 超预算 | 平衡干预，每组汇报后自动续跑下一组 |
| 3 | 细致 | 每组开始前确认 + 结束后汇报 + L3 + 超预算 | 每组开始都确认，下一组不自动续跑 |
| 4 | 全程 | 每个技术决策节点 | 最大干预，每个步骤都审计 |

**所有审计级别的通用触发点**（不可绕过）：
- 发现 L3（必须人审计后才能产出 GCR）
- 实际消耗超过预估（必须人同意追加预算）

---

## 五、核心产出

Skill Agent 的最终产出物：

| 产出物 | 内容 | 更新方式 |
|---|---|---|
| failure_patterns.json | fp-*（L2 失败模式）+ dp-*（L1 防御模式） | 提炼后需人审计追加 |
| gateway_control_requirements.json | GCR 规范（控制需求 + 实施优先级） | 提炼后需人审计追加 |
| 权重矩阵 | seam×boundary → 命中率 | 自动更新 |
| 成本效益模型 | 发现率 / token 消耗 | 自动更新 |
| 测试轨迹 | 完整 trace JSON（含 Agent 响应 + 工具调用链） | 自动追加 |

---

## 六、数据模型

### AuditDecision

```python
@dataclass
class AuditDecision:
    decision: str           # "approved" | "rejected" | "modified"
    modifier: str = ""     # 如果是 modified，记录修改内容
    reason: str = ""       # 人的决策理由
    timestamp: str
```

### AuditLevel

```python
class AuditLevel(Enum):
    MINIMAL = 1      # 极简：仅 L3 + 超预算
    STANDARD = 2     # 标准：每组 + L3 + 超预算
    DETAILED = 3     # 细致：每组开始确认 + 结束后汇报
    FULL = 4         # 全程：每个节点
```

### SkillAgentSession

```python
@dataclass
class SkillAgentSession:
    session_id: str
    audit_level: AuditLevel
    goal: str                    # 人给的高层目标
    budget_tokens: int            # 人给的 token 预算
    consumed_tokens: int = 0      # 累计消耗

    # 抽象层状态
    weight_matrix: dict          # seam×boundary → hit_rate
    pattern_db: list             # 当前 pattern 列表
    gcr_db: list                 # 当前 GCR 列表

    # 当前循环状态
    current_stage: str           # "select" | "test" | "analyze" | "refine" | "decide"
    current_group: tuple          # (seam, boundary) 当前正在测的组
    completed_groups: list       # 已完成的组列表
    pending_audit: AuditDecision | None  # 待人审计的决策
```

### AuditPopup

```python
@dataclass
class AuditPopup:
    stage: str                   # 触发弹框的阶段
    title: str                   # 弹框标题
    summary: str                 # Skill Agent 的汇报摘要
    options: list[str]           # 供人选择的操作（approved/rejected/modified）
    token_cost: int              # 本次消耗
    cumulative_cost: int         # 累计消耗
    l3_flag: bool = False        # L3 发现标记
    next_recommendation: str = "" # 下一推荐（分析阶段填）
    details: dict = {}           # 详细信息（pattern 内容等）
```

---

## 七、Skill Agent 的内部推理（向人显式的部分）

Skill Agent 在做技术决策时，以下推理过程需要向人显式说明：

| 决策 | 显式内容 |
|---|---|
| 选择下一目标 | 推荐的目标 + 推荐理由 + 使用的推荐逻辑 + 预估消耗 |
| 判断是否继续迭代 | 理由 + 预估额外消耗 |
| LLM 分析结果 | 分析消耗 + 提炼出的 pattern 摘要 |
| GCR 提炼 | 提炼依据 + 对应的 failure pattern + 控制点描述 |
| 超预算判断 | 实际 vs 预估对比 + 剩余预算 + 继续/停止建议 |

---

## 八、实现优先级

| 优先级 | 组件 | 说明 |
|---|---|---|
| P0 | SkillAgent 主循环体 | 5阶段循环，标准级审计，每组结束后弹框汇报 |
| P0 | 审计弹框界面 | 文本格式输出到 stdout（可升级为 TUI/GUI） |
| P0 | 抽象层持久化 | Skill Agent 状态保存到 JSON |
| P1 | 审计级别实现 | 4 级弹框频率控制 |
| P1 | LLM 分析自动化 | 无缝集成 analyze_failures() |
| P2 | 权重矩阵自动更新 | 测试结果自动更新命中率 |
| P2 | GCR 自动提炼 | L2 → GCR 自动化（目前是人肉做） |
| P3 | 多 Agent 协作 | 不同 Agent 做不同阶段（规划/执行/分析） |

---

## 九、与人交互的典型对话

**极简级（审计级别 1）**：

```
[Skill Agent]
目标：测绘 I4×A2 边界，预算 50k tokens
推荐：I4-A2（检索结果 × A2 参数边界）
理由：I4 seam 完全未覆盖，A2 在其他 seam 上命中率 60%
预估：15k tokens
是否同意？

> [人] 同意

[Skill Agent] 执行中... 消耗 15k tokens
结果：L2 × 2，Gateway DENY（A2 路径边界）
推荐追加：I4-A3（检索结果 × A3 副作用）
预估追加：12k tokens

> [人] 同意

[Skill Agent] 执行中... 消耗 12k tokens
结果：L1 × 1（Agent 主动拒绝）
推荐：I4 方向已覆盖 A2/A3，建议转向 M2

> [人] 同意继续测 M2

[Skill Agent] 预算已耗尽（27k / 50k），I4/M2 部分覆盖。
最终产出：2 条 failure_patterns，1 条 GCR。
```

---

## 十、验收条件

1. Skill Agent 能完整跑完一个组（选目标→测→分析→汇报），无需人中途干预（标准级）
2. 弹框内容符合设计（必须项不遗漏，可选项可裁剪）
3. L3 发现时，所有审计级别都强制触发弹框
4. 权重矩阵在每次测试后自动更新
5. 产出的 pattern 格式符合 failure_patterns.json 规范
6. Skill Agent 能从中断点恢复（session 持久化）
