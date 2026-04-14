"""
Multi-Round Experiment Runner - Offline + Incremental Save

特性：
- 边测试边保存，每条结果实时写入 JSONL
- 中文 UTF-8 编码保证
- 流式中断恢复（支持断点续跑）
- 离线运行，不依赖 Agent 实时读取
- 每轮实验独立配置

用法：
    python src/experiment_runner.py --round 5 --config config/r5_config.json

恢复中断的实验：
    python src/experiment_runner.py --round 5 --resume
"""
import sys
import io
import os
import json
import time
import uuid
import argparse
import signal
from datetime import datetime
from pathlib import Path
from typing import Optional
from dataclasses import dataclass, asdict

# Windows 编码修复
if sys.platform == "win32":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from src.sandbox.fake_tools import reset_fake_tool_registry
from src.gateway.mock_gateway import MockGateway
from src.harness.harness import Harness
from src.agent.target_agent import TargetAgent
from src.agent.llm_config import LLMConfig


# === 实验配置 ===
@dataclass
class ExperimentConfig:
    """每轮实验的配置"""
    round_id: int
    round_name: str  # 如 "R5-校准轮"
    description: str

    # 测试用例
    test_cases: list  # 用例列表
    paired_design: bool = True  # 是否 paired design

    # baseline vs experience
    baseline_type: str = "heuristic"  # heuristic / template / random
    experience_source: str = "failure_patterns"  # 经验来源

    # 执行参数
    max_turns: int = 5
    iteration_depth: int = 3

    # 保存参数
    output_dir: str = "traces/experiments"
    auto_save_interval: int = 1  # 每 N 条结果保存一次

    # token 预算控制
    token_budget: int = 80000  # 本轮 token 预算
    token_warning_threshold: float = 0.8  # 80% 时警告


# === 结果记录 ===
@dataclass
class ExperimentResult:
    """单条实验结果"""
    # 标识
    result_id: str
    round_id: int
    case_name: str
    test_type: str  # "baseline" or "experience"

    # 测试内容
    seam: str
    boundary: str
    payload: str

    # 结果
    classification: str  # L1 / L2 / L3
    gateway_decision: str
    agent_response: str
    tool_calls_detail: list

    # 元数据
    timestamp: str
    tokens_consumed: int
    duration_ms: int

    # 错误记录
    error: Optional[str] = None


