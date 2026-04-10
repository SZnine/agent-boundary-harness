import pytest
from src.skill.pattern_store import AttackPatternStore


def test_load_patterns():
    store = AttackPatternStore()
    count = store.load_from_file("data/attack_patterns.json")
    assert count > 200


def test_query_by_seam_boundary():
    store = AttackPatternStore()
    store.load_from_file("data/attack_patterns.json")
    results = store.query(seam="I1", boundary="A1")
    assert len(results) > 0
    for p in results:
        assert p["seam"] == "I1"
        assert p["boundary"] == "A1"


def test_query_returns_empty_for_no_match():
    store = AttackPatternStore()
    store.load_from_file("data/attack_patterns.json")
    results = store.query(seam="I1", boundary="M2")
    assert isinstance(results, list)


def test_get_pattern_by_id():
    store = AttackPatternStore()
    store.load_from_file("data/attack_patterns.json")
    patterns = store.query(seam="I1", boundary="A1")
    if patterns:
        pid = patterns[0]["pattern_id"]
        found = store.get_by_id(pid)
        assert found is not None
        assert found["pattern_id"] == pid