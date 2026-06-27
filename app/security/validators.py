# Copyright 2025 Google LLC
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     https://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""Security validators for VibeCast — Day 4 whitepaper, Pillar 4 (Application & Runtime).

This module provides three layers of defence for user-supplied text that flows
into generative-AI tools (Kling video, ElevenLabs TTS):

1. **Sanitisation** — strips shell metacharacters and zero-width Unicode
   characters that could carry invisible payloads.
2. **Injection detection** — compiled regex patterns that flag common prompt-
   injection and shell-escape attempts.
3. **ADK callback** — a ``before_tool_callback`` that validates and gates tool
   execution at the framework level so no unsafe input ever reaches an
   external API.
"""

from __future__ import annotations

import logging
import re
from typing import Any

from google.adk.agents.callback_context import CallbackContext

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_DEFAULT_MAX_LENGTH: int = 2500
"""Default maximum prompt length — matches the Kling AI character limit."""

_TTS_MAX_LENGTH: int = 5000
"""Maximum text length accepted by the TTS pipeline."""

_SHELL_META_CHARS: re.Pattern[str] = re.compile(r"[;|&$`\\!{}<>]")
"""Characters that have special meaning in POSIX shells."""

_ZERO_WIDTH_CHARS: re.Pattern[str] = re.compile(
    "["
    "\u200b"  # zero-width space
    "\u200c"  # zero-width non-joiner
    "\u200d"  # zero-width joiner
    "\u2060"  # word joiner
    "\ufeff"  # zero-width no-break space / BOM
    "\u00ad"  # soft hyphen (invisible in most renderers)
    "\u200e"  # left-to-right mark
    "\u200f"  # right-to-left mark
    "\u202a"  # left-to-right embedding
    "\u202b"  # right-to-left embedding
    "\u202c"  # pop directional formatting
    "\u202d"  # left-to-right override
    "\u202e"  # right-to-left override
    "]"
)
"""Zero-width and invisible Unicode characters used in payload-smuggling attacks."""

# ---------------------------------------------------------------------------
# Injection patterns
# ---------------------------------------------------------------------------

INJECTION_PATTERNS: list[re.Pattern[str]] = [
    re.compile(r"ignore\s+previous\s+instructions", re.IGNORECASE),
    re.compile(r"system\s+prompt", re.IGNORECASE),
    re.compile(r"you\s+are\s+now", re.IGNORECASE),
    re.compile(r"forget\s+everything", re.IGNORECASE),
    re.compile(r"rm\s+-rf\b", re.IGNORECASE),
    re.compile(r"\bsudo\b", re.IGNORECASE),
    re.compile(r"\bwget\b", re.IGNORECASE),
    re.compile(r"\bcurl\b", re.IGNORECASE),
]
"""Compiled regex patterns that flag common prompt-injection and shell-escape
attempts.  Checked by :func:`detect_injection`."""


# ---------------------------------------------------------------------------
# Public helpers
# ---------------------------------------------------------------------------


def sanitize_prompt(text: str, *, max_length: int = _DEFAULT_MAX_LENGTH) -> str:
    """Strip dangerous characters from *text* and enforce a length ceiling.

    Processing order (each step feeds the next):

    1. Remove shell metacharacters (``; | & $ `` ` `` \\ ! { } < >``).
    2. Remove zero-width / invisible Unicode characters.
    3. Strip leading and trailing whitespace.
    4. Truncate to *max_length* characters.

    Args:
        text: Raw user input.
        max_length: Upper bound on returned string length.  Defaults to
            ``2500`` (Kling AI limit).

    Returns:
        The cleaned, length-bounded string.
    """
    cleaned: str = _SHELL_META_CHARS.sub("", text)
    cleaned = _ZERO_WIDTH_CHARS.sub("", cleaned)
    cleaned = cleaned.strip()
    cleaned = cleaned[:max_length]
    return cleaned


def validate_video_prompt(prompt: str) -> str:
    """Sanitise and validate a video-generation prompt.

    Args:
        prompt: Raw prompt destined for the Kling AI video generator.

    Returns:
        The sanitised prompt, guaranteed to be non-empty and at most
        2 500 characters.

    Raises:
        ValueError: If the prompt is empty after sanitisation or exceeds the
            Kling character limit.
    """
    sanitized: str = sanitize_prompt(prompt, max_length=_DEFAULT_MAX_LENGTH)

    if not sanitized:
        raise ValueError(
            "Video prompt is empty after sanitisation.  "
            "Please provide meaningful descriptive text."
        )

    if len(sanitized) > _DEFAULT_MAX_LENGTH:
        raise ValueError(
            f"Video prompt exceeds the {_DEFAULT_MAX_LENGTH}-character Kling AI "
            f"limit (got {len(sanitized)} characters)."
        )

    return sanitized


def validate_tts_text(text: str) -> str:
    """Sanitise and validate text destined for the TTS pipeline.

    Args:
        text: Raw text for speech synthesis.

    Returns:
        The sanitised text, guaranteed non-empty and at most 5 000 characters.

    Raises:
        ValueError: If the text is empty after sanitisation.
    """
    sanitized: str = sanitize_prompt(text, max_length=_TTS_MAX_LENGTH)

    if not sanitized:
        raise ValueError(
            "TTS text is empty after sanitisation.  "
            "Please provide text to convert to speech."
        )

    return sanitized


def detect_injection(text: str) -> bool:
    """Return ``True`` if *text* matches any known injection pattern.

    The check is case-insensitive and scans against every entry in
    :data:`INJECTION_PATTERNS`.

    Args:
        text: The string to inspect.

    Returns:
        ``True`` when at least one pattern matches; ``False`` otherwise.
    """
    return any(pattern.search(text) for pattern in INJECTION_PATTERNS)


# ---------------------------------------------------------------------------
# ADK before-tool callback
# ---------------------------------------------------------------------------


def before_tool_security_callback(
    callback_context: CallbackContext,
    tool_name: str,
    args: dict[str, Any],
) -> dict[str, Any] | None:
    """ADK ``before_tool_callback`` that gates tool execution on input safety.

    Behaviour per tool:

    * **generate_video** — validates ``args["prompt"]`` via
      :func:`validate_video_prompt`.
    * **generate_voiceover** — validates ``args["text"]`` via
      :func:`validate_tts_text`.

    For *every* tool call the callback also scans all string-valued arguments
    for prompt-injection patterns.  If an injection is detected the tool call
    is **blocked** by returning a dict with an ``"error"`` key (the ADK
    convention for aborting execution).

    Args:
        callback_context: The ADK callback context (not used directly but
            required by the callback signature).
        tool_name: Name of the tool about to execute.
        args: Keyword arguments that will be forwarded to the tool.

    Returns:
        ``None`` to allow execution, or a ``dict`` containing an ``"error"``
        key to block it.
    """
    # --- tool-specific validation ----------------------------------------
    try:
        if tool_name == "generate_video" and "prompt" in args:
            args["prompt"] = validate_video_prompt(args["prompt"])

        if tool_name == "generate_voiceover" and "text" in args:
            args["text"] = validate_tts_text(args["text"])

    except ValueError as exc:
        logger.warning(
            "Security callback blocked tool '%s': %s",
            tool_name,
            exc,
        )
        return {"error": str(exc)}

    # --- injection scan across ALL string args ---------------------------
    for key, value in args.items():
        if isinstance(value, str) and detect_injection(value):
            msg = (
                f"Prompt-injection pattern detected in argument '{key}' "
                f"for tool '{tool_name}'.  Execution blocked."
            )
            logger.warning(msg)
            return {"error": msg}

    # Allow execution
    return None
