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

# Long structured-output phases (recipe) use the plain V2.5 model:
# MiMo Pro's reasoning consumes the output budget and 524s on big
# generations; V2.5 generates long-form reliably.
RECIPE_MODEL = "xiaomi/mimo-v2.5"

# Adversarial review (critic) — a DIFFERENT model than the builder to
# avoid self-review bias. Muse Spark Contributor is cheap + reliable.
CRITIC_MODEL = "meta/muse-spark-1.2-contributor"


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
    timeout: float = 300.0,
    retries: int = 2,
    model: str | None = None,
) -> str:
    """One chat completion with retry on transient 5xx/524. Returns text."""
    base, key, default_model = _config()
    body = {
        "model": model or default_model,
        "messages": messages,
        "temperature": temperature,
        "max_tokens": max_tokens,
    }
    last_err: Exception | None = None
    for attempt in range(retries + 1):
        try:
            with httpx.Client(timeout=timeout) as client:
                resp = client.post(
                    f"{base}/chat/completions",
                    headers={"Authorization": f"Bearer {key}"},
                    json=body,
                )
                resp.raise_for_status()
                data = resp.json()
            return data["choices"][0]["message"]["content"]
        except httpx.HTTPStatusError as e:
            last_err = e
            if e.response.status_code in (524, 502, 503, 429):
                import time

                time.sleep(2 * (attempt + 1))  # backoff
                continue
            raise
        except httpx.TimeoutException as e:
            last_err = e
            import time

            time.sleep(2 * (attempt + 1))
            continue
    raise RuntimeError(f"LLM call failed after {retries + 1} attempts: {last_err}")
