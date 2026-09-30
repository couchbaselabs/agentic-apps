"""LLM access layer — OpenAI-compatible, pluggable, with provider fallback.

Mirrors PRINCE's "unified OpenAI-compatible endpoint exposing models from
multiple providers". Point LLM_BASE_URL at any compatible gateway. If a primary
call fails after retries, we automatically fall back to a secondary provider
(the article's "LLM fallback").

Set MOCK_LLM=true to run the ENTIRE pipeline deterministically with no network
access — every agent stage is served by `mock.py`. This is what powers the
offline demo/CI path.

Every call passes a `task` label so (a) mock mode can dispatch and (b) traces
are legible in logs/Langfuse.
"""
from __future__ import annotations

import json
from typing import Any, Optional

from tenacity import retry, stop_after_attempt, wait_exponential

from .config import settings
from . import mock


class LLMError(RuntimeError):
    pass


def _client(base_url: str, api_key: str):
    from openai import OpenAI  # imported lazily so mock mode needs no key
    return OpenAI(base_url=base_url, api_key=api_key or "not-needed")


class LLM:
    def __init__(self) -> None:
        self.mock = settings.mock_llm
        self._primary = None
        self._fallback = None

    # -- lazy clients --
    @property
    def primary(self):
        if self._primary is None:
            self._primary = _client(settings.llm_base_url, settings.llm_api_key)
        return self._primary

    @property
    def fallback(self):
        if self._fallback is None and settings.llm_fallback_base_url:
            self._fallback = _client(
                settings.llm_fallback_base_url, settings.llm_fallback_api_key
            )
        return self._fallback

    # ------------------------------------------------------------------
    def complete(
        self,
        messages: list[dict[str, str]],
        *,
        model: Optional[str] = None,
        fast: bool = False,
        temperature: float = 0.0,
        json_mode: bool = False,
        task: str = "generic",
    ) -> str:
        if self.mock:
            return mock.complete(task=task, messages=messages, json_mode=json_mode)

        model = model or (settings.llm_model_fast if fast else settings.llm_model_strong)
        try:
            return self._call(self.primary, model, messages, temperature, json_mode)
        except Exception as primary_exc:  # noqa: BLE001
            if self.fallback is not None:
                fb_model = (
                    settings.llm_fallback_model_fast if fast
                    else settings.llm_fallback_model_strong
                ) or model
                try:
                    return self._call(self.fallback, fb_model, messages, temperature, json_mode)
                except Exception as fb_exc:  # noqa: BLE001
                    raise LLMError(f"primary+fallback failed: {primary_exc} | {fb_exc}")
            raise LLMError(str(primary_exc))

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=1, max=8))
    def _call(self, client, model, messages, temperature, json_mode) -> str:
        kwargs: dict[str, Any] = {
            "model": model,
            "messages": messages,
            "temperature": temperature,
        }
        if json_mode:
            kwargs["response_format"] = {"type": "json_object"}
        resp = client.chat.completions.create(**kwargs)
        return resp.choices[0].message.content or ""

    # ------------------------------------------------------------------
    def json(
        self,
        messages: list[dict[str, str]],
        *,
        fast: bool = False,
        task: str = "generic",
        temperature: float = 0.0,
    ) -> Any:
        raw = self.complete(
            messages, fast=fast, temperature=temperature, json_mode=True, task=task
        )
        raw = raw.strip()
        # tolerate ```json fences
        if raw.startswith("```"):
            raw = raw.split("```", 2)[1]
            if raw.startswith("json"):
                raw = raw[4:]
        try:
            return json.loads(raw)
        except json.JSONDecodeError as exc:
            raise LLMError(f"expected JSON, got: {raw[:200]}") from exc


llm = LLM()
