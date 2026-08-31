"""
GeminiEngine — Google Gemini API engine for Language Tutor

Talks to the Gemini Developer API (aistudio.google.com) using the
OpenAI-compatible endpoint Google exposes. Free tier: 15 RPM,
1M tokens/day for gemini-2.0-flash.

Setup:
    export GOOGLE_API_KEY="your-key-from-aistudio.google.com"

Usage in strategy config:
    {
        "engine": "gemini",
        "model":  "gemini-2.0-flash",
    }
"""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from typing import Optional


GEMINI_BASE_URL = "https://generativelanguage.googleapis.com/v1beta/openai"
DEFAULT_MODEL = "gemini-2.0-flash"


class GeminiEngine:
    """Minimal LLM engine wrapper for Google Gemini via OpenAI-compat API.

    Implements the same interface as OllamaEngine.generate() so it can be
    used as a drop-in replacement in EngineManager.
    """

    def __init__(
        self,
        model_name: str = DEFAULT_MODEL,
        api_key: Optional[str] = None,
        timeout: int = 120,
        max_context: int = 32768,
        system_prompt: Optional[str] = None,
    ) -> None:
        self.model_name = model_name
        self.api_key = api_key or os.environ.get("GOOGLE_API_KEY", "")
        self.timeout = timeout
        self.max_context_length = max_context
        self.system_prompt = system_prompt or ""

        if not self.api_key:
            raise RuntimeError(
                "GOOGLE_API_KEY not set. "
                "Get a free key at https://aistudio.google.com/apikey "
                "then: export GOOGLE_API_KEY='your-key'"
            )

    # ------------------------------------------------------------------
    # Public interface (matches OllamaEngine.generate signature)
    # ------------------------------------------------------------------

    def generate(
        self,
        prompt: str,
        system_prompt: Optional[str] = None,
        max_tokens: int = 1024,
        temperature: float = 0.7,
        **kwargs,
    ) -> str:
        """Generate a response from Gemini."""
        sys = system_prompt or self.system_prompt
        messages = []
        if sys:
            messages.append({"role": "system", "content": sys})
        messages.append({"role": "user", "content": prompt})

        return self._call(messages, max_tokens=max_tokens, temperature=temperature)

    def generate_structured(self, prompt: str, response_model, **kwargs) -> object:
        """Generate and parse a structured response.

        Asks Gemini to return JSON matching response_model's schema,
        then parses it. Falls back to generate() if parsing fails.
        """
        import re as _re

        schema_hint = self._schema_hint(response_model)
        full_prompt = f"{prompt}\n\nRespond with JSON only matching this schema:\n{schema_hint}"
        raw = self.generate(
            full_prompt,
            system_prompt=kwargs.get("system_prompt", self.system_prompt),
            max_tokens=kwargs.get("max_tokens", 1024),
        )

        # Strip markdown fences if present
        raw_clean = _re.sub(r"^```[a-z]*\s*|\s*```$", "", raw.strip(), flags=_re.MULTILINE)
        try:
            data = json.loads(raw_clean)
            return response_model(**data)
        except Exception:
            # Try extracting first JSON object
            m = _re.search(r"\{.*\}", raw_clean, _re.DOTALL)
            if m:
                try:
                    return response_model(**json.loads(m.group()))
                except Exception:
                    pass
        # Return empty model as fallback
        try:
            return response_model()
        except Exception:
            raise ValueError(
                f"Could not parse Gemini response as {response_model.__name__}: {raw[:200]}"
            )

    def count_tokens(self, text: str) -> int:
        """Rough token count — Gemini uses ~4 chars/token."""
        return len(text) // 4

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _call(
        self,
        messages: list,
        max_tokens: int = 1024,
        temperature: float = 0.7,
    ) -> str:
        url = f"{GEMINI_BASE_URL}/chat/completions"
        payload = {
            "model": self.model_name,
            "messages": messages,
            "max_tokens": max_tokens,
            "temperature": temperature,
        }
        data = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(
            url,
            data=data,
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {self.api_key}",
            },
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                result = json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            body = e.read().decode("utf-8", errors="replace")
            raise RuntimeError(f"Gemini API error {e.code}: {body[:400]}") from e

        try:
            return result["choices"][0]["message"]["content"]
        except (KeyError, IndexError) as e:
            raise RuntimeError(f"Unexpected Gemini response shape: {result}") from e

    @staticmethod
    def _schema_hint(model) -> str:
        """Return a JSON schema hint string from a Pydantic model."""
        try:
            return json.dumps(model.model_json_schema(), indent=2)
        except Exception:
            try:
                return json.dumps(model.schema(), indent=2)
            except Exception:
                return str(model)
