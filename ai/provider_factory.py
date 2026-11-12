"""
AI Provider Factory for AutoGit AI.
Selects and configures the appropriate LLM client.
"""

from typing import Optional

from ai.llm_client import (
    AnthropicClient,
    BaseLLMClient,
    FallbackClient,
    GeminiClient,
    OpenAIClient,
)
from config.constants import (
    PROVIDER_ANTHROPIC,
    PROVIDER_GEMINI,
    PROVIDER_OPENAI,
)
from config.settings import settings
from utils.logger import logger


class AIProviderFactory:
    """Factory to instantiate the configured AI client."""

    @staticmethod
    def get_client(provider_name: Optional[str] = None) -> BaseLLMClient:
        provider = (provider_name or settings.DEFAULT_AI_PROVIDER or "").lower().strip()

        if provider == PROVIDER_GEMINI and settings.GEMINI_API_KEY:
            return GeminiClient()
        elif provider == PROVIDER_OPENAI and settings.OPENAI_API_KEY:
            return OpenAIClient()
        elif provider == PROVIDER_ANTHROPIC and settings.ANTHROPIC_API_KEY:
            return AnthropicClient()
        else:
            logger.debug(
                f"No API key configured for provider '{provider}'. Using FallbackClient."
            )
            return FallbackClient()

