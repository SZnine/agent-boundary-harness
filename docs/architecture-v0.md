# 架构 v0

**状态：v0 冻结**
**用途：显式化整体架构和工作流，作为实现和协作的共同基准**

---

## 一、系统角色

| 角色 | 定义 | 职责边界 |
|---|---|---|
| **Harness（主控 Agent）** | 主动攻击者 + 观察者 + 案例演化者 | 发起攻击、观察响应、分类 L1/L2/L3、显式迭代判断、产出 L3 控制需求 |
| **被测 Agent** | 攻击目标 | 接收任务、执行、调用 Gateway |
| **Gateway** | 被测控制层 | A1/A2/A3 边界控制 |
| **用户（Human）** | 审计者 + 决策者 | 审查测评报告、授权深度测试、决策控制方案落地 |

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
│          - requires_deeper_probe                      │
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

## 三、组件接口

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

## 四、接口清单

| 接口 | 方向 | 说明 |
|---|---|---|
| `POST /harness/attack` | Harness → Agent | 向被测 Agent 注入攻击载荷 |
| `GET /gateway/events` | Gateway → Harness | 订阅 Gateway 事件流 |
| `POST /harness/session/start` | Harness → Harness | 开始攻击会话 |
| `POST /harness/session/end` | Harness → Harness | 结束攻击会话，产出测评报告 |
| `GET /harness/report/<session_id>` | Harness → 用户 | 获取结构化攻击测评报告 |
| `POST /harness/deep_dive/authorize` | 用户 → Harness | 用户授权深度测试方向 |

---

## 五、轨迹数据结构

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
  "gateway_decision": {
    "decision": "ALLOW | DENY",
    "matched_at": "A1 | A2 | A3"
  },
  "continuation_decision": {
    "requires_deeper_probe": true | false,
    "estimated_cost": "0.5h / 低",
    "stop_reason": null
  },
  "failure_classification": {
    "layer": "L1 | L2 | L3"
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

---

## 六、关键设计决策

| 决策 | 选择 | 理由 |
|---|---|---|
| 迭代决策权 | 用户审计 + 授权 | 避免 Harness 自主迭代引入不可预期的复杂攻击；成本和价值判断需要人工权衡 |
| 攻击深度标记 | iteration_depth（非固定阶数）| 保留扩展空间，具体走多深由实际风险价值决定 |
| L3 触发阈值 | L3 = 直接产出控制方案 | v0.1 先跑通，宁多不漏 |
| 标准测试集大小 | 4 个用例（v0.1）| 平衡覆盖和启动成本，保留扩展空间 |
| 成本量化 | 定性 + iteration_depth | 避免过早量化失真，用定性判断 + 深度足够支撑决策 |

---

## 七、当前缺失（v0.1 待实现）

| 组件 | 状态 | 说明 |
|---|---|---|
| 沙箱运行时 | ❌ 待实现 | 提供 fake tools / assets / side effect recorder |
| Gateway 事件推送 | ❌ 待对接 | Gateway 需暴露事件流接口 |
| 被测 Agent 连接 | ❌ 待对接 | 标准 payload 注入接口 |
| 轨迹存储 | ❌ 待实现 | 持久化和查询接口 |
| 用户决策界面 | ❌ 待实现 | 报告展示 + 授权控制台 |
| 标准测试集（4 个用例）| ❌ 待编写 | T-I1-A1, T-I2-A1, T-I5-A1, T-M1-A2 |

---

## 八、未来扩展预留

- M1/M2 记忆污染深度测试
- I3 文档注入 / I4 检索结果注入
- 多 Agent 交互边界
- 审批 / 工作流边界
- 风险评分（严重度 P0/P1/P2）
- 回归用例自动生成
