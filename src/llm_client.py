from __future__ import annotations

import os
from dataclasses import dataclass

from dotenv import load_dotenv


@dataclass
class LLMStatus:
    available: bool
    model: str
    base_url: str
    last_error: str = ""


class LLMClient:
    def __init__(self) -> None:
        load_dotenv()
        self.model = os.getenv("OPENAI_MODEL", "gpt-4o-mini")
        self.api_key = os.getenv("OPENAI_API_KEY")
        self.base_url = os.getenv("OPENAI_BASE_URL")
        self.last_error = ""
        self._client = None
        if self.api_key:
            from openai import OpenAI

            kwargs = {
                "api_key": self.api_key,
                "timeout": float(os.getenv("OPENAI_TIMEOUT", "25")),
                "max_retries": int(os.getenv("OPENAI_MAX_RETRIES", "0")),
            }
            if self.base_url:
                kwargs["base_url"] = self.base_url
            self._client = OpenAI(**kwargs)

    @property
    def available(self) -> bool:
        return self._client is not None

    def status(self) -> LLMStatus:
        return LLMStatus(
            available=self.available,
            model=self.model,
            base_url=self.base_url or "OpenAI default",
            last_error=self.last_error,
        )

    def complete(self, system: str, user: str, temperature: float = 0.2) -> str:
        if not self._client:
            self.last_error = "OPENAI_API_KEY is empty; using local fallback logic."
            return ""
        try:
            response = self._client.chat.completions.create(
                model=self.model,
                temperature=temperature,
                messages=[
                    {"role": "system", "content": system},
                    {"role": "user", "content": user},
                ],
            )
            self.last_error = ""
            return response.choices[0].message.content or ""
        except Exception as exc:
            self.last_error = f"{type(exc).__name__}: {exc}"
            return ""
