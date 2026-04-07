"""
沙箱运行时 - 提供 fake tools 和副作用记录
"""

from .fake_tools import FakeToolRegistry, get_fake_tool_registry

__all__ = ["FakeToolRegistry", "get_fake_tool_registry"]
