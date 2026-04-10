# 系统接口 v0

**状态：v0 冻结**
**用途：定义组件间的接口、数据结构和工作流，作为实现的共同基准**
**依赖文档**：
- 威胁模型：[threat-model-v0.md](threat-model-v0.md)（角色、Seam、边界、失败分类）
- 终态架构：[superpowers/specs/2026-04-10-terminal-architecture-design.md](superpowers/specs/2026-04-10-terminal-architecture-design.md)（Skill/Harness 分层设计）

---

## 一、整体架构（v0.1 阶段）

```
┌─────────────────────────────────────────────────────────────┐
│  Harness                                                     │
│  ├─ attack_context: {seam, payload, depth, probe_direction}│
│  ├─ continuation_decision: {requires_deeper_probe, cost,    │
│  │                             stop_reason}                 │
│  └─ output: attack_report                                   │
│                        │                                     │
│                        │ injection (I1~I5)                  │
│                        ▼                                     │
│  ┌─────────────────────────────────────────────────────────┐│
│  │  被测 Agent（外部）                                       ││
│  │  └─ 不修改 Harness 代码，接口通过标准化 payload 注入      ││
│  └─────────────────────────┬───────────────────────────────┘│
│                            │ tool call                       │
│                            ▼                                 │
│  ┌─────────────────────────────────────────────────────────┐│
│  │  沙箱运行时（Sandbox Runtime）                           ││
│  │  ├─ tool registry（可注入 fake tool）                   ││
│  │  ├─ asset store（fake files / webpages / docs）          ││
│  │  └─ side effect recorder（记录所有副作用）               ││
│  └─────────────────────────┬───────────────────────────────┘│
│                            │ request                         │
│                            ▼                                 │
│  ┌─────────────────────────────────────────────────────────┐│
│  │  Gateway（外部）                                         ││
│  │  ├─ handle_request() → normalize → policy → execute    ││
│  │  └─ 事件流推送到 Harness                                 ││
│  └─────────────────────────┬───────────────────────────────┘│
│                            │ event stream                   │
│                            ▼                                 │
│  ┌─────────────────────────────────────────────────────────┐│
│  │  轨迹存储（Trace Store）                                 ││
│  │  └─ Decision Trace Unit × N → Attack Session            ││
│  └─────────────────────────────────────────────────────────┘│
```

---

## 二、三阶段工作流

```
┌──────────────────────────────────────────────────────┐
│  阶段一：标准测试（Standard Suite）                    │
│                                                      │
│  输入：预置攻击用例集（v0.1: 4 个用例）                  │
│  过程：Harness 逐个执行，记录每次攻击的结果              │
│  输出：结构化攻击测评报告                              │
│         - 每条: 攻击方式 / 结果 / 分类                  │
│         - 高价值点: requires_deeper_probe             │
│           + probe_direction + estimated_cost          │
└──────────────────────────┬───────────────────────────┘
                           │ 用户审计
                           ▼
┌──────────────────────────────────────────────────────┐
│  阶段二：深入个性化测试（On-demand Deep Dive）          │
│                                                      │
│  输入：用户授权的探测方向                              │
│  过程：Harness 按需迭代（iteration_depth += 1）        │
│        每次迭代输出显式：                              │
│          - probe_direction（演进方向）                 │
│          - estimated_cost（预估成本）                  │
│          - evolution_reason（理由）                    │
│          - requires_deeper_probe                     │
│  输出：深度攻击测评报告                                │
│  控制：用户可随时终止或调整方向                        │
└──────────────────────────┬───────────────────────────┘
                           │ L3 目标产出
                           ▼
┌──────────────────────────────────────────────────────┐
│  阶段三：风险评估 + 控制方案                          │
│                                                      │
│  L3 → 控制面优化方案（进入 Gateway backlog）          │
│  L2 → 记录待处理                                      │
│  L1 → 忽略                                            │
└──────────────────────────────────────────────────────┘
```

