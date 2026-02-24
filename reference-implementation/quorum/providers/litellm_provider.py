# SPDX-License-Identifier: MIT
# Copyright 2026 SharedIntellect — https://github.com/SharedIntellect/quorum

"""
LiteLLM universal provider.

Wraps LiteLLM to support 100+ models (Anthropic, OpenAI, Mistral, Groq, etc.)
through a single interface. Model names pass through directly to LiteLLM.

Auth: set the appropriate env vars (ANTHROPIC_API_KEY, OPENAI_API_KEY, etc.)
or pass api_keys in the config.
"""

from __future__ import annotations

import json
import logging
import os
import re
from typing import Any

try:
    import litellm
    from litellm import completion
except ImportError as e:
    raise ImportError(
        "LiteLLM is required. Install it with: pip install litellm"
    ) from e

from quorum.providers.base import BaseProvider

logger = logging.getLogger(__name__)


class LiteLLMProvider(BaseProvider):
    """
    Universal LLM provider via LiteLLM.

    Handles all models with one interface. API keys are read from env vars
    automatically by LiteLLM. You can also pass extra_kwargs for provider-
    specific parameters.
    """

    def __init__(
        self,
        api_keys: dict[str, str] | None = None,
        extra_kwargs: dict[str, Any] | None = None,
    ):
        """
        Args:
            api_keys: Optional dict of {env_var_name: key_value} pairs.
                      These are injected into the environment before each call.
            extra_kwargs: Additional kwargs passed to every litellm.completion() call.
        """
        self._api_keys = api_keys or {}
        self._extra_kwargs = extra_kwargs or {}

        # Suppress LiteLLM's verbose logging unless debug mode is on
        litellm.suppress_debug_info = True
        litellm.set_verbose = False

        # Inject API keys into env now
        for key, value in self._api_keys.items():
            if value:
                os.environ[key] = value

    def complete(
        self,
        messages: list[dict[str, str]],
        model: str,
        temperature: float = 0.1,
        max_tokens: int = 4096,
    ) -> str:
        """Call any LiteLLM-supported model and return text."""
        logger.debug("Calling model=%s (temp=%.2f, max_tokens=%d)", model, temperature, max_tokens)
        try:
            response = completion(
                model=model,
                messages=messages,
                temperature=temperature,
                max_tokens=max_tokens,
                **self._extra_kwargs,
            )
            return response.choices[0].message.content or ""
        except Exception as e:
            logger.error("LLM call failed for model=%s: %s", model, e)
            raise

    def complete_json(
        self,
        messages: list[dict[str, str]],
        model: str,
        schema: dict[str, Any],
        temperature: float = 0.1,
    ) -> dict[str, Any]:
        """
        Call LLM requesting JSON output, then parse and return.

        Strategy:
        1. Append a JSON instruction to the last user message
        2. Call complete()
        3. Extract and parse the JSON block from the response
        4. Raise ValueError if parsing fails
        """
        # Append JSON instruction to the system or last user message
        json_instruction = (
            "\n\nRespond with ONLY valid JSON matching this schema. "
            "No markdown fences, no explanation, just the JSON object:\n"
            f"{json.dumps(schema, indent=2)}"
        )

        augmented_messages = list(messages)
        # If there's a user message at the end, append to it
        if augmented_messages and augmented_messages[-1]["role"] == "user":
            augmented_messages[-1] = {
                **augmented_messages[-1],
                "content": augmented_messages[-1]["content"] + json_instruction,
            }
        else:
            augmented_messages.append({"role": "user", "content": json_instruction})

        raw = self.complete(
            messages=augmented_messages,
            model=model,
            temperature=temperature,
            max_tokens=8192,  # JSON responses may be large
        )

        return self._parse_json(raw, model)

    def _parse_json(self, raw: str, model: str) -> dict[str, Any]:
        """Extract and parse JSON from LLM response, handling common formatting issues."""
        text = raw.strip()

        # Try direct parse first
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            pass

        # Strip markdown code fences if present
        fence_match = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.DOTALL)
        if fence_match:
            try:
                return json.loads(fence_match.group(1))
            except json.JSONDecodeError:
                pass

        # Try to find any JSON object in the response
        obj_match = re.search(r"\{.*\}", text, re.DOTALL)
        if obj_match:
            try:
                return json.loads(obj_match.group(0))
            except json.JSONDecodeError:
                pass

        raise ValueError(
            f"Could not parse JSON from model={model} response. "
            f"First 200 chars: {raw[:200]!r}"
        )
