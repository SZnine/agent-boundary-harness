import json
from pathlib import Path
from typing import Optional


class AttackPatternStore:
    """攻击模式存储：加载、查询"""

    def __init__(self):
        self._patterns: list[dict] = []
        self._index_by_id: dict[str, dict] = {}
        self._index_by_seam_boundary: dict[str, list[dict]] = {}

    def load_from_file(self, filepath: str) -> int:
        """从 JSON 文件加载 patterns"""
        path = Path(filepath)
        if not path.is_absolute():
            path = Path(__file__).resolve().parent.parent.parent / filepath
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        self._patterns = data.get("patterns", [])
        self._build_indexes()
        return len(self._patterns)

    def load_from_list(self, patterns: list[dict]):
        """直接加载 pattern 列表"""
        self._patterns = patterns
        self._build_indexes()

    def _build_indexes(self):
        """构建查询索引"""
        self._index_by_id = {}
        self._index_by_seam_boundary = {}
        for p in self._patterns:
            pid = p.get("pattern_id", "")
            self._index_by_id[pid] = p
            key = f"{p.get('seam', '')}-{p.get('boundary', '')}"
            self._index_by_seam_boundary.setdefault(key, []).append(p)

    def query(self, seam: str, boundary: str) -> list[dict]:
        """按 seam × boundary 精确匹配查询"""
        key = f"{seam}-{boundary}"
        return self._index_by_seam_boundary.get(key, [])

    def get_by_id(self, pattern_id: str) -> Optional[dict]:
        """按 pattern_id 查询"""
        return self._index_by_id.get(pattern_id)

    @property
    def total_count(self) -> int:
        return len(self._patterns)