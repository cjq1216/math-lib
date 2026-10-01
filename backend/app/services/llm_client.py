"""线上 LLM 与 Embedding 客户端抽象与实现（支持 MiniMax 及 OpenAI 兼容协议）。

特性：
1. 纯线上商用大模型调用（MiniMax / OpenAI 兼容协议），零本地模型权重部署负担；
2. 自动化 3 次指数退避重试（针对 429 速率限制、502/503/504 服务抖动与网络超时）；
3. 长文本切题 120s 超时保护；
4. 深度 JSON 模式提取器（自动剥离 Markdown ```json 代码块及首尾闲聊）；
5. 线上 Embedding 批量向量计算接口。
"""

from __future__ import annotations

import asyncio
import json
import re
from abc import ABC, abstractmethod
from typing import Any

import httpx
from loguru import logger

from app.core.config import settings


class LLMError(Exception):
    """LLM 调用基类异常"""

    def __init__(self, message: str, status_code: int | None = None, details: Any = None):
        super().__init__(message)
        self.message = message
        self.status_code = status_code
        self.details = details


class LLMConfigurationError(LLMError):
    """LLM 配置缺失（如缺少 API Key）"""


class LLMClient(ABC):
    """LLM 客户端抽象基类"""

    @abstractmethod
    async def chat(
        self,
        messages: list[dict[str, str]],
        temperature: float = 0.1,
        max_tokens: int = 4096,
        response_format: dict[str, str] | None = None,
    ) -> str:
        """调用大模型，返回文本响应。"""

    @abstractmethod
    async def embed(self, texts: list[str]) -> list[list[float]]:
        """调用 Embedding 模型，返回向量数组。"""


class MiniMaxClient(LLMClient):
    """MiniMax 线上商用大模型客户端（OpenAI 兼容协议）。"""

    def __init__(
        self,
        api_key: str | None = None,
        base_url: str | None = None,
        model: str | None = None,
        timeout: float = 120.0,
        max_retries: int = 3,
    ):
        self.api_key = api_key or settings.minimax_api_key
        self.base_url = (base_url or settings.minimax_base_url or "https://api.minimaxi.com/v1").rstrip("/")
        self.model = model or settings.minimax_model or "MiniMax-Text-01"
        self.embedding_model = settings.embedding_model or "bge-m3"
        self.timeout = timeout
        self.max_retries = max_retries

    def _get_headers(self) -> dict[str, str]:
        if not self.api_key:
            raise LLMConfigurationError(
                "MiniMax API Key 未配置。请在 .env 中设置 MINIMAX_API_KEY 后再使用 AI 功能。"
            )
        return {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

    async def chat(
        self,
        messages: list[dict[str, str]],
        temperature: float = 0.1,
        max_tokens: int = 4096,
        response_format: dict[str, str] | None = None,
    ) -> str:
        """调用 MiniMax Chat Completions，具备自动退避重试机制。"""
        headers = self._get_headers()
        url = f"{self.base_url}/chat/completions"

        payload: dict[str, Any] = {
            "model": self.model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
        }
        if response_format:
            payload["response_format"] = response_format

        last_error: Exception | None = None

        for attempt in range(self.max_retries):
            try:
                async with httpx.AsyncClient(timeout=self.timeout) as client:
                    resp = await client.post(url, headers=headers, json=payload)

                    if resp.status_code == 200:
                        data = resp.json()
                        choices = data.get("choices", [])
                        if not choices:
                            raise LLMError("MiniMax 返回空选项列表", status_code=200, details=data)
                        content = choices[0].get("message", {}).get("content", "")
                        return content

                    # 速率限制 429 或服务端暂时错误 502/503/504 执行退避重试
                    if resp.status_code in (429, 502, 503, 504) and attempt < self.max_retries - 1:
                        backoff = 2 ** attempt * 1.5
                        logger.warning(
                            f"MiniMax 调用遇到 {resp.status_code}，将在 {backoff:.1f} 秒后执行第 {attempt + 1} 次重试..."
                        )
                        await asyncio.sleep(backoff)
                        continue

                    # 其他错误直接抛出
                    err_msg = resp.text
                    try:
                        err_json = resp.json()
                        err_msg = err_json.get("error", {}).get("message") or resp.text
                    except Exception:
                        pass
                    raise LLMError(f"MiniMax API 响应错误 ({resp.status_code}): {err_msg}", status_code=resp.status_code)

            except (httpx.ConnectError, httpx.ReadTimeout, httpx.RemoteProtocolError) as e:
                last_error = e
                if attempt < self.max_retries - 1:
                    backoff = 2 ** attempt * 1.5
                    logger.warning(f"网络抖动或超时 ({e})，将在 {backoff:.1f} 秒后重试...")
                    await asyncio.sleep(backoff)
                else:
                    raise LLMError(f"连接 MiniMax 服务失败或响应超时 ({type(e).__name__}): {e}") from e

        if last_error:
            raise LLMError(f"重试全部耗尽，MiniMax 调用失败: {last_error}") from last_error
        raise LLMError("未知 LLM 错误")

    async def embed(self, texts: list[str]) -> list[list[float]]:
        """调用线上 Embedding 接口获取文本向量。"""
        if not texts:
            return []

        headers = self._get_headers()
        url = f"{self.base_url}/embeddings"

        # 支持标准 OpenAI input 字段与 MiniMax 兼容格式
        payload = {
            "model": self.embedding_model,
            "input": texts,
        }

        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.post(url, headers=headers, json=payload)
            if resp.status_code != 200:
                raise LLMError(f"MiniMax Embedding 失败 ({resp.status_code}): {resp.text}", status_code=resp.status_code)

            data = resp.json()
            items = data.get("data", [])
            # 保证按原始索引顺序返回
            items_sorted = sorted(items, key=lambda x: x.get("index", 0))
            return [it["embedding"] for it in items_sorted]


def extract_json_payload(raw_text: str) -> Any:
    """从 LLM 返回的文本中提取并解析 JSON 对象或数组（自动剥离 Markdown 围栏与杂质）。"""
    if not raw_text or not raw_text.strip():
        raise ValueError("大模型返回内容为空，未包含有效 JSON")

    text = raw_text.strip()

    # 1. 尝试匹配 ```json ... ``` 或 ``` ... ``` 代码块
    fence_pattern = re.compile(r"```(?:json)?\s*([\s\S]*?)\s*```", re.IGNORECASE)
    matches = fence_pattern.findall(text)
    if matches:
        candidate = matches[0].strip()
        try:
            return json.loads(candidate)
        except json.JSONDecodeError:
            pass

    # 2. 尝试寻找最外层大括号 {...} 或中括号 [...]
    first_brace = text.find("{")
    last_brace = text.rfind("}")
    if first_brace != -1 and last_brace != -1 and last_brace > first_brace:
        candidate = text[first_brace : last_brace + 1]
        try:
            return json.loads(candidate)
        except json.JSONDecodeError:
            pass

    first_bracket = text.find("[")
    last_bracket = text.rfind("]")
    if first_bracket != -1 and last_bracket != -1 and last_bracket > first_bracket:
        candidate = text[first_bracket : last_bracket + 1]
        try:
            return json.loads(candidate)
        except json.JSONDecodeError:
            pass

    # 3. 直接尝试整体 loads
    return json.loads(text)


def get_llm_client() -> LLMClient:
    """获取单例/默认线上 LLM 客户端。"""
    return MiniMaxClient()
