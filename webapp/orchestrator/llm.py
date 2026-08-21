"""Thin OpenAI-compatible LLM client.

Any OpenAI-compatible endpoint works (CommandCode, OpenRouter, local, ...).
Configured via env vars:
  OMP_LLM_BASE_URL  (default: https://api.commandcode.ai/provider/v1)
  OMP_LLM_API_KEY   (required)
  OMP_LLM_MODEL     (default: commandcode/xiaomi/mimo-v2.5-pro)
"""
from __future__ import annotations

import os

import httpx

DEFAULT_BASE = "https://api.commandcode.ai/provider/v1"
DEFAULT_MODEL = "xiaomi/mimo-v2.5-pro"


def _config() -> tuple[str, str, str]:
    base = os.environ.get("OMP_LLM_BASE_URL", DEFAULT_BASE).rstrip("/")
    key = os.environ.get("OMP_LLM_API_KEY", "")
    model = os.environ.get("OMP_LLM_MODEL", DEFAULT_MODEL)
    if not key:
        raise RuntimeError("OMP_LLM_API_KEY is not set")
    return base, key, model


def chat(
    messages: list[dict[str, str]],
    *,
    temperature: float = 0.4,
    max_tokens: int = 4000,
    timeout: float = 120.0,
) -> str:
    """One chat completion. Returns the assistant text (or raises)."""
    base, key, model = _config()
    body = {
        "model": model,
        "messages": messages,
        "temperature": temperature,
        "max_tokens": max_tokens,
    }
    with httpx.Client(timeout=timeout) as client:
        resp = client.post(
            f"{base}/chat/completions",
            headers={"Authorization": f"Bearer {key}"},
            json=body,
        )
        resp.raise_for_status()
        data = resp.json()
    return data["choices"][0]["message"]["content"]
