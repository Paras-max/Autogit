"""
LLM Client abstraction supporting Google Gemini, OpenAI, Anthropic, and safe Fallback.
Uses httpx for resilient asynchronous communication with timeouts.
"""

from abc import ABC, abstractmethod
import json
from typing import Optional
import httpx

from config.settings import settings
from utils.logger import logger


class BaseLLMClient(ABC):
    """Abstract interface for LLM providers."""

    @abstractmethod
    async def generate_response(
        self, system_prompt: str, user_prompt: str, timeout: float = 25.0
    ) -> Optional[str]:
        pass


class GeminiClient(BaseLLMClient):
    """Google Gemini API client using REST endpoint."""

    API_URL = "https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent"

    def __init__(self, api_key: Optional[str] = None):
        self.api_key = api_key or settings.GEMINI_API_KEY

    async def generate_response(
        self, system_prompt: str, user_prompt: str, timeout: float = 25.0
    ) -> Optional[str]:
        if not self.api_key:
            logger.warning("Gemini API key is not configured.")
            return None

        url = f"{self.API_URL}?key={self.api_key}"
        payload = {
            "contents": [
                {
                    "parts": [
                        {"text": f"SYSTEM INSTRUCTION: {system_prompt}\n\nUSER REQUEST: {user_prompt}"}
                    ]
                }
            ],
            "generationConfig": {
                "temperature": 0.2,
                "responseMimeType": "application/json",
            },
        }

        try:
            async with httpx.AsyncClient(timeout=timeout) as client:
                res = await client.post(url, json=payload)
                if res.status_code == 200:
                    data = res.json()
                    candidates = data.get("candidates", [])
                    if candidates:
                        parts = candidates[0].get("content", {}).get("parts", [])
                        if parts:
                            return parts[0].get("text")
                else:
                    logger.warning(f"Gemini API returned status {res.status_code}: {res.text[:200]}")
                    return None
        except Exception as e:
            logger.error(f"Gemini API request failed: {e}")
            return None


class OpenAIClient(BaseLLMClient):
    """OpenAI API client using chat completions REST endpoint."""

    API_URL = "https://api.openai.com/v1/chat/completions"

    def __init__(self, api_key: Optional[str] = None):
        self.api_key = api_key or settings.OPENAI_API_KEY

    async def generate_response(
        self, system_prompt: str, user_prompt: str, timeout: float = 25.0
    ) -> Optional[str]:
        if not self.api_key:
            logger.warning("OpenAI API key is not configured.")
            return None

        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        payload = {
            "model": "gpt-4o-mini",
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            "temperature": 0.2,
            "response_format": {"type": "json_object"},
        }

        try:
            async with httpx.AsyncClient(timeout=timeout) as client:
                res = await client.post(self.API_URL, headers=headers, json=payload)
                if res.status_code == 200:
                    data = res.json()
                    choices = data.get("choices", [])
                    if choices:
                        return choices[0].get("message", {}).get("content")
                else:
                    logger.warning(f"OpenAI API returned status {res.status_code}")
                    return None
        except Exception as e:
            logger.error(f"OpenAI API request failed: {e}")
            return None


class AnthropicClient(BaseLLMClient):
    """Anthropic API client using messages REST endpoint."""

    API_URL = "https://api.anthropic.com/v1/messages"

    def __init__(self, api_key: Optional[str] = None):
        self.api_key = api_key or settings.ANTHROPIC_API_KEY

    async def generate_response(
        self, system_prompt: str, user_prompt: str, timeout: float = 25.0
    ) -> Optional[str]:
        if not self.api_key:
            logger.warning("Anthropic API key is not configured.")
            return None

        headers = {
            "x-api-key": self.api_key,
            "anthropic-version": "2023-06-01",
            "Content-Type": "application/json",
        }
        payload = {
            "model": "claude-3-haiku-20240307",
            "system": system_prompt,
            "messages": [
                {"role": "user", "content": user_prompt},
            ],
            "max_tokens": 1024,
            "temperature": 0.2,
        }

        try:
            async with httpx.AsyncClient(timeout=timeout) as client:
                res = await client.post(self.API_URL, headers=headers, json=payload)
                if res.status_code == 200:
                    data = res.json()
                    content = data.get("content", [])
                    if content and content[0].get("type") == "text":
                        return content[0].get("text")
                else:
                    logger.warning(f"Anthropic API returned status {res.status_code}")
                    return None
        except Exception as e:
            logger.error(f"Anthropic API request failed: {e}")
            return None


class FallbackClient(BaseLLMClient):
    """
    Deterministic fallback client when external AI provider is unconfigured or unavailable.
    Returns None to instruct downstream agents to use their rule-based domain fallbacks.
    """

    async def generate_response(
        self, system_prompt: str, user_prompt: str, timeout: float = 25.0
    ) -> Optional[str]:
        return None
