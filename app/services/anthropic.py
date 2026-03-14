from __future__ import annotations

import json

import httpx


class AnthropicError(RuntimeError):
    pass


class AnthropicService:
    def __init__(
        self,
        api_key: str,
        model: str,
        api_url: str,
        version: str,
    ) -> None:
        self.api_key = api_key
        self.model = model
        self.api_url = api_url
        self.version = version
        self._client = httpx.AsyncClient(timeout=httpx.Timeout(120.0))

    async def close(self) -> None:
        await self._client.aclose()

    async def chat(
        self,
        *,
        system_prompt: str,
        messages: list[dict[str, str]],
        temperature: float = 0.1,
        max_tokens: int = 4096,
    ) -> str:
        payload = {
            "model": self.model,
            "max_tokens": max_tokens,
            "temperature": temperature,
            "system": system_prompt,
            "messages": messages,
        }
        headers = {
            "x-api-key": self.api_key,
            "anthropic-version": self.version,
            "content-type": "application/json",
        }

        response = await self._client.post(self.api_url, headers=headers, json=payload)
        if response.status_code >= 400:
            raise AnthropicError(
                f"Anthropic request failed with {response.status_code}: {response.text}"
            )

        data = response.json()
        text_blocks = [
            block.get("text", "")
            for block in data.get("content", [])
            if block.get("type") == "text"
        ]
        content = "\n".join(part for part in text_blocks if part).strip()
        if not content:
            raise AnthropicError(f"No text content returned by Anthropic: {json.dumps(data)}")
        return content
