"""
Mock Gateway - 模拟 Gateway v0.1 的三条主路径

基于 agent-security-gateway v0.1 的 6 个测试用例设计：
- T01: 非白名单工具拒绝 (DENY)
- T02: 路径越界拒绝 (DENY)
- T03: 私网目标拒绝 (DENY)
- T04: 合法读取成功 (ALLOW)
- T05: normalization 失败 (DENY)
- T06: 执行失败 (ALLOW -> FAILED)

状态机：
RECEIVED -> NORMALIZED -> POLICY_CHECKING -> DENIED / ALLOWED -> EXECUTING -> SUCCEEDED / FAILED
"""

from typing import Dict, Any, List, Optional
from enum import Enum
from datetime import datetime
import uuid


class GatewayState(Enum):
    """Gateway 状态"""
    RECEIVED = "RECEIVED"
    NORMALIZED = "NORMALIZED"
    POLICY_CHECKING = "POLICY_CHECKING"
    DENIED = "DENIED"
    ALLOWED = "ALLOWED"
    EXECUTING = "EXECUTING"
    SUCCEEDED = "SUCCEEDED"
    FAILED = "FAILED"


class Decision(Enum):
    """决策结果"""
    ALLOW = "ALLOW"
    DENY = "DENY"


class MockGateway:
    """
    Mock Gateway 实现

    模拟 Gateway v0.1 的核心功能：
    - 工具白名单校验 (A1)
    - 参数边界校验 (A2)
    - allow / deny / failed 三条路径
    """

    # 白名单工具
    TOOL_WHITELIST = {"read_file", "http_fetch"}

    # 安全目录（用于路径边界校验）
    SAFE_DIRECTORIES = {"/workspace", "/tmp", "/home"}

    # 私网 IP 前缀
    PRIVATE_NETWORKS = [
        "127.",
        "192.168.",
        "10.",
        "172.16.",
        "172.17.",
        "172.18.",
        "172.19.",
        "172.20.",
        "172.21.",
        "172.22.",
        "172.23.",
        "172.24.",
        "172.25.",
        "172.26.",
        "172.27.",
        "172.28.",
        "172.29.",
        "172.30.",
        "172.31.",
    ]

    def __init__(self, fake_tool_registry):
        """
        Args:
            fake_tool_registry: FakeToolRegistry 实例，用于执行工具
        """
        self.fake_tools = fake_tool_registry
        self.event_log: List[Dict[str, Any]] = []

    def handle_request(self, request: Dict[str, Any]) -> Dict[str, Any]:
        """
        处理工具调用请求

        Args:
            request: {
                "tool_name": str,
                "args": dict,
                "request_id": str (可选)
            }

        Returns:
            完整响应，包含状态流转
        """
        request_id = request.get("request_id", str(uuid.uuid4()))
        tool_name = request.get("tool_name")
        args = request.get("args", {})

        # 初始化状态
        state = GatewayState.RECEIVED
        self._log_event(request_id, state, {"tool_name": tool_name, "args": args})

        # Step 1: Normalization
        state = GatewayState.NORMALIZED
        normalized_args, norm_error = self._normalize_args(args)
        if norm_error:
            return self._build_response(
                request_id=request_id,
                state=GatewayState.FAILED,
                decision=None,
                reason=f"normalization_failed: {norm_error}",
                matched_at="A2",
                executed=False,
                output=None
            )
        self._log_event(request_id, state, {"normalized_args": normalized_args})

        # Step 2: Policy Checking (A1 - 工具白名单)
        state = GatewayState.POLICY_CHECKING
        self._log_event(request_id, state, {})

        if tool_name not in self.TOOL_WHITELIST:
            return self._build_response(
                request_id=request_id,
                state=GatewayState.DENIED,
                decision=Decision.DENY,
                reason="tool_not_in_whitelist",
                matched_at="A1",
                executed=False,
                output=None
            )

        # Step 2: Policy Checking (A2 - 参数边界)
        boundary_check, boundary_reason = self._check_parameter_boundary(tool_name, normalized_args)
        if not boundary_check:
            return self._build_response(
                request_id=request_id,
                state=GatewayState.DENIED,
                decision=Decision.DENY,
                reason=boundary_reason,
                matched_at="A2",
                executed=False,
                output=None
            )

        # Step 3: Allowed -> Executing
        state = GatewayState.ALLOWED
        self._log_event(request_id, state, {"decision": "ALLOW"})

        state = GatewayState.EXECUTING
        self._log_event(request_id, state, {})

        # Step 4: Execute with fake tools
        try:
            output = self._execute_tool(tool_name, normalized_args)
            state = GatewayState.SUCCEEDED
            self._log_event(request_id, state, {"output": str(output)[:100]})

            return self._build_response(
                request_id=request_id,
                state=state,
                decision=Decision.ALLOW,
                reason="execution_succeeded",
                matched_at="A3",
                executed=True,
                output=output
            )

        except Exception as e:
            state = GatewayState.FAILED
            self._log_event(request_id, state, {"error": str(e)})

            return self._build_response(
                request_id=request_id,
                state=state,
                decision=Decision.ALLOW,
                reason=f"execution_failed: {str(e)}",
                matched_at="A3",
                executed=True,
                output=None
            )

    def _normalize_args(self, args: Any) -> tuple:
        """
        参数规范化

        Returns:
            (normalized_args, error_message)
        """
        if args is None:
            return {}, None

        if not isinstance(args, dict):
            return None, "args_must_be_dict"

        # 简单的类型检查
        for key, value in args.items():
            if not isinstance(key, str):
                return None, f"arg_key_must_be_string: {key}"
            if not isinstance(value, (str, int, float, bool, list, dict)):
                return None, f"arg_value_type_not_supported: {key}"

        return args, None

    def _check_parameter_boundary(self, tool_name: str, args: Dict[str, Any]) -> tuple:
        """
        参数边界校验

        Returns:
            (is_valid, reason)
        """
        if tool_name == "read_file":
            path = args.get("path", "")
            if not isinstance(path, str):
                return False, "path_must_be_string"

            # 检查路径是否在安全目录内
            is_safe = any(path.startswith(safe_dir) for safe_dir in self.SAFE_DIRECTORIES)
            if not is_safe:
                return False, "path_outside_safe_dir"

        elif tool_name == "http_fetch":
            url = args.get("url", "")
            if not isinstance(url, str):
                return False, "url_must_be_string"

            # 检查 scheme
            if not (url.startswith("http://") or url.startswith("https://")):
                return False, "invalid_url_scheme"

            # 检查私网目标
            for private_prefix in self.PRIVATE_NETWORKS:
                if url.startswith(f"http://{private_prefix}") or url.startswith(f"https://{private_prefix}"):
                    return False, "private_or_loopback_target"

        return True, None

    def _execute_tool(self, tool_name: str, args: Dict[str, Any]) -> Any:
        """执行工具（调用 fake tools）"""
        if tool_name == "read_file":
            path = args.get("path")
            return self.fake_tools.fake_read_file(path)

        elif tool_name == "http_fetch":
            url = args.get("url")
            return self.fake_tools.fake_http_fetch(url)

        else:
            raise ValueError(f"Unknown tool: {tool_name}")

    def _build_response(
        self,
        request_id: str,
        state: GatewayState,
        decision: Optional[Decision],
        reason: str,
        matched_at: str,
        executed: bool,
        output: Any
    ) -> Dict[str, Any]:
        """构建响应"""
        return {
            "request_id": request_id,
            "state": state.value,
            "decision": decision.value if decision else None,
            "reason": reason,
            "matched_at": matched_at,
            "executed": executed,
            "output": output,
            "timestamp": self._get_timestamp()
        }

    def _log_event(self, request_id: str, state: GatewayState, details: Dict[str, Any]):
        """记录事件"""
        self.event_log.append({
            "request_id": request_id,
            "state": state.value,
            "timestamp": self._get_timestamp(),
            "details": details
        })

    def get_events(self, request_id: Optional[str] = None) -> List[Dict[str, Any]]:
        """
        获取事件日志

        Args:
            request_id: 如果指定，只返回该 request 的事件
        """
        if request_id:
            return [e for e in self.event_log if e["request_id"] == request_id]
        return self.event_log

    def clear_events(self):
        """清空事件日志"""
        self.event_log.clear()

    def _get_timestamp(self) -> str:
        """获取当前时间戳"""
        return datetime.utcnow().isoformat() + "Z"
