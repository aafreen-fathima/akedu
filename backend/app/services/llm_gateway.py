"""LLM gateway (ADR-02): one interface, swappable providers.

Only this module talks to a model. Providers:
- ollama:    a local model served by Ollama (default; outlines never leave the machine)
- openai:    any OpenAI-compatible chat-completions API (hosted, LM Studio, vLLM...)
- heuristic: no model at all; a regex extractor used for offline demos and tests
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Protocol

import httpx

from ..config import Settings


class LLMError(Exception):
    pass


@dataclass
class LLMResult:
    data: dict
    raw: str


class LLMProvider(Protocol):
    name: str
    model: str

    def complete_json(self, system: str, prompt: str, schema: dict) -> LLMResult: ...


def _parse(raw: str) -> dict:
    raw = raw.strip()
    if raw.startswith("```"):
        raw = raw.strip("`")
        raw = raw[raw.find("{"):]
    start, end = raw.find("{"), raw.rfind("}")
    if start == -1 or end == -1:
        raise LLMError("Model reply contained no JSON object.")
    try:
        return json.loads(raw[start:end + 1])
    except json.JSONDecodeError as exc:
        raise LLMError(f"Model reply was not valid JSON: {exc}") from exc


class OllamaProvider:
    name = "ollama"

    def __init__(self, settings: Settings):
        self.model = settings.llm_model
        self.base = settings.llm_base_url.rstrip("/")
        self.timeout = settings.llm_timeout_s
        self.num_ctx = getattr(settings, "llm_num_ctx", 32768)

    def complete_json(self, system: str, prompt: str, schema: dict) -> LLMResult:
        body = {
            "model": self.model,
            "messages": [{"role": "system", "content": system}, {"role": "user", "content": prompt}],
            "format": schema,
            "stream": False,
            "options": {"temperature": 0, "num_ctx": self.num_ctx},
        }
        try:
            r = httpx.post(f"{self.base}/api/chat", json=body, timeout=self.timeout)
            r.raise_for_status()
        except httpx.HTTPError as exc:
            raise LLMError(f"Could not reach Ollama at {self.base}: {exc}") from exc
        raw = r.json().get("message", {}).get("content", "")
        return LLMResult(_parse(raw), raw)


class OpenAICompatibleProvider:
    name = "openai"

    def __init__(self, settings: Settings):
        self.model = settings.llm_model
        self.base = settings.llm_base_url.rstrip("/")
        self.key = settings.llm_api_key
        self.timeout = settings.llm_timeout_s

    def complete_json(self, system: str, prompt: str, schema: dict) -> LLMResult:
        body = {
            "model": self.model,
            "temperature": 0,
            "response_format": {"type": "json_object"},
            "messages": [
                {"role": "system", "content": system + "\nReply with one JSON object matching this schema:\n" + json.dumps(schema)},
                {"role": "user", "content": prompt},
            ],
        }
        headers = {"Authorization": f"Bearer {self.key}"} if self.key else {}
        try:
            r = httpx.post(f"{self.base}/chat/completions", json=body, headers=headers, timeout=self.timeout)
            r.raise_for_status()
        except httpx.HTTPError as exc:
            raise LLMError(f"LLM API call failed: {exc}") from exc
        raw = r.json()["choices"][0]["message"]["content"]
        return LLMResult(_parse(raw), raw)


class HeuristicProvider:
    """Not an LLM: a rule-based extractor with the same output shape.

    Lets the whole app run without a model (CI, demos on a laptop with no GPU),
    and gives the PoC a baseline to compare the LLM against.
    """

    name = "heuristic"
    model = "regex-v1"

    def complete_json(self, system: str, prompt: str, schema: dict) -> LLMResult:
        from .heuristic_extractor import extract

        data = extract(prompt)
        return LLMResult(data, json.dumps(data))


def get_provider(settings: Settings) -> LLMProvider:
    kind = settings.llm_provider.lower()
    if kind == "ollama":
        return OllamaProvider(settings)
    if kind == "openai":
        return OpenAICompatibleProvider(settings)
    if kind == "heuristic":
        return HeuristicProvider()
    raise ValueError(f"Unknown AKEDU_LLM_PROVIDER: {settings.llm_provider}")
