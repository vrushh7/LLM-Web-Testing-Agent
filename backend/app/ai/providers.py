import asyncio
import json
from dataclasses import dataclass
from typing import Any

import httpx

from app.core.config import settings


class AIProviderError(RuntimeError):
    pass


@dataclass(frozen=True)
class AIResponse:
    provider: str
    model: str
    raw_text: str


class GeminiProvider:
    name = "gemini"

    async def generate(self, system_prompt: str, user_prompt: str) -> AIResponse:
        if not settings.GEMINI_API_KEY:
            raise AIProviderError("Gemini API key is not configured")

        last_error: str | None = None
        for model in settings.gemini_model_order:
            for attempt in range(2):
                try:
                    return await self._generate_with_model(model, system_prompt, user_prompt)
                except AIProviderError as exc:
                    last_error = str(exc)
                    retryable = any(token in last_error.lower() for token in ["404", "not found", "429", "503", "unavailable"])
                    if not retryable:
                        raise
                    if attempt == 0 and any(token in last_error.lower() for token in ["429", "503", "unavailable"]):
                        await asyncio.sleep(0.8)
                        continue
                    break

        raise AIProviderError(last_error or "Gemini request failed for all configured Flash models")

    async def _generate_with_model(self, model: str, system_prompt: str, user_prompt: str) -> AIResponse:
        url = f"{settings.GEMINI_API_URL}/models/{model}:generateContent?key={settings.GEMINI_API_KEY}"
        payload: dict[str, Any] = {
            "system_instruction": {"parts": [{"text": system_prompt}]},
            "contents": [{"role": "user", "parts": [{"text": user_prompt}]}],
            "generationConfig": {
                "temperature": 0,
                "topP": 0.3,
                "maxOutputTokens": 900,
                "response_mime_type": "application/json",
            },
        }

        async with httpx.AsyncClient(timeout=settings.AI_TIMEOUT_SECONDS) as client:
            response = await client.post(url, json=payload)
        if response.status_code >= 400:
            raise AIProviderError(f"Gemini request failed: {response.status_code} {response.text[:300]}")

        data = response.json()
        try:
            parts = data["candidates"][0]["content"]["parts"]
            text = "".join(part.get("text", "") for part in parts)
        except (KeyError, IndexError, TypeError) as exc:
            raise AIProviderError(f"Gemini returned an unexpected response: {json.dumps(data)[:300]}") from exc

        return AIResponse(provider=self.name, model=model, raw_text=text)


class OpenAIProvider:
    name = "openai"

    async def generate(self, system_prompt: str, user_prompt: str) -> AIResponse:
        if not settings.OPENAI_API_KEY:
            raise AIProviderError("OpenAI API key is not configured")

        url = f"{settings.OPENAI_API_URL}/chat/completions"
        payload = {
            "model": settings.OPENAI_MODEL,
            "temperature": 0,
            "max_tokens": 900,
            "response_format": {"type": "json_object"},
            "messages": [
                {"role": "system", "content": system_prompt + "\nReturn {\"steps\":[...]} for this provider."},
                {"role": "user", "content": user_prompt},
            ],
        }
        headers = {
            "Authorization": f"Bearer {settings.OPENAI_API_KEY}",
            "Content-Type": "application/json",
        }

        async with httpx.AsyncClient(timeout=settings.AI_TIMEOUT_SECONDS) as client:
            response = await client.post(url, json=payload, headers=headers)
        if response.status_code >= 400:
            raise AIProviderError(f"OpenAI request failed: {response.status_code} {response.text[:300]}")

        data = response.json()
        try:
            text = data["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError) as exc:
            raise AIProviderError(f"OpenAI returned an unexpected response: {json.dumps(data)[:300]}") from exc

        return AIResponse(provider=self.name, model=settings.OPENAI_MODEL, raw_text=text)


def provider_for_name(name: str):
    if name == "gemini":
        return GeminiProvider()
    if name == "openai":
        return OpenAIProvider()
    raise AIProviderError(f"Unknown AI provider: {name}")
