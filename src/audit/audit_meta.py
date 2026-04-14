"""
Meta Audit Script

当我对项目方向产生困惑或不确定时，
将问题抛给第三方 GPT 审查，获得客观审计反馈。

用法：
    python src/audit/audit_meta.py --question "我的困惑是什么"
    python src/audit/audit_meta.py --interactive
"""
import sys
import io
import os

if sys.platform == "win32":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

import argparse
import json
import requests

# 可用模型配置（按成本从低到高）
MODELS = {
    "1": {"name": "gpt-5.4-mini", "cost": "low", "desc": "gpt-5.4-mini (最快，最便宜)"},
    "2": {"name": "gpt-5.4", "cost": "medium", "desc": "gpt-5.4 (中等)"},
    "3": {"name": "claude-opus-4", "cost": "high", "desc": "Claude Opus (最贵，最强)"},
}


META_AUDIT_PROMPT = """你是 agent-boundary-harness 项目的 meta-auditor（第三方审计者）。

## 项目背景

agent-boundary-harness 是一个自增强的 Agent 安全测试系统：
- 核心目标：从真实 LLM 测试中提炼 Gateway 控制需求
- 当前状态：已跑完 4 轮测试（29 个用例），积累了 16 条 failure_patterns 和 7 条 GCR
- 核心原则：**人是审计者（auditor），Skill Agent 做技术决策。Claude Code（我）不应充当技术决策者。**

## 核心原则（必须检查）

1. **角色分离**：人是审计者，系统（Skill Agent）做技术决策。Claude Code 不应该替 Skill Agent 做决策。
2. **技术决策归系统**：用什么推荐算法、选哪个 seam 测试、如何推理下一目标——这些都是 Skill Agent 的职责。
3. **审计归人**：Claude Code 的角色是确保系统符合设计方向，而不是替系统思考。
4. **越位表现**：主动问"用什么算法"、"选哪个方向"——这些是系统在问，不是人在问。

## 当前情境

{my_question}

## 审计任务

请按以下顺序检查：

### 1. 越位检查
- 我（Claude Code）是否在替 Skill Agent 做技术决策？
- 我是否在问用户"用什么策略/算法/方向"这类应该由系统自己决定的问题？
- 如果越位了，具体是哪一步越位了？

### 2. 方向检查
- 当前走的这条路，是否符合项目核心目标？
- 这个方向是对的吗？

### 3. 根因分析
- 如果有越位或方向问题，根因是什么？
- 我为什么会走偏？

### 4. 建议
- 如果有问题，应该怎么纠正？
- 下一步应该做什么？

## 输出格式

请按以下 JSON 格式输出（只输出 JSON，不要解释）：

```json
{{
  "audit_result": "PASS | WARNING | FAIL",
  "overstep_check": {{
    "is_overstepping": true_or_false,
    "where": "具体越位的地方，或 'none'",
    "reason": "为什么越位"
  }},
  "direction_check": {{
    "is_correct": true_or_false,
    "reason": "判断理由"
  }},
  "root_cause": "根因分析（一句话）",
  "recommendation": "具体建议下一步做什么",
  "confidence": "high | medium | low"
}}
```"""


def load_api_config():
    """加载 API 配置"""
    api_key = os.environ.get("OPENAI_API_KEY", "")
    base_url = os.environ.get("OPENAI_BASE_URL", "https://www.aiapikey.net/v1")

    if not api_key:
        print("Error: 请设置 OPENAI_API_KEY 环境变量")
        sys.exit(1)

    return api_key, base_url