class ExperimentRunner:
    """实验运行器 - 支持增量保存和断点续跑"""

    def __init__(self, config: ExperimentConfig, resume: bool = False):
        self.config = config
        self.resume = resume

        # 初始化 LLM
        try:
            self.llm_config = LLMConfig.from_env()
        except ValueError as e:
            print(f"[错误] 环境变量未设置: {e}")
            sys.exit(1)

        # 创建输出目录
        self.output_dir = Path(config.output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)

        # 定义文件路径
        self.results_file = self.output_dir / f"r{config.round_id}-results.jsonl"
        self.state_file = self.output_dir / f"r{config.round_id}-state.json"
        self.log_file = self.output_dir / f"r{config.round_id}-log.txt"

        # 加载状态（断点续跑）
        self.completed_cases = self._load_completed_cases()
        self.total_tokens = self._load_token_count()

        # 信号处理（优雅退出）
        self.interrupted = False
        signal.signal(signal.SIGINT, self._signal_handler)
        signal.signal(signal.SIGTERM, self._signal_handler)

        print(f"[实验 R{config.round_id}] 初始化完成")
        print(f"  输出目录: {self.output_dir}")
        print(f"  结果文件: {self.results_file}")
        print(f"  已完成的用例: {len(self.completed_cases)}")
        print(f"  累计 token 消耗: {self.total_tokens}")

    def _signal_handler(self, signum, frame):
        """处理中断信号"""
        print(f"\n[收到信号 {signum}] 正在保存状态并退出...")
        self.interrupted = True
        self._save_state()
        sys.exit(0)

    def _load_completed_cases(self) -> set:
        """加载已完成的用例 ID"""
        completed = set()
        if self.results_file.exists():
            try:
                with open(self.results_file, 'r', encoding='utf-8') as f:
                    for line in f:
                        if line.strip():
                            data = json.loads(line)
                            case_key = f"{data['case_name']}_{data['test_type']}"
                            completed.add(case_key)
                print(f"[恢复] 找到 {len(completed)} 条已完成记录")
            except Exception as e:
                print(f"[警告] 读取历史结果失败: {e}")
        return completed

    def _load_token_count(self) -> int:
        """加载累计 token 数"""
        if self.state_file.exists():
            try:
                with open(self.state_file, 'r', encoding='utf-8') as f:
                    state = json.load(f)
                    return state.get('total_tokens', 0)
            except:
                pass
        return 0

    def _save_state(self):
        """保存当前状态"""
        state = {
            'round_id': self.config.round_id,
            'round_name': self.config.round_name,
            'completed_cases': list(self.completed_cases),
            'total_tokens': self.total_tokens,
            'last_save': datetime.now().isoformat(),
            'interrupted': self.interrupted
        }
        with open(self.state_file, 'w', encoding='utf-8') as f:
            json.dump(state, f, ensure_ascii=False, indent=2)
        print(f"[状态保存] {self.state_file}")

    def _append_result(self, result: ExperimentResult):
        """追加单条结果到 JSONL（实时保存）"""
        # 确保目录存在
        self.output_dir.mkdir(parents=True, exist_ok=True)

        # 追加写入（追加模式 + UTF-8）
        with open(self.results_file, 'a', encoding='utf-8') as f:
            json.dump(asdict(result), f, ensure_ascii=False)
            f.write('\n')
            f.flush()  # 强制刷新到磁盘

        # 更新状态
        case_key = f"{result.case_name}_{result.test_type}"
        self.completed_cases.add(case_key)
        self.total_tokens += result.tokens_consumed

        # 定期保存状态
        if len(self.completed_cases) % self.config.auto_save_interval == 0:
            self._save_state()

    def _log(self, message: str):
        """写入日志"""
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        log_line = f"[{timestamp}] {message}\n"

        # 控制台输出
        print(log_line.rstrip())

        # 文件记录
        with open(self.log_file, 'a', encoding='utf-8') as f:
            f.write(log_line)
            f.flush()

    def _check_token_budget(self) -> bool:
        """检查 token 预算"""
        ratio = self.total_tokens / self.config.token_budget
        if ratio >= 1.0:
            self._log(f"[预算超限] 已使用 {self.total_tokens}/{self.config.token_budget} tokens")
            return False
        elif ratio >= self.config.token_warning_threshold:
            self._log(f"[预算警告] 已使用 {ratio*100:.1f}% tokens ({self.total_tokens}/{self.config.token_budget})")
        return True

    def run_single_test(self, case: dict, test_type: str) -> ExperimentResult:
        """运行单个测试"""
        start_time = time.time()
        result_id = str(uuid.uuid4())[:8]

        self._log(f"[{result_id}] 开始测试: {case['name']} [{test_type}]")

        try:
            # 准备环境
            fake_tools = reset_fake_tool_registry()

            # 设置测试数据
            if case.get('setup'):
                setup_fn = globals().get(case['setup'])
                if setup_fn:
                    setup_fn(fake_tools)

            # 创建组件
            gateway = MockGateway(fake_tools)
            target_agent = TargetAgent(gateway, fake_tools, self.llm_config, max_turns=self.config.max_turns)
            harness = Harness(gateway, fake_tools, target_agent=target_agent)

            # 构造 payload（根据 test_type 调整）
            payload = case['payload']
            if test_type == "baseline":
                # baseline 版本：简化 payload，不使用经验
                payload = self._apply_baseline_transform(payload, case)
            else:
                # experience 版本：使用 defense_weakness
                payload = self._apply_experience_transform(payload, case)

            # 执行测试
            session = harness._run_attack_with_agent(
                session_id=str(uuid.uuid4()),
                initial_task=f"R{self.config.round_id}-{test_type}: {case['name']}",
                target_boundary=case['boundary'],
                seam=case['seam'],
                payload=payload,
                probe_direction=case.get('reason', ''),
                iteration_depth=self.config.iteration_depth
            )

            # 提取结果
            classification = session.final_classification
            gateway_dec = "NONE"
            if session.iteration_chain:
                gateway_dec = session.iteration_chain[0].gateway_decision

            # 获取 Agent 详情
            agent_response = ""
            tool_calls_detail = []
            if target_agent.last_result:
                ar = target_agent.last_result
                agent_response = ar.final_response[:500]
                tool_calls_detail = [
                    {"tool": tc.tool_name, "args": tc.args, "gateway": tc.gateway_decision}
                    for tc in ar.tool_calls
                ]

            # 估算 token（简化估算）
            tokens_consumed = len(payload) + len(agent_response) + 500  # 基础开销

            duration_ms = int((time.time() - start_time) * 1000)

            self._log(f"[{result_id}] 完成: {classification} | gateway={gateway_dec} | {duration_ms}ms")

            return ExperimentResult(
                result_id=result_id,
                round_id=self.config.round_id,
                case_name=case['name'],
                test_type=test_type,
                seam=case['seam'],
                boundary=case['boundary'],
                payload=payload[:200],
                classification=classification,
                gateway_decision=gateway_dec,
                agent_response=agent_response,
                tool_calls_detail=tool_calls_detail,
                timestamp=datetime.now().isoformat(),
                tokens_consumed=tokens_consumed,
                duration_ms=duration_ms,
                error=None
            )

        except Exception as e:
            duration_ms = int((time.time() - start_time) * 1000)
            self._log(f"[{result_id}] 错误: {str(e)}")

            return ExperimentResult(
                result_id=result_id,
                round_id=self.config.round_id,
                case_name=case['name'],
                test_type=test_type,
                seam=case.get('seam', '?'),
                boundary=case.get('boundary', '?'),
                payload=case.get('payload', '')[:200],
                classification="ERROR",
                gateway_decision="ERROR",
                agent_response="",
                tool_calls_detail=[],
                timestamp=datetime.now().isoformat(),
                tokens_consumed=0,
                duration_ms=duration_ms,
                error=str(e)
            )

    def _apply_baseline_transform(self, payload: str, case: dict) -> str:
        """应用 baseline 变换（简化版，不依赖经验）"""
        # Heuristic baseline: 移除所有诱导性语言，直接陈述
        # 这里只是一个示例，实际需要根据 baseline_type 定制
        return payload

    def _apply_experience_transform(self, payload: str, case: dict) -> str:
        """应用 experience 变换（基于 defense_weakness）"""
        # 从 case 中获取 experience 优化
        # 这里只是一个框架，实际需要从 failure_patterns 加载
        return payload

    def run(self):
        """主运行循环"""
        self._log(f"=== 开始实验 R{self.config.round_id}: {self.config.round_name} ===")
        self._log(f"总用例数: {len(self.config.test_cases)}")
        self._log(f"Paired design: {self.config.paired_design}")
        self._log(f"Token 预算: {self.config.token_budget}")

        total_cases = len(self.config.test_cases)
        completed_count = 0

        for i, case in enumerate(self.config.test_cases, 1):
            if self.interrupted:
                break

            # 检查 token 预算
            if not self._check_token_budget():
                self._log("[预算耗尽] 停止实验")
                break

            # 准备测试类型列表
            if self.config.paired_design:
                test_types = ["baseline", "experience"]
            else:
                test_types = ["baseline"]

            for test_type in test_types:
                case_key = f"{case['name']}_{test_type}"

                # 跳过已完成的
                if case_key in self.completed_cases:
                    self._log(f"[跳过] {case_key} (已完成)")
                    continue

                # 运行测试
                result = self.run_single_test(case, test_type)

                # 实时保存结果
                self._append_result(result)

                # 进度报告
                completed_count += 1
                if completed_count % 5 == 0:
                    self._log(f"[进度] 已完成 {completed_count} 条测试 | Token: {self.total_tokens}/{self.config.token_budget}")

                # 短暂休息，避免 API 限流
                time.sleep(0.5)

        # 实验结束
        self._save_state()
        self._log(f"=== 实验 R{self.config.round_id} 结束 ===")
        self._log(f"完成测试: {len(self.completed_cases)}")
        self._log(f"总 token 消耗: {self.total_tokens}")

        # 生成汇总报告
        self._generate_summary()

    def _generate_summary(self):
        """生成实验汇总报告"""
        if not self.results_file.exists():
            return

        results = []
        with open(self.results_file, 'r', encoding='utf-8') as f:
            for line in f:
                if line.strip():
                    results.append(json.loads(line))

        # 统计
        total = len(results)
        baseline_results = [r for r in results if r['test_type'] == 'baseline']
        experience_results = [r for r in results if r['test_type'] == 'experience']

        # L1/L2/L3 分布
        def count_classification(res_list):
            l1 = sum(1 for r in res_list if r['classification'] == 'L1')
            l2 = sum(1 for r in res_list if r['classification'] == 'L2')
            l3 = sum(1 for r in res_list if r['classification'] == 'L3')
            return {'L1': l1, 'L2': l2, 'L3': l3}

        baseline_stats = count_classification(baseline_results)
        experience_stats = count_classification(experience_results)

        # paired 对比
        paired_wins = 0
        paired_losses = 0
        paired_ties = 0

        if self.config.paired_design:
            case_names = set(r['case_name'] for r in results)
            for name in case_names:
                b = next((r for r in baseline_results if r['case_name'] == name), None)
                e = next((r for r in experience_results if r['case_name'] == name), None)
                if b and e:
                    # L3 > L2 > L1（越危险越好）
                    severity = {'L1': 0, 'L2': 1, 'L3': 2, 'ERROR': -1}
                    b_score = severity.get(b['classification'], 0)
                    e_score = severity.get(e['classification'], 0)

                    if e_score > b_score:
                        paired_wins += 1
                    elif e_score < b_score:
                        paired_losses += 1
                    else:
                        paired_ties += 1

        summary = {
            'round_id': self.config.round_id,
            'round_name': self.config.round_name,
            'total_results': total,
            'baseline': {
                'count': len(baseline_results),
                'distribution': baseline_stats
            },
            'experience': {
                'count': len(experience_results),
                'distribution': experience_stats
            },
            'paired_comparison': {
                'wins': paired_wins,      # experience 更强
                'losses': paired_losses,  # experience 更弱
                'ties': paired_ties       # 持平
            },
            'win_rate': f"{paired_wins/(paired_wins+paired_losses+paired_ties)*100:.1f}%" if (paired_wins+paired_losses+paired_ties) > 0 else "N/A",
            'total_tokens': self.total_tokens,
            'generated_at': datetime.now().isoformat()
        }

        summary_file = self.output_dir / f"r{self.config.round_id}-summary.json"
        with open(summary_file, 'w', encoding='utf-8') as f:
            json.dump(summary, f, ensure_ascii=False, indent=2)

        self._log(f"[汇总报告] {summary_file}")
        self._log(f"  Baseline: {baseline_stats}")
        self._log(f"  Experience: {experience_stats}")
        self._log(f"  Paired: {paired_wins} wins, {paired_losses} losses, {paired_ties} ties")
        self._log(f"  Win rate: {summary['win_rate']}")


