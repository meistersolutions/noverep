"""OpenAI-compatible chat + embeddings client (Ollama or cloud)."""

from __future__ import annotations

import json
import re
from typing import Any

import httpx

from app.config import settings


def llm_configured() -> bool:
    return bool((settings.llm_base_url or "").strip())


def _headers() -> dict[str, str]:
    headers = {"Content-Type": "application/json"}
    key = (settings.llm_api_key or "").strip()
    if key:
        headers["Authorization"] = f"Bearer {key}"
    return headers


def _base() -> str:
    return (settings.llm_base_url or "").rstrip("/")


async def chat_json(system: str, user: str, *, temperature: float = 0.2) -> dict[str, Any]:
    if not llm_configured():
        raise RuntimeError("LLM_BASE_URL is not configured")
    payload = {
        "model": settings.llm_model,
        "temperature": temperature,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        "response_format": {"type": "json_object"},
    }
    async with httpx.AsyncClient(timeout=120.0) as client:
        response = await client.post(
            f"{_base()}/chat/completions",
            headers=_headers(),
            json=payload,
        )
        # Some local models reject response_format — retry without it.
        if response.status_code >= 400 and "response_format" in (response.text or ""):
            payload.pop("response_format", None)
            response = await client.post(
                f"{_base()}/chat/completions",
                headers=_headers(),
                json=payload,
            )
        response.raise_for_status()
        data = response.json()
    content = (
        ((data.get("choices") or [{}])[0].get("message") or {}).get("content") or ""
    ).strip()
    return _parse_json_object(content)


async def embed_texts(texts: list[str]) -> list[list[float]]:
    if not llm_configured():
        raise RuntimeError("LLM_BASE_URL is not configured")
    if not texts:
        return []
    payload = {"model": settings.embedding_model, "input": texts}
    async with httpx.AsyncClient(timeout=120.0) as client:
        response = await client.post(
            f"{_base()}/embeddings",
            headers=_headers(),
            json=payload,
        )
        response.raise_for_status()
        data = response.json()
    items = data.get("data") or []
    items = sorted(items, key=lambda row: int(row.get("index") or 0))
    vectors: list[list[float]] = []
    for item in items:
        emb = item.get("embedding")
        if not isinstance(emb, list) or not emb:
            raise RuntimeError("embedding response missing vector")
        vectors.append([float(x) for x in emb])
    if len(vectors) != len(texts):
        raise RuntimeError("embedding count mismatch")
    return vectors


async def embed_text(text: str) -> list[float]:
    return (await embed_texts([text]))[0]


def _parse_json_object(content: str) -> dict[str, Any]:
    if not content:
        raise RuntimeError("empty LLM response")
    try:
        data = json.loads(content)
        if isinstance(data, dict):
            return data
    except json.JSONDecodeError:
        pass
    match = re.search(r"\{[\s\S]*\}", content)
    if not match:
        raise RuntimeError("LLM response was not JSON")
    data = json.loads(match.group(0))
    if not isinstance(data, dict):
        raise RuntimeError("LLM JSON was not an object")
    return data
