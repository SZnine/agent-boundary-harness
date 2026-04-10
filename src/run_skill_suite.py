import sys
import io
import os

if sys.platform == "win32":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')

# Add project root to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

import json

from src.sandbox.fake_tools import get_fake_tool_registry
from src.gateway.mock_gateway import MockGateway
from src.harness.harness import Harness
from src.skill.skill_api import SkillAPI


def main():
    # 初始化组件
    fake_tools = get_fake_tool_registry()
    gateway = MockGateway(fake_tools)
    skill = SkillAPI(data_path="data/attack_patterns.json")
    harness = Harness(gateway, fake_tools, skill_api=skill)

    print(f"AttackPatternStore loaded: {skill._store.total_count} patterns")
    print()

    # 运行 Skill 驱动的测试
    sessions = harness.run_skill_driven_suite()
    report = harness.generate_summary_report()

    # 输出结果
    print("=" * 60)
    print("Skill-driven Attack Test Report")
    print("=" * 60)

    summary = report["summary"]
    print(f"Total sessions: {summary['total_sessions']}")
    print(f"L1 (capability miss): {summary['l1_count']}")
    print(f"L2 (control weakness): {summary['l2_count']}")
    print(f"L3 (exploitable): {summary['l3_count']}")
    print()

    for session_data in report["sessions"]:
        task = session_data["initial_task"]
        boundary = session_data["target_boundary"]
        classification = session_data["final_classification"]
        print(f"  {task} | boundary: {boundary} | class: {classification}")

    # 保存报告
    os.makedirs("traces", exist_ok=True)
    with open("traces/skill-suite-report.json", "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)
    print()
    print("Report saved to traces/skill-suite-report.json")


if __name__ == "__main__":
    main()
