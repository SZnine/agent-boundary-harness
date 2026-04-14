"""
Run failure analysis on Round 2 results.

Uses SkillAPI.analyze_failures() to extract failure patterns from L2 results.

Run: OPENAI_API_KEY=sk-xxx python src/snapshots/run_round2_analysis.py
"""
import sys
import io
import os

if sys.platform == "win32":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

import json

from src.skill.skill_service import SkillAPI


def main():
    try:
        api_key = open("key.md").read().strip()
    except FileNotFoundError:
        api_key = os.environ.get("OPENAI_API_KEY", "")

    if not api_key:
        print("Error: No API key found in key.md or OPENAI_API_KEY env")
        sys.exit(1)

    # Load Round 2 results
    with open("traces/round2-report.json", "r", encoding="utf-8") as f:
        report = json.load(f)

    results = report["results"]
    print(f"Round 2 results: {len(results)} total")
    print(f"  L2: {sum(1 for r in results if r['classification'] == 'L2')}")
    print()

    # Run failure analysis
    skill = SkillAPI()
    patterns = skill.analyze_failures(
        results,
        api_key=api_key,
        base_url="https://www.aiapikey.net/v1",
        model="gpt-5.4-mini"
    )

    if patterns:
        print(f"\nExtracted {len(patterns)} failure patterns")
        for p in patterns:
            print(f"  {p.get('pattern_id', '?')}: {p.get('induction_method', '?')[:60]}...")
    else:
        print("\nNo patterns extracted")


if __name__ == "__main__":
    main()
