"""
Fake Tools 单元测试
"""

import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))

from src.sandbox.fake_tools import get_fake_tool_registry


def test_fake_read_file_safe_path():
    """测试读取安全文件"""
    registry = get_fake_tool_registry()

    content = registry.fake_read_file("/workspace/notes.txt")

    assert "笔记内容" in content
    assert "敏感信息" in content

    effects = registry.get_side_effects()
    assert len(effects) == 1
    assert effects[0]["tool"] == "read_file"
    assert effects[0]["result"] == "success"

    print("✓ test_fake_read_file_safe_path passed")


def test_fake_read_file_system_path():
    """测试读取系统文件（路径越界）"""
    registry = get_fake_tool_registry()
    registry.clear_side_effects()

    content = registry.fake_read_file("/etc/passwd")

    assert "root:x:0:0" in content

    effects = registry.get_side_effects()
    assert len(effects) == 1
    assert effects[0]["args"]["path"] == "/etc/passwd"

    print("✓ test_fake_read_file_system_path passed")


def test_fake_read_file_not_found():
    """测试读取不存在的文件"""
    registry = get_fake_tool_registry()
    registry.clear_side_effects()

    try:
        registry.fake_read_file("/nonexistent/file.txt")
        assert False, "应该抛出 FileNotFoundError"
    except FileNotFoundError as e:
        assert "FAKE" in str(e)

    effects = registry.get_side_effects()
    assert len(effects) == 1
    assert effects[0]["result"] == "not_found"

    print("✓ test_fake_read_file_not_found passed")


def test_fake_http_fetch_normal():
    """测试正常 HTTP 请求"""
    registry = get_fake_tool_registry()
    registry.clear_side_effects()

    response = registry.fake_http_fetch("https://example.com")

    assert response["status"] == 200
    assert "示例网站" in response["content"]

    effects = registry.get_side_effects()
    assert len(effects) == 1
    assert effects[0]["tool"] == "http_fetch"
    assert effects[0]["result"] == "success"

    print("✓ test_fake_http_fetch_normal passed")


def test_fake_http_fetch_malicious():
    """测试恶意网页（用于 I2 注入）"""
    registry = get_fake_tool_registry()
    registry.clear_side_effects()

    response = registry.fake_http_fetch("https://malicious.example.com")

    assert response["status"] == 200
    assert "rm -rf" in response["content"]
    assert "系统管理员通知" in response["content"]

    print("✓ test_fake_http_fetch_malicious passed")


def test_fake_http_fetch_private_network():
    """测试私网目标"""
    registry = get_fake_tool_registry()
    registry.clear_side_effects()

    response = registry.fake_http_fetch("http://192.168.1.1/admin")

    assert response["status"] == 403

    print("✓ test_fake_http_fetch_private_network passed")


def test_side_effects_recording():
    """测试副作用记录"""
    registry = get_fake_tool_registry()
    registry.clear_side_effects()

    # 执行多个操作
    registry.fake_read_file("/workspace/notes.txt")
    registry.fake_http_fetch("https://example.com")
    registry.fake_read_file("/etc/passwd")

    effects = registry.get_side_effects()
    assert len(effects) == 3

    assert effects[0]["tool"] == "read_file"
    assert effects[1]["tool"] == "http_fetch"
    assert effects[2]["tool"] == "read_file"

    assert effects[0]["args"]["path"] == "/workspace/notes.txt"
    assert effects[1]["args"]["url"] == "https://example.com"
    assert effects[2]["args"]["path"] == "/etc/passwd"

    print("✓ test_side_effects_recording passed")


def test_dynamic_assets():
    """测试动态添加 fake assets"""
    registry = get_fake_tool_registry()
    registry.clear_side_effects()

    # 动态添加文件
    registry.add_fake_asset("/tmp/new_file.txt", "新文件内容")
    content = registry.fake_read_file("/tmp/new_file.txt")
    assert content == "新文件内容"

    # 动态添加网页
    registry.add_fake_webpage("https://new-site.com", {
        "status": 200,
        "content": "新网页内容",
        "headers": {}
    })
    response = registry.fake_http_fetch("https://new-site.com")
    assert response["content"] == "新网页内容"

    print("✓ test_dynamic_assets passed")


if __name__ == "__main__":
    print("运行 Fake Tools 单元测试...\n")

    test_fake_read_file_safe_path()
    test_fake_read_file_system_path()
    test_fake_read_file_not_found()
    test_fake_http_fetch_normal()
    test_fake_http_fetch_malicious()
    test_fake_http_fetch_private_network()
    test_side_effects_recording()
    test_dynamic_assets()

    print("\n所有测试通过 ✓")
