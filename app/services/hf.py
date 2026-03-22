from __future__ import annotations

from huggingface_hub import AsyncInferenceClient


class HFError(RuntimeError):
    pass


class HFService:
    def __init__(
        self,
        api_key: str,
        model: str,
    ) -> None:
        self.api_key = api_key
        self.model = model
        self._client = AsyncInferenceClient(
            model=self.model,
            token=self.api_key,
            timeout=120.0,
        )

    async def close(self) -> None:
        pass

    async def chat(
        self,
        *,
        system_prompt: str,
        messages: list[dict[str, str]],
        temperature: float = 0.1,
        max_tokens: int = 4096,
    ) -> str:
        full_messages: list[dict[str, str]] = [
            {"role": "system", "content": system_prompt},
            *messages,
        ]

        try:
            response = await self._client.chat_completion(
                messages=full_messages,
                temperature=temperature,
                max_tokens=max_tokens,
            )
        except Exception as exc:
            raise HFError(f"HuggingFace request failed: {exc}") from exc

        content = response.choices[0].message.content
        if not content or not content.strip():
            raise HFError("No text content returned by HuggingFace.")
        return content.strip()