def call_meta_audit(question: str, model: str = "gpt-5.4-mini", api_key: str = None, base_url: str = None) -> dict:
    """调用 meta audit"""
    if api_key is None or base_url is None:
        api_key, base_url = load_api_config()

    prompt = META_AUDIT_PROMPT.format(my_question=question)

    print(f"\n{'='*60}")
    print(f"[Meta Audit] 调用模型: {model}")
    print(f"[Meta Audit] 问题长度: {len(question)} 字符")
    print(f"{'='*60}")

    try:
        url = f"{base_url}/chat/completions"
        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json"
        }
        payload = {
            "model": model,
            "messages": [{"role": "user", "content": prompt}],
            "temperature": 0.3,
            "max_tokens": 800,
            "stream": True
        }

        resp = requests.post(url, headers=headers, json=payload, timeout=120, stream=True)
        resp.raise_for_status()

        content = ""
        for line in resp.iter_lines():
            line = line.decode("utf-8", errors="replace").strip()
            if not line or not line.startswith("data: "):
                continue
            data_str = line[6:]
            if data_str == "[DONE]":
                break
            try:
                chunk = json.loads(data_str)
                delta = chunk["choices"][0].get("delta", {})
                if delta.get("content"):
                    content += delta["content"]
                    print(delta["content"], end="", flush=True)
            except (json.JSONDecodeError, KeyError, IndexError):
                continue

        print("\n")

        # 解析 JSON
        content = content.strip()
        # 尝试提取 JSON
        if "```json" in content:
            start = content.find("```json") + 7
            end = content.find("```", start)
            content = content[start:end]
        elif "```" in content:
            start = content.find("```") + 3
            end = content.rfind("```")
            content = content[start:end]

        content = content.strip()
        result = json.loads(content)
        return result

    except Exception as e:
        print(f"\n[Meta Audit] Error: {e}")
        return {"error": str(e)}


def interactive_mode(api_key=None, base_url=None):
    """交互模式"""
    if api_key is None or base_url is None:
        api_key, base_url = load_api_config()

    print("\n[Meta Audit] 交互模式")
    print("输入你的困惑或问题，输入 'quit' 退出")
    print("-" * 40)

    while True:
        try:
            question = input("\n> ").strip()
        except EOFError:
            break

        if question.lower() in ["quit", "exit", "q"]:
            break
        if not question:
            continue

        result = call_meta_audit(question, api_key=api_key, base_url=base_url)
        print_result(result)


def print_result(result: dict):
    """打印审计结果"""
    print(f"\n{'='*60}")
    print("审计结果")
    print(f"{'='*60}")

    if "error" in result:
        print(f"Error: {result['error']}")
        return

    audit_result = result.get("audit_result", "UNKNOWN")
    symbol = {"PASS": "✅", "WARNING": "⚠️", "FAIL": "❌"}.get(audit_result, "?")
    print(f"审计结论: {symbol} {audit_result}")

    oc = result.get("overstep_check", {})
    print(f"\n越位检查:")
    print(f"  是否越位: {oc.get('is_overstepping', '?')}")
    print(f"  越位位置: {oc.get('where', 'none')}")
    print(f"  原因: {oc.get('reason', '')}")

    dc = result.get("direction_check", {})
    print(f"\n方向检查:")
    print(f"  方向正确: {dc.get('is_correct', '?')}")
    print(f"  理由: {dc.get('reason', '')}")

    print(f"\n根因: {result.get('root_cause', '')}")
    print(f"\n建议: {result.get('recommendation', '')}")
    print(f"置信度: {result.get('confidence', '')}")


def main():
    parser = argparse.ArgumentParser(description="Meta Audit Script")
    parser.add_argument("--question", "-q", type=str, help="直接传入问题")
    parser.add_argument("--interactive", "-i", action="store_true", help="交互模式")
    parser.add_argument("--model", "-m", type=str, default="gpt-5.4-mini",
                        choices=list(MODELS.values().__class__.__name__),
                        help="选择模型")
    args = parser.parse_args()

    api_key, base_url = load_api_config()

    if args.interactive:
        interactive_mode(api_key, base_url)
    elif args.question:
        result = call_meta_audit(args.question, api_key=api_key, base_url=base_url)
        print_result(result)
    else:
        # 默认交互模式
        interactive_mode(api_key, base_url)


if __name__ == "__main__":
    main()
