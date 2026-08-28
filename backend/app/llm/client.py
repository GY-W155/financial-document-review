"""OpenAI 兼容 LLM 客户端：文本对话 / 视觉 / 结构化提取。

通过 OPENAI_BASE_URL / OPENAI_API_KEY / OPENAI_MODEL 配置，兼容
DeepSeek / Qwen / Kimi / GPT 等。任一步失败即时抛出，由上层降级为规则分析。
"""
from __future__ import annotations

import base64
import json
import logging
from typing import Any

from openai import AsyncOpenAI

from ..config import settings

logger = logging.getLogger(__name__)
_client: AsyncOpenAI | None = None


def _get_client() -> AsyncOpenAI | None:
    global _client
    if not settings.OPENAI_API_KEY:
        return None
    if _client is None:
        _client = AsyncOpenAI(api_key=settings.OPENAI_API_KEY, base_url=settings.OPENAI_BASE_URL)
    return _client


def llm_available() -> bool:
    return bool(settings.OPENAI_API_KEY) and settings.LLM_ENABLED


async def chat(messages: list[dict[str, str]], model: str | None = None,
               temperature: float = 0.2, max_tokens: int = 2000) -> str:
    client = _get_client()
    if client is None:
        raise RuntimeError("LLM 未配置：OPENAI_API_KEY 为空或 LLM_ENABLED=False")
    resp = await client.chat.completions.create(
        model=model or settings.OPENAI_MODEL,
        messages=messages,
        temperature=temperature,
        max_tokens=max_tokens,
    )
    return resp.choices[0].message.content or ""


async def chat_vision(image_base64: str, prompt: str, model: str | None = None) -> str:
    client = _get_client()
    if client is None:
        raise RuntimeError("LLM 未配置")
    resp = await client.chat.completions.create(
        model=model or settings.OPENAI_VISION_MODEL,
        messages=[
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": prompt},
                    {"type": "image_url",
                     "image_url": {"url": f"data:image/png;base64,{image_base64}"}},
                ],
            }
        ],
        temperature=0.0,
    )
    return resp.choices[0].message.content or ""


async def extract_json(messages: list[dict[str, str]]) -> dict[str, Any]:
    """要求模型返回 JSON，并做稳健解析。"""
    text = await chat(messages, temperature=0.0, max_tokens=2500)
    return parse_json_loose(text)


def parse_json_loose(text: str) -> dict[str, Any]:
    """尽力从模型输出中解析 JSON。"""
    text = text.strip()
    # 去掉 ```json ... ``` 包裹
    if text.startswith("```"):
        text = text.split("\n", 1)[-1]
        if text.endswith("```"):
            text = text[:-3]
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        start = text.find("{")
        end = text.rfind("}")
        if start != -1 and end != -1 and end > start:
            try:
                return json.loads(text[start:end + 1])
            except json.JSONDecodeError:
                pass
    return {}


def encode_image_base64(data: bytes) -> str:
    return base64.b64encode(data).decode()


async def summarize_risk(risk_list: list[dict]) -> str:
    """基于风险项生成整体审核建议。LLM 不可用时回退规则式。"""
    if not llm_available() or not risk_list:
        return ""
    brief = json.dumps(risk_list, ensure_ascii=False)[:6000]
    try:
        return await chat([
            {"role": "system", "content": "你是资深财务风控专家。基于风险项列表输出一段简短整体审核建议（100字内），聚焦最严重问题。"},
            {"role": "user", "content": brief},
        ], max_tokens=400)
    except Exception as exc:  # pragma: no cover
        logger.warning("LLM summarize failed: %s", exc)
        return ""
