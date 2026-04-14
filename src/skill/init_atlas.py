"""
ATLAS → AttackPatternStore 初始化脚本

用法：
    1. 设置环境变量：export OPENAI_API_KEY="sk-..."
    2. 运行：python src/skill/init_attack_patterns.py [数量]
    3. 输出：data/attack_patterns.json

    如果 data/atlas_stix.json 不存在，会自动从 GitHub 下载。
"""

import json
import os
import sys
import time
import io
from pathlib import Path

# Windows 编码修复
if sys.platform == "win32":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

ATLAS_STIX_PATH = PROJECT_ROOT / "data" / "atlas_stix.json"
ATLAS_STIX_URL = "https://raw.githubusercontent.com/mitre-atlas/atlas-navigator-data/master/dist/stix-atlas.json"

# ---------------------------------------------------------------------------
# 第一阶段：加载 ATLAS STIX 数据
# ---------------------------------------------------------------------------

def ensure_atlas_data():
    """确保 ATLAS STIX 数据存在"""
    if ATLAS_STIX_PATH.exists():
        print(f"[1/3] 使用本地数据：{ATLAS_STIX_PATH}")
        return

    print(f"[1/3] 下载 ATLAS STIX 数据...")
    import requests
    resp = requests.get(ATLAS_STIX_URL, timeout=60)
    resp.raise_for_status()
    ATLAS_STIX_PATH.parent.mkdir(exist_ok=True)
    with open(ATLAS_STIX_PATH, "w", encoding="utf-8") as f:
        f.write(resp.text)
    print(f"  已下载到 {ATLAS_STIX_PATH}")


def parse_stix_techniques() -> list[dict]:
    """从 STIX 数据中提取攻击技术"""
    with open(ATLAS_STIX_PATH, "r", encoding="utf-8") as f:
        stix = json.load(f)

    objects = stix.get("objects", [])

    # 提取 attack-pattern 类型的对象
    techniques = []
    for obj in objects:
        if obj.get("type") != "attack-pattern":
            continue

        ext_id = ""
        for ref in obj.get("external_references", []):
            if ref.get("source_name") == "mitre-atlas":
                ext_id = ref.get("external_id", "")
                break

        if not ext_id:
            continue

        # ATLAS ID 格式：AML.Txxxx 为顶层，AML.Txxxx.xxx 为子技术
        is_sub = ext_id.count(".") > 1  # AML.T0000 有1个点，AML.T0000.000 有2个点

        # 提取 tactics
        tactics = []
        for phase in obj.get("kill_chain_phases", []):
            if phase.get("kill_chain_name") == "mitre-atlas":
                tactics.append(phase.get("phase_name", ""))

        # 提取描述
        description = obj.get("description", "")
        if not description:
            # 尝试从 source 拼接
            for ref in obj.get("external_references", []):
                if ref.get("description"):
                    description = ref["description"]
                    break

        techniques.append({
            "id": ext_id,
            "name": obj.get("name", ""),
            "description": description,
            "tactics": tactics,
            "url": f"https://atlas.mitre.org/techniques/{ext_id}",
            "is_subtechnique": is_sub
        })

    # 按ID排序
    techniques.sort(key=lambda t: t["id"])

    # 只保留顶层技术（非子技术），子技术信息会在 LLM 分析时参考
    top_level = [t for t in techniques if not t["is_subtechnique"]]
    sub_level = [t for t in techniques if t["is_subtechnique"]]

    # 将子技术信息附加到父技术
    sub_map = {}
    for s in sub_level:
        parent_id = s["id"].split(".")[0]
        sub_map.setdefault(parent_id, []).append(s)

    for t in top_level:
        t["sub_techniques"] = sub_map.get(t["id"], [])

    print(f"  发现 {len(top_level)} 个顶层技术，{len(sub_level)} 个子技术")
    return top_level


# ---------------------------------------------------------------------------
# 第二阶段：调用 OpenAI 分析 → 映射为 AttackPattern
# ---------------------------------------------------------------------------

SYSTEM_PROMPT = """你是一个 AI 系统安全研究员。你的任务是将 MITRE ATLAS 的技术条目映射为结构化的风险模式。

## 输入输出分类（Seam）

| 编号 | 名称 | 含义 |
|---|---|---|
| I1 | user_input | 用户直接提供的指令 |
| I2 | web_content | Agent 访问的网页内容 |
| I3 | document_content | Agent 读取的文件内容 |
| I4 | retrieval_result | RAG 或搜索返回的内容 |
| I5 | tool_output | 外部工具返回的结果 |

## 控制边界（Boundary）

| 编号 | 名称 | 含义 |
|---|---|---|
| A1 | tool_selection | 工具选择控制 |
| A2 | param_construction | 参数构造控制 |
| A3 | side_effect | 副作用执行控制 |
| M1 | temp_state | 临时状态管理 |
| M2 | cross_session | 跨会话状态管理 |

## 规则

1. 一条 ATLAS 可拆为多个 pattern
2. 信息不足时 confidence = "low"
3. 不适用时输出 {"skip": true, "reason": "..."}

## 输出 JSON 数组格式

[{"pattern_id":"ap-{seam}-{slug}-v1","seam":"I1","boundary":"A1","seam_boundary_pair":["I1-A1"],"pattern_description":"中文描述50-150字","atlas_mapping":{"technique_id":"原ID","technique_name":"原名称","tactics":["战术"],"mapped_confidence":"high"},"attack_flow":["步骤"],"detection_hints":["信号"],"effectiveness_score":0.0,"sample_size":0,"embedding_hint":"english keywords","source":"atlas_analysis"}]

约束：只输出JSON数组，中文描述，不瞎编。"""