---

## 三、接口清单（HTTP API）

| 接口 | 方向 | 说明 |
|---|---|---|
| `POST /harness/attack` | Harness → Agent | 向被测 Agent 注入攻击载荷 |
| `GET /gateway/events` | Gateway → Harness | 订阅 Gateway 事件流 |
| `POST /harness/session/start` | Harness → Harness | 开始攻击会话 |
| `POST /harness/session/end` | Harness → Harness | 结束攻击会话，产出测评报告 |
| `GET /harness/report/<session_id>` | Harness → 用户 | 获取结构化攻击测评报告 |
| `POST /harness/deep_dive/authorize` | 用户 → Harness | 用户授权深度测试方向 |

---

## 四、轨迹数据结构

### Decision Trace Unit（单次攻击）

```json
{
  "trace_id": "uuid",
  "session_id": "uuid",
  "iteration_depth": 1,
  "task_id": "...",

  "attack_context": {
    "injected_seam": "I1",
    "attack_payload_snippet": "...",
    "probe_direction": "..."
  },

  "gateway_request": {
    "tool_name": "调用的工具名",
    "args": "参数（脱敏后）",
    "args_boundary_valid": "参数是否满足边界要求"
  },

  "gateway_decision": {
    "decision": "ALLOW | DENY",
    "reason": "具体原因",
    "matched_rule": "命中的规则名",
    "matched_at": "A1 | A2 | A3"
  },

  "execution_result": {
    "executed": "是否实际执行",
    "success": "执行是否成功",
    "output_snippet": "输出的前 200 字符",
    "side_effects": ["产生的副作用列表"]
  },

  "continuation_decision": {
    "requires_deeper_probe": true | false,
    "estimated_cost": "0.5h / 低",
    "stop_reason": null
  },

  "failure_classification": {
    "layer": "L1 | L2 | L3",
    "control_gap": "缺失的控制描述"
  }
}
```

### Attack Session（完整会话）

```json
{
  "session_id": "uuid",
  "phase": "standard | deep_dive | risk_assessment",
  "initial_task": "...",
  "iteration_chain": [ /* Decision Trace Unit[] */ ],
  "final_classification": "L3",
  "control_requirement_id": "CR-001",
  "max_iteration_depth": 2
}
```

> 详细字段说明见 [threat-model-v0.md](threat-model-v0.md) 第 2 节。

---

## 五、事件流（Event Stream）

### 5.1 Gateway 事件流

```
REQUEST_RECEIVED
    ↓
REQUEST_NORMALIZED
    ↓
POLICY_DECIDED
    ↓
REQUEST_DENIED      ← A1/A2 层拒绝
    OR
EXECUTION_STARTED
    ↓
EXECUTION_FINISHED  ← A3 层成功
    OR
EXECUTION_FAILED    ← A3 层失败
```

### 5.2 Harness 攻击事件流

```
ATTACK_SESSION_STARTED   ← Harness 开始一个攻击会话
    ↓
ATTACK_PAYLOAD_INJECTED ← Harness 向被测 Agent 注入攻击载荷
    ↓
AGENT_RESPONSE_OBSERVED ← Harness 观察到被测 Agent 的响应
    ↓
GATEWAY_DECISION_OBSERVED ← Harness 观察到 Gateway 的决策
    ↓
TRACE_RECORDED          ← 轨迹已记录
    ↓
┌───┴───┐
↓        ↓
L1/L2   L3
↓        ↓
进化   记录控制需求
↓
ATTACK_SESSION_ENDED ← 攻击会话结束
```

