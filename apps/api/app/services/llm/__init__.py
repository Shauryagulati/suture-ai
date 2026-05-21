"""Provider-agnostic LLM access.

Every LLM call in application code goes through `get_llm_provider()`.
Do not import `anthropic` or `openai` directly — see ADR 007.
"""

from __future__ import annotations

from app.services.llm.base import JSONExtractionError, LLMProvider
from app.services.llm.factory import get_llm_provider

__all__ = ["JSONExtractionError", "LLMProvider", "get_llm_provider"]
