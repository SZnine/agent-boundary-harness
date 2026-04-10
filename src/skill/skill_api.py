from src.skill.models import Strategy, SessionContext
from src.skill.pattern_store import AttackPatternStore


class SkillAPI:
    """Skill 层对外接口"""

    def __init__(self, data_path: str = "data/attack_patterns.json"):
        self._store = AttackPatternStore()
        self._store.load_from_file(data_path)

    def get_next_strategy(self, context: SessionContext) -> Strategy | None:
        """
        根据 context 查询最匹配的攻击策略。
        v0.2：Schema 精确匹配（零成本），取第一个匹配结果。
        """
        patterns = self._store.query(
            seam=context.target_seam,
            boundary=context.target_boundary
        )

        if not patterns:
            return None

        best = patterns[0]

        return Strategy(
            strategy_id=best["pattern_id"],
            target_seam=best["seam"],
            target_boundary=best["boundary"],
            payload_template=best["pattern_description"],
            payload_vars={},
            estimated_tokens=500,
            requires_llm_call=False,
            priority="P1",
            rationale=f"ATLAS 映射: {best['atlas_mapping']['technique_id']} "
                      f"(置信度: {best['atlas_mapping']['mapped_confidence']})"
        )

    def record_result(self, trace: dict):
        """记录攻击结果。v0.2：仅打印日志。"""
        classification = trace.get("failure_classification", "?")
        trace_id = trace.get("trace_id", "?")
        print(f"[Skill] record_result: trace={trace_id}, classification={classification}")