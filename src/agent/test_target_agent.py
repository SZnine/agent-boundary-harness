import sys, io
if sys.platform == "win32":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')

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