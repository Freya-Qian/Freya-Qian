"""LLM 客户端：OpenAI 兼容 chat/completions，异步，带超时、有限重试与统一错误。

含 SDK/客户端初始化失败兜底（无 Key 在重试逻辑之外，直接抛 NO_API_KEY）。
"""
from __future__ import annotations

import asyncio
from typing import AsyncIterator

import httpx

from app.config import settings


class LLMError(Exception):
    """统一业务错误：code 由全局异常处理器映射到 HTTP 状态码。"""

    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code
        self.message = message


# code → HTTP 状态码（集中定义，路由与异常处理器共用）
ERROR_STATUS = {
    "NO_API_KEY": 503,
    "TIMEOUT": 504,
    "NETWORK": 502,
    "MODEL_ERROR": 502,
    "PARSE_ERROR": 502,
    "INVALID_URL": 422,
    "FETCH_TIMEOUT": 504,
    "FETCH_ERROR": 502,
    "CONTENT_TOO_SHORT": 422,
    "NOT_FOUND": 404,
    "UNAUTHORIZED": 401,
    "CONFLICT": 409,
    "INVALID_INPUT": 422,
}


class LLMClient:
    def __init__(self, api_key: str | None = None, base_url: str | None = None,
                 model: str | None = None, timeout: float | None = None,
                 max_retries: int | None = None):
        self.api_key = api_key if api_key is not None else settings.model_api_key
        self.base_url = (base_url or settings.model_base_url).rstrip("/")
        self.model = model or settings.model_name
        self.timeout = timeout if timeout is not None else settings.model_timeout
        self.max_retries = max_retries if max_retries is not None else settings.model_max_retries

    def _headers(self) -> dict:
        return {"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"}

    def _payload(self, system: str, user: str, max_tokens: int, temperature: float,
                 stream: bool = False) -> dict:
        return {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            "max_tokens": max_tokens,
            "temperature": temperature,
            "stream": stream,
        }

    async def complete(self, system: str, user: str, max_tokens: int = 2000,
                       temperature: float = 0.6) -> str:
        """返回模型完整文本。无 Key 抛 NO_API_KEY；超时/网络/5xx 有限重试。"""
        if not self.api_key:
            raise LLMError("NO_API_KEY", "未配置模型 API Key，请在项目 .env 中填写 MODEL_API_KEY")

        url = f"{self.base_url}/chat/completions"
        last_err: LLMError | None = None
        for attempt in range(self.max_retries + 1):
            try:
                async with httpx.AsyncClient(timeout=self.timeout) as client:
                    resp = await client.post(
                        url, json=self._payload(system, user, max_tokens, temperature),
                        headers=self._headers(),
                    )
            except httpx.TimeoutException:
                last_err = LLMError("TIMEOUT", "模型调用超时，请稍后重试")
            except httpx.HTTPError:
                last_err = LLMError("NETWORK", "模型服务连接失败")
            else:
                if resp.status_code == 200:
                    try:
                        data = resp.json()
                        return data["choices"][0]["message"]["content"]
                    except (KeyError, IndexError, TypeError, ValueError):
                        last_err = LLMError("PARSE_ERROR", "模型服务返回结构异常")
                elif 400 <= resp.status_code < 500:
                    # 客户端错误不重试（含鉴权失败、参数错误）
                    raise LLMError("MODEL_ERROR", f"模型服务返回错误（HTTP {resp.status_code}）")
                else:
                    last_err = LLMError("MODEL_ERROR", f"模型服务返回错误（HTTP {resp.status_code}）")

            if attempt < self.max_retries:
                await asyncio.sleep(0.5 * (attempt + 1))

        raise last_err if last_err else LLMError("MODEL_ERROR", "模型调用失败")

    async def stream(self, system: str, user: str, max_tokens: int = 2000,
                     temperature: float = 0.6) -> AsyncIterator[str]:
        """流式返回 delta 文本。无 Key 抛 NO_API_KEY。"""
        if not self.api_key:
            raise LLMError("NO_API_KEY", "未配置模型 API Key，请在项目 .env 中填写 MODEL_API_KEY")

        url = f"{self.base_url}/chat/completions"
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                async with client.stream(
                    "POST", url,
                    json=self._payload(system, user, max_tokens, temperature, stream=True),
                    headers=self._headers(),
                ) as resp:
                    if resp.status_code != 200:
                        raise LLMError("MODEL_ERROR", f"模型服务返回错误（HTTP {resp.status_code}）")
                    async for line in resp.aiter_lines():
                        if not line or not line.startswith("data:"):
                            continue
                        data = line[5:].strip()
                        if data == "[DONE]":
                            break
                        import json as _json
                        try:
                            obj = _json.loads(data)
                            delta = obj["choices"][0]["delta"].get("content", "")
                        except (KeyError, IndexError, TypeError, ValueError):
                            continue
                        if delta:
                            yield delta
        except httpx.TimeoutException:
            raise LLMError("TIMEOUT", "模型调用超时，请稍后重试")
        except httpx.HTTPError:
            raise LLMError("NETWORK", "模型服务连接失败")
