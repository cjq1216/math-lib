"""
LLM 客户端抽象 + 实现

主 LLM：MiniMax API（OpenAI 兼容）
本地兜底：Ollama + Qwen2.5-14B

切换 provider 只改配置，业务代码无感。
"""
from abc import ABC, abstractmethod

import httpx

from app.core.config import settings


class LLMClient(ABC):
    """LLM 客户端抽象基类"""

    @abstractmethod
    async def chat(
        self,
        messages: list[dict],
        response_format: dict | None = None,
        temperature: float = 0.3,
        max_tokens: int = 4096,
    ) -> str:
        """调用 LLM，返回文本"""


class MiniMaxClient(LLMClient):
    """MiniMax API 客户端（OpenAI 兼容）"""

    def __init__(self):
        self.api_key = settings.minimax_api_key
        self.base_url = settings.minimax_base_url
        self.model = settings.minimax_model

    async def chat(
        self,
        messages: list[dict],
        response_format: dict | None = None,
        temperature: float = 0.3,
        max_tokens: int = 4096,
    ) -> str:
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        payload = {
            "model": self.model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
        }
        if response_format:
            payload["response_format"] = response_format

        async with httpx.AsyncClient(timeout=60.0) as client:
            r = await client.post(
                f"{self.base_url}/chat/completions",
                headers=headers,
                json=payload,
            )
            r.raise_for_status()
            data = r.json()
            return data["choices"][0]["message"]["content"]


class OllamaClient(LLMClient):
    """Ollama 本地客户端"""

    def __init__(self):
        self.base_url = settings.ollama_base_url
        self.model = settings.ollama_model

    async def chat(
        self,
        messages: list[dict],
        response_format: dict | None = None,
        temperature: float = 0.3,
        max_tokens: int = 4096,
    ) -> str:
        payload = {
            "model": self.model,
            "messages": messages,
            "stream": False,
            "options": {
                "temperature": temperature,
                "num_predict": max_tokens,
            },
        }
        if response_format:
            payload["format"] = "json"

        async with httpx.AsyncClient(timeout=120.0) as client:
            r = await client.post(
                f"{self.base_url}/api/chat",
                json=payload,
            )
            r.raise_for_status()
            data = r.json()
            return data["message"]["content"]


def get_llm_client() -> LLMClient:
    """根据配置获取客户端实例"""
    if settings.llm_provider == "ollama":
        return OllamaClient()
    return MiniMaxClient()