def analyze_technique(technique: dict, client_config: dict) -> list[dict]:
    """调用 LLM 分析单个技术条目"""
    sub_info = ""
    if technique.get("sub_techniques"):
        sub_names = [f"{s['id']}: {s['name']} - {s['description'][:100]}" for s in technique["sub_techniques"]]
        sub_info = f"\n\n子技术：\n" + "\n".join(sub_names)

    user_content = f"""=== ATLAS ENTRY ===
ID: {technique['id']}
名称: {technique['name']}
战术: {', '.join(technique['tactics']) or '无'}

{technique['description']}{sub_info}
=== END ===

请将上述 ATLAS 条目映射为 AttackPattern JSON 数组。"""

    try:
        import requests
        url = f"{client_config['base_url']}/chat/completions"
        headers = {
            "Authorization": f"Bearer {client_config['api_key']}",
            "Content-Type": "application/json"
        }
        payload = {
            "model": "gpt-5.4-mini",
            "messages": [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": user_content}
            ],
            "temperature": 0.3,
            "max_tokens": 2000
        }

        payload["stream"] = True  # 此代理��台非 stream 模式 content 返回 null

        resp = requests.post(url, headers=headers, json=payload, timeout=120, stream=True)
        resp.raise_for_status()

        # 收集 stream chunks
        raw = ""
        for line in resp.iter_lines():
            line = line.decode("utf-8").strip()
            if not line or not line.startswith("data: "):
                continue
            data_str = line[6:]
            if data_str == "[DONE]":
                break
            try:
                chunk = json.loads(data_str)
                delta = chunk["choices"][0].get("delta", {})
                content = delta.get("content")
                if content:
                    raw += content
            except (json.JSONDecodeError, KeyError, IndexError):
                continue

        raw = raw.strip()

        # 清理可能的 markdown 包裹
        if raw.startswith("```"):
            lines = raw.split("\n")
            raw = "\n".join(lines[1:])
        if raw.endswith("```"):
            raw = raw[:-3]
        if raw.startswith("json"):
            raw = raw[4:]
        raw = raw.strip()

        result = json.loads(raw)

        # 统一为数组
        if isinstance(result, dict):
            if result.get("skip"):
                return []
            result = [result]

        return [r for r in result if not r.get("skip")]

    except json.JSONDecodeError as e:
        print(f"  Warning: JSON parse failed ({technique['id']}): {e}")
        return []
    except Exception as e:
        print(f"  Warning: API call failed ({technique['id']}): {e}")
        return []


# ---------------------------------------------------------------------------
# 第三阶段：汇总输出
# ---------------------------------------------------------------------------

def run_initialization(max_techniques: int = 5):
    """运行完整初始化流程"""
    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key:
        print("错误：请设置环境变量 OPENAI_API_KEY")
        print("  export OPENAI_API_KEY='sk-your-key-here'")
        sys.exit(1)

    try:
        from openai import OpenAI
    except ImportError:
        print("错误：需要安装 openai 库")
        print("  pip install openai")
        sys.exit(1)

    # 第三方代理，直接用 requests 调用（避免 openai 库代理问题）
    base_url = os.environ.get("OPENAI_BASE_URL", "https://www.aiapikey.net/v1")
    client = {"api_key": api_key, "base_url": base_url}

    # 加载 ATLAS 数据
    ensure_atlas_data()
    all_techniques = parse_stix_techniques()
    techniques = all_techniques[:max_techniques]

    print(f"\n将分析前 {len(techniques)} 个技术（共 {len(all_techniques)} 个可用）\n")

    # LLM 分析
    all_patterns = []
    for i, technique in enumerate(techniques):
        print(f"[2/3] LLM 分析 ({i+1}/{len(techniques)}): {technique['id']} {technique['name']}")
        patterns = analyze_technique(technique, client)
        all_patterns.extend(patterns)
        print(f"  → 产出 {len(patterns)} 个 AttackPattern")
        time.sleep(1)

    # 保存结果
    output_dir = PROJECT_ROOT / "data"
    output_dir.mkdir(exist_ok=True)
    output_path = output_dir / "attack_patterns.json"

    output = {
        "metadata": {
            "source": "MITRE ATLAS",
            "total_patterns": len(all_patterns),
            "atlas_techniques_analyzed": len(techniques),
            "atlas_techniques_total": len(all_techniques),
            "model": "gpt-5.4-mini",
            "created_at": time.strftime("%Y-%m-%dT%H:%M:%S")
        },
        "patterns": all_patterns
    }

    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)

    print(f"\n[3/3] 完成！共 {len(all_patterns)} 个 AttackPattern")
    print(f"输出文件：{output_path}")

    # 统计
    seam_counts = {}
    boundary_counts = {}
    confidence_counts = {}
    for p in all_patterns:
        s = p.get("seam", "?")
        b = p.get("boundary", "?")
        c = p.get("atlas_mapping", {}).get("mapped_confidence", "?")
        seam_counts[s] = seam_counts.get(s, 0) + 1
        boundary_counts[b] = boundary_counts.get(b, 0) + 1
        confidence_counts[c] = confidence_counts.get(c, 0) + 1

    print(f"\nSeam 分布：{json.dumps(seam_counts, ensure_ascii=False)}")
    print(f"Boundary 分布：{json.dumps(boundary_counts, ensure_ascii=False)}")
    print(f"置信度分布：{json.dumps(confidence_counts, ensure_ascii=False)}")


if __name__ == "__main__":
    max_t = int(sys.argv[1]) if len(sys.argv) > 1 else 5
    run_initialization(max_techniques=max_t)
