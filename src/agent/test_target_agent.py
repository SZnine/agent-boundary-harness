import os
import pytest
from src.agent.llm_config import LLMConfig


def test_llm_config_defaults():
    config = LLMConfig(api_key="sk-test")
    assert config.api_key == "sk-test"
    assert config.base_url == "https://www.aiapikey.net/v1"
    assert config.model == "gpt-5.4-mini"
    assert config.max_tokens == 1000
    assert config.temperature == 0.7


def test_llm_config_from_env(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "sk-env-test")
    monkeypatch.setenv("OPENAI_BASE_URL", "https://custom.api/v1")
    config = LLMConfig.from_env()
    assert config.api_key == "sk-env-test"
    assert config.base_url == "https://custom.api/v1"


def test_llm_config_from_env_defaults(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    monkeypatch.delenv("OPENAI_BASE_URL", raising=False)
    config = LLMConfig.from_env()
    assert config.base_url == "https://www.aiapikey.net/v1"


from src.agent.target_agent import TargetAgent, ToolCallRecord, TargetAgentResult


def test_tool_call_record_creation():
    record = ToolCallRecord(
        turn=1,
        tool_name="read_file",
        args={"path": "/workspace/notes.txt"},
        gateway_decision="ALLOW",
        gateway_reason="whitelist match",
        tool_output="file content here"
    )
    assert record.turn == 1
    assert record.tool_name == "read_file"


def test_target_agent_result_creation():
    result = TargetAgentResult(
        messages=[{"role": "user", "content": "test"}],
        tool_calls=[],
        gateway_decisions=[],
        final_response="done",
        turns_used=0
    )
    assert result.turns_used == 0
    assert result.final_response == "done"
    assert len(result.tool_calls) == 0