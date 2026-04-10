import pytest
from src.skill.skill_api import SkillAPI
from src.skill.models import Strategy, SessionContext, DecisionTraceUnit


def _make_context(seam="I1", boundary="A1", depth=1) -> SessionContext:
    return SessionContext(
        current_trace=DecisionTraceUnit(
            trace_id="t-001",
            session_id="s-001",
            iteration_depth=depth
        ),
        target_seam=seam,
        target_boundary=boundary,
        iteration_depth=depth
    )


def test_get_strategy_returns_strategy():
    api = SkillAPI(data_path="data/attack_patterns.json")
    ctx = _make_context("I1", "A1")
    strategy = api.get_next_strategy(ctx)
    assert isinstance(strategy, Strategy)
    assert strategy.target_seam == "I1"
    assert strategy.target_boundary == "A1"
    assert strategy.strategy_id != ""
    assert strategy.payload_template != ""


def test_get_strategy_with_no_match():
    api = SkillAPI(data_path="data/attack_patterns.json")
    ctx = _make_context("I1", "M3")
    strategy = api.get_next_strategy(ctx)
    assert strategy is None


def test_record_result_does_not_crash():
    api = SkillAPI(data_path="data/attack_patterns.json")
    api.record_result({
        "trace_id": "t-001",
        "failure_classification": "L2"
    })