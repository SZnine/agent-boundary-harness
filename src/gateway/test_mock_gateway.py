"""
Mock Gateway 单元测试

覆盖 Gateway v0.1 的 6 个核心测试用例：
- T01: 非白名单工具拒绝
- T02: 路径越界拒绝
- T03: 私网目标拒绝
- T04: 合法读取成功
- T05: normalization 失败
- T06: 执行失败
"""

import sys
import os

# Fix Windows console encoding
if sys.platform == 'win32':
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8')
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))

from src.sandbox.fake_tools import get_fake_tool_registry
from src.gateway.mock_gateway import MockGateway, GatewayState, Decision


def setup_gateway():
    """创建测试用的 Gateway 实例"""
    fake_tools = get_fake_tool_registry()
    fake_tools.clear_side_effects()
    return MockGateway(fake_tools)


def test_t01_tool_not_in_whitelist():
    """T01: 非白名单工具拒绝 (DENY)"""
    gateway = setup_gateway()

    response = gateway.handle_request({
        "tool_name": "delete_file",
        "args": {"path": "/workspace/file.txt"}
    })

    assert response["state"] == GatewayState.DENIED.value
    assert response["decision"] == Decision.DENY.value
    assert response["reason"] == "tool_not_in_whitelist"
    assert response["matched_at"] == "A1"
    assert response["executed"] == False

    print("✓ T01: 非白名单工具拒绝")


def test_t02_path_outside_safe_dir():
    """T02: 路径越界拒绝 (DENY)"""
    gateway = setup_gateway()

    response = gateway.handle_request({
        "tool_name": "read_file",
        "args": {"path": "/etc/passwd"}
    })

    assert response["state"] == GatewayState.DENIED.value
    assert response["decision"] == Decision.DENY.value
    assert response["reason"] == "path_outside_safe_dir"
    assert response["matched_at"] == "A2"
    assert response["executed"] == False

    print("✓ T02: 路径越界拒绝")


def test_t03_private_network_target():
    """T03: 私网目标拒绝 (DENY)"""
    gateway = setup_gateway()

    response = gateway.handle_request({
        "tool_name": "http_fetch",
        "args": {"url": "http://127.0.0.1/admin"}
    })

    assert response["state"] == GatewayState.DENIED.value
    assert response["decision"] == Decision.DENY.value
    assert response["reason"] == "private_or_loopback_target"
    assert response["matched_at"] == "A2"
    assert response["executed"] == False

    print("✓ T03: 私网目标拒绝")


def test_t04_valid_read_success():
    """T04: 合法读取成功 (ALLOW -> SUCCEEDED)"""
    gateway = setup_gateway()

    response = gateway.handle_request({
        "tool_name": "read_file",
        "args": {"path": "/workspace/notes.txt"}
    })

    assert response["state"] == GatewayState.SUCCEEDED.value
    assert response["decision"] == Decision.ALLOW.value
    assert response["reason"] == "execution_succeeded"
    assert response["matched_at"] == "A3"
    assert response["executed"] == True
    assert "笔记内容" in response["output"]

    print("✓ T04: 合法读取成功")


def test_t05_normalization_failure():
    """T05: normalization 失败 (FAILED)"""
    gateway = setup_gateway()

    response = gateway.handle_request({
        "tool_name": "read_file",
        "args": "not_a_dict"  # 非法参数类型
    })

    assert response["state"] == GatewayState.FAILED.value
    assert response["decision"] is None
    assert "normalization_failed" in response["reason"]
    assert response["matched_at"] == "A2"
    assert response["executed"] == False

    print("✓ T05: normalization 失败")


def test_t06_execution_failure():
    """T06: 执行失败 (ALLOW -> FAILED)"""
    gateway = setup_gateway()

    # 请求一个不存在的文件（在 safe dir 内，但文件不存在）
    response = gateway.handle_request({
        "tool_name": "read_file",
        "args": {"path": "/workspace/nonexistent.txt"}
    })

    assert response["state"] == GatewayState.FAILED.value
    assert response["decision"] == Decision.ALLOW.value
    assert "execution_failed" in response["reason"]
    assert response["matched_at"] == "A3"
    assert response["executed"] == True  # 尝试执行了，但失败

    print("✓ T06: 执行失败")


def test_event_logging():
    """测试事件日志记录"""
    gateway = setup_gateway()

    # 执行一个请求
    response = gateway.handle_request({
        "tool_name": "read_file",
        "args": {"path": "/workspace/notes.txt"}
    })

    request_id = response["request_id"]

    # 获取该请求的事件
    events = gateway.get_events(request_id)
    assert len(events) >= 4  # RECEIVED, NORMALIZED, ALLOWED, EXECUTING, SUCCEEDED

    # 验证状态流转
    states = [e["state"] for e in events]
    assert GatewayState.RECEIVED.value in states
    assert GatewayState.NORMALIZED.value in states
    assert GatewayState.ALLOWED.value in states
    assert GatewayState.SUCCEEDED.value in states

    print("✓ 事件日志记录")


def test_http_fetch_success():
    """测试 http_fetch 成功"""
    gateway = setup_gateway()

    response = gateway.handle_request({
        "tool_name": "http_fetch",
        "args": {"url": "https://example.com"}
    })

    assert response["state"] == GatewayState.SUCCEEDED.value
    assert response["decision"] == Decision.ALLOW.value
    assert response["executed"] == True
    assert response["output"]["status"] == 200

    print("✓ http_fetch 成功")


def test_http_fetch_invalid_scheme():
    """测试 http_fetch 非法 scheme"""
    gateway = setup_gateway()

    response = gateway.handle_request({
        "tool_name": "http_fetch",
        "args": {"url": "ftp://example.com"}
    })

    assert response["state"] == GatewayState.DENIED.value
    assert response["decision"] == Decision.DENY.value
    assert response["reason"] == "invalid_url_scheme"

    print("✓ http_fetch 非法 scheme")


if __name__ == "__main__":
    print("运行 Mock Gateway 单元测试...\n")

    test_t01_tool_not_in_whitelist()
    test_t02_path_outside_safe_dir()
    test_t03_private_network_target()
    test_t04_valid_read_success()
    test_t05_normalization_failure()
    test_t06_execution_failure()
    test_event_logging()
    test_http_fetch_success()
    test_http_fetch_invalid_scheme()

    print("\n所有测试通过 ✓")
