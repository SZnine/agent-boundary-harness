"""
Run L1 defense pattern analysis on Round 1 results.

Analyzes the 5 L1 results to understand WHY the Agent resisted,
then produces defense patterns and counter-attack hints.

Run: OPENAI_API_KEY=sk-xxx python src/snapshots/run_l1_analysis.py
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
        print("Error: No API key found")
        sys.exit(1)

    # Load rich Round 1 results
    with open("traces/indirect-injection-report.json", "r", encoding="utf-8") as f:
        results = json.load(f)

    l1_count = sum(1 for r in results if r["classification"] == "L1")
    print(f"Round 1 results: {len(results)} total, {l1_count} L1")

    # Show L1 items
    for r in results:
        if r["classification"] == "L1":
            resp = r.get("agent_response", "")[:80]
            print(f"  {r['name']}: {resp}...")

    print()

    # Run L1-only analysis (skip L2 this time)
    skill = SkillAPI()

    # Only pass L1 results to analyze_failures with analyze_l1=True
    l1_results = [r for r in results if r["classification"] == "L1"]
    patterns = skill.analyze_failures(
        l1_results,
        api_key=api_key,
        base_url="https://www.aiapikey.net/v1",
        model="gpt-5.4-mini",
        analyze_l1=True
    )

    if patterns:
        print(f"\nExtracted {len(patterns)} defense patterns")
        for p in patterns:
            pid = p.get("pattern_id", "?")
            defense = p.get("defense_pattern", "?")[:60]
            counter = p.get("counter_attack_hint", "?")[:60]
            print(f"  {pid}:")
            print(f"    defense: {defense}...")
            print(f"    counter: {counter}...")
    else:
        print("\nNo patterns extracted")


if __name__ == "__main__":
    main()