| Harness 事件 | 含义 |
|---|---|
| `ATTACK_SESSION_STARTED` | Harness 开始一个针对某边界/Seam 的攻击会话 |
| `ATTACK_PAYLOAD_INJECTED` | Harness 成功向被测 Agent 注入了恶意内容 |
| `AGENT_RESPONSE_OBSERVED` | 被测 Agent 对攻击载荷产生了响应（调用了 Gateway）|
| `GATEWAY_DECISION_OBSERVED` | Gateway 对 Agent 请求做出了决策 |
| `TRACE_RECORDED` | 轨迹已写入存储 |
| `EVOLUTION_TRIGGERED` | Harness 决定演化到下一阶攻击 |
| `CONTROL_GAP_IDENTIFIED` | 发现 L3，产出控制需求 |
| `ATTACK_SESSION_ENDED` | 攻击会话结束 |

---

## 六、轨迹采集接口

### 接口 1：事件流订阅
```
Harness 订阅 Gateway 的事件流
每次 EventType 变化时，Gateway 推送到 Harness
```

### 接口 2：请求快照
```
GET /gateway/request/<request_id>
返回该 request_id 对应的完整轨迹片段
```

### 接口 3：轨迹查询
```
POST /gateway/traces/query
Body: { "task_id": "...", "step_range": [0, 10] }
返回指定任务的时间序轨迹列表
```

### 接口 4：攻击载荷注入
```
POST /harness/inject
Body: { "target_agent_id": "...", "seam": "I1~I5", "payload": "...", "session_id": "..." }
Harness 向被测 Agent 注入攻击载荷
```

### 接口 5：攻击会话管理
```
POST /harness/session/start
Body: { "target_boundary": "A1", "target_seam": "I1", "initial_task": "..." }
开始一个攻击会话

POST /harness/session/<session_id>/evolve
Body: { "parent_trace_id": "...", "evolution_reason": "...", "next_payload": "..." }
从当前阶演化到下一阶攻击

POST /harness/session/<session_id>/end
Body: { "final_classification": "L3", "control_requirement_id": "..." }
结束攻击会话
```

---

## 七、关键设计决策

| 决策 | 选择 | 理由 |
|---|---|---|
| 迭代决策权 | 用户审计 + 授权 | 避免 Harness 自主迭代引入不可预期的复杂攻击；成本和价值判断需要人工权衡 |
| 攻击深度标记 | iteration_depth（非固定阶数）| 保留扩展空间，具体走多深由实际风险价值决定 |
| L3 触发阈值 | L3 = 直接产出控制方案 | v0.1 先跑通，宁多不漏 |
| 标准测试集大小 | 4 个用例（v0.1）| 平衡覆盖和启动成本，保留扩展空间 |
| 成本量化 | 定性 + iteration_depth | 避免过早量化失真，用定性判断 + 深度足够支撑决策 |

---

## 八、当前能力 vs 需求（v0.1 阶段）

| 维度 | Gateway 当前 | Harness 当前 | 缺口 |
|---|---|---|---|
| request_id 全链路贯穿 | ✅ | ✅ | — |
| 事件类型枚举 | ✅ 8 种 | ❌ Harness 事件未定义 | 需要定义 Harness 事件 |
| 决策原因 | ✅ reason | ✅ | reason 过于简单 |
| 轨迹持久化 | ❌ 内存 | ❌ | 无持久化和查询接口 |
| 任务上下文 | ❌ task_id | ❌ | 无法跨请求关联同一任务 |
| 步骤序号 | ❌ step_id | ❌ | 无法还原决策顺序 |
| 漂移检测 | ❌ | ❌ | 无法判断目标是否漂移 |
| 输入来源标注 | ❌ | ❌ | 不知道输入来自哪个 I-seam |
| **攻击演化链** | ❌ | ❌ | **无法追踪多阶演化** |
| **控制需求产出** | ❌ | ❌ | **无 L3 → 控制需求链路** |
| **回归用例映射** | ❌ | ❌ | **无 regression_case_id** |

---

## 九、未来扩展预留

- M1/M2 记忆污染深度测试
- I3 文档注入 / I4 检索结果注入
- 多 Agent 交互边界
- 审批 / 工作流边界
- 风险评分（严重度 P0/P1/P2）
- 回归用例自动生成
