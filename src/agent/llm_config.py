import os
from dataclasses import dataclass


@dataclass
class LLMConfig:
    """LLM API 调用配置"""
    api_key: str
    base_url: str = "https://www.aiapikey.net/v1"
    model: str = "gpt-5.4-mini"
    max_tokens: int = 1000
    temperature: float = 0.7

    @staticmethod
    def from_env() -> "LLMConfig":
        api_key = os.environ.get("OPENAI_API_KEY", "")
        base_url = os.environ.get("OPENAI_BASE_URL", "https://www.aiapikey.net/v1")
        if not api_key:
            raise ValueError("OPENAI_API_KEY environment variable is required")
        return LLMConfig(api_key=api_key, base_url=base_url)