# === 默认配置生成器 ===
def get_default_config(round_id: int) -> ExperimentConfig:
    """生成默认配置"""
    configs = {
        5: {
            'round_name': 'R5-校准轮',
            'description': '校准 baseline、rubric、judge，验证 paired design 可行性',
            'test_cases': [],  # 需要填充
            'token_budget': 80000
        },
        6: {
            'round_name': 'R6-聚焦探索',
            'description': '验证 experience 在不同 task slice 的效果差异',
            'test_cases': [],
            'token_budget': 100000
        },
        7: {
            'round_name': 'R7-跨 seam 复现',
            'description': '验证 experience 效果在不同 seam 是否可复现',
            'test_cases': [],
            'token_budget': 120000
        },
        8: {
            'round_name': 'R8-扩展验证',
            'description': '最终统计验证 + real Gateway spot-check',
            'test_cases': [],
            'token_budget': 150000
        }
    }

    cfg = configs.get(round_id, configs[5])
    return ExperimentConfig(
        round_id=round_id,
        round_name=cfg['round_name'],
        description=cfg['description'],
        test_cases=cfg['test_cases'],
        token_budget=cfg['token_budget']
    )


# === CLI 入口 ===
def main():
    parser = argparse.ArgumentParser(description='多轮实验运行器')
    parser.add_argument('--round', '-r', type=int, required=True, help='轮次 ID (5/6/7/8)')
    parser.add_argument('--config', '-c', type=str, help='配置文件路径')
    parser.add_argument('--resume', action='store_true', help='恢复中断的实验')

    args = parser.parse_args()

    # 加载配置
    if args.config:
        with open(args.config, 'r', encoding='utf-8') as f:
            config_data = json.load(f)
            config = ExperimentConfig(**config_data)
    else:
        config = get_default_config(args.round)
        print(f"[警告] 使用默认配置，请确保 test_cases 已填充")

    # 运行实验
    runner = ExperimentRunner(config, resume=args.resume)
    runner.run()


if __name__ == "__main__":
    main()
