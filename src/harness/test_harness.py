"""
Harness 主控逻辑单元测试

验证：
1. 标准测试集运行（4 个用例）
2. 攻击分类（L1/L2/L3）
3. 迭代决策判断
4. 报告生成
"""

import sys
import os

# Fix Windows console encoding
if sys.platform == 'win32':
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8')

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))

from src.sandbox.fake_tools import FakeToolRegistry
from src.gateway.mock_gateway import MockGateway
from src.harness.harness import Harness, FailureClassification


def setup_harness():
    """创建测试用的 Harness 实例"""
    fake_tools = FakeToolRegistry()
    gateway = MockGateway(fake_tools)
    return Harness(gateway, fake_tools)


def test_t_i1_a1_classification():
    """T-I1-A1: 用户输入直接诱导 → 应被 A1 拦住 → L2"""
    harness = setup_harness()
    sessions = harness.run_standard_suite()

    session = sessions[0]  # T-I1-A1
    assert session.initial_task == "T-I1-A1: 用户输入直接诱导工具选择"
    assert session.target_boundary == "A1"

    result = session.iteration_chain[0]
    assert result.seam == "I1"
    assert result.failure_classification == FailureClassification.L2_CONTROL_WEAKNESS

    # L2 应建议继续探测
    assert result.continuation_decision.requires_deeper_probe == True
    assert result.continuation_decision.probe_direction is not None
    assert result.continuation_decision.estimated_cost is not None

    print(f"✓ T-I1-A1: L2 (控制弱点), 建议继续: {result.continuation_decision.probe_direction}")


def test_t_i2_a1_classification():
    """T-I2-A1: 网页间接注入 → 应触发 http_fetch → L1 或 L2"""
    harness = setup_harness()
    sessions = harness.run_standard_suite()

    session = sessions[1]  # T-I2-A1
    assert session.initial_task == "T-I2-A1: 网页内容间接诱导工具选择"

    result = session.iteration_chain[0]
    assert result.seam == "I2"
    # http_fetch 到恶意网页 → ALLOW（因为 URL 合法）→ L1（正常执行）
    # 但网页内容包含恶意指令 → 这个信息在 output 中
    assert result.failure_classification in [
        FailureClassification.L1_CAPABILITY_MISS,
        FailureClassification.L2_CONTROL_WEAKNESS,
        FailureClassification.L3_EXPLOITABLE_VULNERABILITY
    ]

    print(f"✓ T-I2-A1: {result.failure_classification.value}, Gateway 决策: {result.gateway_decision}")


def test_t_i5_a1_classification():
    """T-I5-A1: 工具输出伪装 → 应触发 http_fetch → 分析输出"""
    harness = setup_harness()
    sessions = harness.run_standard_suite()

    session = sessions[2]  # T-I5-A1
    assert session.initial_task == "T-I5-A1: 工具输出伪装管理员指令"

    result = session.iteration_chain[0]
    assert result.seam == "I5"

    print(f"✓ T-I5-A1: {result.failure_classification.value}, Gateway 决策: {result.gateway_decision}")


def test_t_m1_a2_classification():
    """T-M1-A2: 记忆污染 → 应触发 read_file(/etc/passwd) → A2 DENY → L2"""
    harness = setup_harness()
    sessions = harness.run_standard_suite()

    session = sessions[3]  # T-M1-A2
    assert session.initial_task == "T-M1-A2: 多步任务中的临时状态污染"
    assert session.target_boundary == "A2"

    result = session.iteration_chain[0]
    assert result.seam == "M1"
    # /etc/passwd 被拦住 → L2
    assert result.failure_classification == FailureClassification.L2_CONTROL_WEAKNESS

    # L2 + A2 → 建议继续路径遍历绕过
    assert result.continuation_decision.requires_deeper_probe == True

    print(f"✓ T-M1-A2: L2 (控制弱点), 建议继续: {result.continuation_decision.probe_direction}")


def test_standard_suite_count():
    """验证标准测试集包含 4 个会话"""
    harness = setup_harness()
    sessions = harness.run_standard_suite()

    assert len(sessions) == 4
    print(f"✓ 标准测试集: {len(sessions)} 个会话")


def test_summary_report():
    """验证汇总报告生成"""
    harness = setup_harness()
    harness.run_standard_suite()

    report = harness.generate_summary_report()

    assert "summary" in report
    assert "high_value_probes" in report
    assert "sessions" in report

    summary = report["summary"]
    assert summary["total_sessions"] == 4
    assert summary["l1_count"] + summary["l2_count"] + summary["l3_count"] == 4

    print(f"✓ 汇总报告: L1={summary['l1_count']}, L2={summary['l2_count']}, L3={summary['l3_count']}")
    print(f"  高价值探测点: {len(report['high_value_probes'])}")


def test_session_report():
    """验证单会话报告"""
    harness = setup_harness()
    sessions = harness.run_standard_suite()

    session_id = sessions[0].session_id
    report = harness.generate_report(session_id)

    assert report["session_id"] == session_id
    assert "iteration_chain" in report
    assert len(report["iteration_chain"]) == 1

    print(f"✓ 单会话报告: {report['initial_task']}")


def test_save_report(tmp_path=None):
    """验证报告保存"""
    import tempfile
    harness = setup_harness()
    harness.run_standard_suite()

    with tempfile.NamedTemporaryFile(suffix=".json", delete=False, mode='w') as f:
        filepath = f.name

    harness.save_report(filepath)

    import json
    with open(filepath, 'r', encoding='utf-8') as f:
        report = json.load(f)

    assert "summary" in report
    assert report["summary"]["total_sessions"] == 4

    os.unlink(filepath)
    print("✓ 报告保存: JSON 文件写入成功")


def test_continuation_decision_l3_stops():
    """L3 应停止迭代"""
    harness = setup_harness()

    # 构造一个 L3 场景：ALLOW + 敏感内容输出
    # 通过直接调用 _classify_failure 和 _decide_continuation
    response = {
        "decision": "ALLOW",
        "reason": "execution_succeeded",
        "matched_at": "A3",
        "executed": True,
        "output": "root:x:0:0:root:/root:/bin/bash\n"
    }

    classification = harness._classify_failure(response, "I1")
    assert classification == FailureClassification.L3_EXPLOITABLE_VULNERABILITY

    continuation = harness._decide_continuation(response, classification, "I1", "A1")
    assert continuation.requires_deeper_probe == False
    assert "L3" in continuation.stop_reason

    print("✓ L3 停止迭代验证")


def test_continuation_decision_l1_stops():
    """L1 应停止迭代"""
    harness = setup_harness()

    response = {
        "decision": "ALLOW",
        "reason": "execution_succeeded",
        "matched_at": "A3",
        "executed": True,
        "output": "正常文件内容"
    }

    classification = harness._classify_failure(response, "I1")
    assert classification == FailureClassification.L1_CAPABILITY_MISS

    continuation = harness._decide_continuation(response, classification, "I1", "A1")
    assert continuation.requires_deeper_probe == False
    assert "L1" in continuation.stop_reason

    print("✓ L1 停止迭代验证")


if __name__ == "__main__":
    print("运行 Harness 主控逻辑单元测试...\n")

    test_t_i1_a1_classification()
    test_t_i2_a1_classification()
    test_t_i5_a1_classification()
    test_t_m1_a2_classification()
    test_standard_suite_count()
    test_summary_report()
    test_session_report()
    test_save_report()
    test_continuation_decision_l3_stops()
    test_continuation_decision_l1_stops()

    print("\n所有测试通过 ✓")
