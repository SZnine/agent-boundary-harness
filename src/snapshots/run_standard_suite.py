"""
运行标准测试集并产出攻击测评报告
"""

import sys
import os

# Fix Windows console encoding
if sys.platform == 'win32':
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8')

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from src.sandbox.fake_tools import FakeToolRegistry
from src.gateway.mock_gateway import MockGateway
from src.harness.harness import Harness, FailureClassification


def print_separator(char="=", length=60):
    print(char * length)


def print_report_summary(report):
    """打印可读的报告摘要"""
    summary = report["summary"]

    print_separator()
    print("  攻击测评报告（v0.1 标准测试集）")
    print_separator()

    print(f"\n  总会话数: {summary['total_sessions']}")
    print(f"  L1 (能力缺失):     {summary['l1_count']}")
    print(f"  L2 (控制弱点):     {summary['l2_count']}")
    print(f"  L3 (可利用漏洞):   {summary['l3_count']}")

    print(f"\n  高价值探测点: {len(report['high_value_probes'])}")
    print_separator("-")

    # 每个会话详情
    for i, session in enumerate(report["sessions"], 1):
        result = session["iteration_chain"][0]
        attack = result["attack_context"]
        gw = result["gateway_response"]
        cont = result["continuation_decision"]

        print(f"\n  [{i}] {session['initial_task']}")
        print(f"      Seam: {attack['seam']}  |  边界: {session['target_boundary']}")
        print(f"      载荷: {attack['payload'][:50]}...")
        print(f"      Gateway: {gw['decision']} ({gw['reason']}) @ {gw['matched_at']}")
        print(f"      分类: {result['failure_classification']}")

        if cont["requires_deeper_probe"]:
            print(f"      >> 建议继续: {cont['probe_direction']}")
            print(f"         预估成本: {cont['estimated_cost']}")
        else:
            print(f"      >> 停止: {cont['stop_reason']}")

    # 高价值探测点汇总
    if report["high_value_probes"]:
        print()
        print_separator("-")
        print("  建议深入测试的方向（需用户授权）:")
        print_separator("-")
        for i, item in enumerate(report["high_value_probes"], 1):
            print(f"\n  {i}. {item['task']}")
            print(f"     方向: {item['probe_direction']}")
            print(f"     成本: {item['estimated_cost']}")

    print()
    print_separator()
    print("  报告已保存到 traces/standard-suite-report.json")
    print_separator()


def main():
    print("\n运行标准测试集...\n")

    # 创建组件
    fake_tools = FakeToolRegistry()
    gateway = MockGateway(fake_tools)
    harness = Harness(gateway, fake_tools)

    # 运行标准测试集
    sessions = harness.run_standard_suite()

    # 生成报告
    report = harness.generate_summary_report()

    # 打印可读摘要
    print_report_summary(report)

    # 保存 JSON 报告
    os.makedirs("traces", exist_ok=True)
    harness.save_report("traces/standard-suite-report.json")

    return report


if __name__ == "__main__":
    main()
