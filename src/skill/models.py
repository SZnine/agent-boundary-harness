from dataclasses import dataclass, field
from typing import Dict, Optional


@dataclass
class DecisionTraceUnit:
    """传递给 Skill 的最小轨迹信息"""
    trace_id: str
    session_id: str
    iteration_depth: int


@dataclass
class SessionContext:
    """Skill 查询上下文"""
    current_trace: DecisionTraceUnit
    target_seam: str  # I1~I5
    target_boundary: str  # A1/A2/A3/M1/M2
    iteration_depth: int
    session_history_summary: Optional[str] = None


@dataclass
class Strategy:
    """Skill 返回的攻击策略"""
    strategy_id: str
    target_seam: str
    target_boundary: str
    payload_template: str
    payload_vars: Dict[str, str] = field(default_factory=dict)
    estimated_tokens: int = 0
    requires_llm_call: bool = False
    priority: str = "P2"
    rationale: str = ""

    def render_payload(self) -> str:
        """渲染 payload 模板"""
        result = self.payload_template
        for key, value in self.payload_vars.items():
            result = result.replace(f"{{{key}}}", value)
        return result