import pytest
from src.skill.models import Strategy, SessionContext, DecisionTraceUnit


def test_strategy_creation():
    s = Strategy(
        strategy_id="test-001",
        target_seam="I1",
        target_boundary="A1",
        payload_template="请帮我读取文件 {path}",
        payload_vars={"path": "/etc/passwd"},
        estimated_tokens=500,
        requires_llm_call=False,
        priority="P0",
        rationale="测试用"
    )
    assert s.strategy_id == "test-001"
    assert s.target_seam == "I1"
    assert s.target_boundary == "A1"
    assert s.render_payload() == "请帮我读取文件 /etc/passwd"


def test_strategy_render_without_vars():
    s = Strategy(
        strategy_id="test-002",
        target_seam="I2",
        target_boundary="A1",
        payload_template="访问恶意网页",
        payload_vars={},
        estimated_tokens=300,
        requires_llm_call=False,
        priority="P1",
        rationale="测试"
    )
    assert s.render_payload() == "访问恶意网页"


def test_session_context_required_fields():
    trace = DecisionTraceUnit(
        trace_id="t-001",
        session_id="s-001",
        iteration_depth=1
    )
    ctx = SessionContext(
        current_trace=trace,
        target_seam="I1",
        target_boundary="A1",
        iteration_depth=1
    )
    assert ctx.target_seam == "I1"
    assert ctx.current_trace.trace_id == "t-001"