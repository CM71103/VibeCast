# Copyright 2026 VibeCast Team
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

"""FastMCP Media Tools Server for VibeCast.

This MCP server exposes three tools for media asset generation:
  - generate_video: Creates video clips via Kling AI
  - generate_voiceover: Generates speech audio via Gemini TTS
  - generate_subtitles: Creates SRT-formatted subtitle files

The server acts as the secure bridge between the ADK agent workflow
and external media generation APIs (Day 2 whitepaper: MCP as the
interoperability layer, bypassing the NxM integration problem).

Security (Day 4 whitepaper, Pillar 4): All tool inputs are sanitized
before reaching external APIs. The MCP server is the ONLY path to
external services — agents cannot make raw HTTP calls.
"""

import logging

from fastmcp import FastMCP

from app.mcp_server.kling_client import KlingClient
from app.mcp_server.tts_client import GeminiTTSClient
from app.security.validators import (
    validate_tts_text,
    validate_video_prompt,
)

logger = logging.getLogger(__name__)

# Initialize the FastMCP server
mcp_server = FastMCP(
    name="vibecast-media-tools",
    instructions=(
        "Media generation tools for the VibeCast video "
        "creation pipeline. Use generate_video for visual "
        "clips, generate_voiceover for narration audio, and "
        "generate_subtitles for SRT subtitle files."
    ),
)

# Shared client instances (initialized on first tool call)
_kling_client: KlingClient | None = None
_tts_client: GeminiTTSClient | None = None


def _get_kling_client() -> KlingClient:
    """Lazy-initialize the Kling AI client."""
    global _kling_client
    if _kling_client is None:
        _kling_client = KlingClient()
    return _kling_client


def _get_tts_client() -> GeminiTTSClient:
    """Lazy-initialize the Gemini TTS client."""
    global _tts_client
    if _tts_client is None:
        _tts_client = GeminiTTSClient()
    return _tts_client


@mcp_server.tool()
async def generate_video(
    prompt: str,
    duration: int = 5,
    aspect_ratio: str = "16:9",
) -> dict:
    """Generate a video clip from a visual description using Kling AI.

    Args:
        prompt: A detailed visual description of the scene to
            generate. Maximum 2500 characters. Should describe
            the scene, camera movement, lighting, and style.
        duration: Video duration in seconds (5 or 10).
        aspect_ratio: Output aspect ratio. Options: 16:9, 9:16, 1:1.

    Returns:
        dict with 'status', 'video_url', and 'task_id' keys.
    """
    try:
        # Security: sanitize and validate prompt before API call
        clean_prompt = validate_video_prompt(prompt)

        client = _get_kling_client()
        video_url = await client.generate_video(
            prompt=clean_prompt,
            duration=duration,
            aspect_ratio=aspect_ratio,
        )

        logger.info("Video generated: %s", video_url)
        return {
            "status": "success",
            "video_url": video_url,
            "prompt_used": clean_prompt[:100] + "...",
        }

    except ValueError as e:
        logger.warning("Prompt validation failed: %s", e)
        return {"status": "error", "error": str(e)}
    except Exception as e:
        logger.error("Video generation failed: %s", e)
        return {"status": "error", "error": str(e)}


@mcp_server.tool()
async def generate_voiceover(
    text: str,
    voice: str = "Kore",
) -> dict:
    """Generate speech audio from narration text using Gemini TTS.

    Args:
        text: The narration text to convert to speech. Maximum
            5000 characters. Use natural language with punctuation
            for best results.
        voice: The voice to use. Options: Aoede, Charon, Fenrir,
            Kore, Puck, Leda, Orus, Zephyr.

    Returns:
        dict with 'status', 'audio_url', and 'mime_type' keys.
    """
    try:
        # Security: sanitize and validate text before TTS call
        clean_text = validate_tts_text(text)

        client = _get_tts_client()
        result = await client.generate_voiceover(
            text=clean_text,
            voice=voice,
        )

        logger.info(
            "Voiceover generated: %s (%d chars)",
            result.get("audio_url", "inline"),
            len(clean_text),
        )
        return {
            "status": "success",
            "audio_url": result["audio_url"],
            "audio_data": result["audio_data"],
            "mime_type": result["mime_type"],
        }

    except ValueError as e:
        logger.warning("Text validation failed: %s", e)
        return {"status": "error", "error": str(e)}
    except Exception as e:
        logger.error("Voiceover generation failed: %s", e)
        return {"status": "error", "error": str(e)}


@mcp_server.tool()
async def generate_subtitles(
    segments: list[dict],
) -> dict:
    """Generate SRT-formatted subtitles from script segments.

    Args:
        segments: List of segment dicts, each containing:
            - segment_number (int): Sequential segment index
            - narration (str): The narration text for this segment
            - duration_seconds (int): Duration of this segment

    Returns:
        dict with 'status' and 'srt_content' keys. The srt_content
        is a complete SRT subtitle file as a string.
    """
    try:
        if not segments:
            return {
                "status": "error",
                "error": "No segments provided",
            }

        srt_lines = []
        current_time = 0.0

        for seg in segments:
            seg_num = seg.get("segment_number", 0)
            narration = seg.get("narration", "")
            duration = seg.get("duration_seconds", 5)

            if not narration.strip():
                current_time += duration
                continue

            # Calculate SRT timestamps
            start_time = current_time
            end_time = current_time + duration

            start_str = _format_srt_time(start_time)
            end_str = _format_srt_time(end_time)

            # Build SRT entry
            srt_lines.append(str(seg_num))
            srt_lines.append(f"{start_str} --> {end_str}")
            srt_lines.append(narration.strip())
            srt_lines.append("")  # Blank line separator

            current_time = end_time

        srt_content = "\n".join(srt_lines)

        logger.info(
            "Generated subtitles: %d segments, %.1f seconds",
            len(segments),
            current_time,
        )

        return {
            "status": "success",
            "srt_content": srt_content,
            "total_duration_seconds": current_time,
        }

    except Exception as e:
        logger.error("Subtitle generation failed: %s", e)
        return {"status": "error", "error": str(e)}


def _format_srt_time(seconds: float) -> str:
    """Convert seconds to SRT timestamp format (HH:MM:SS,mmm).

    Args:
        seconds: Time in seconds.

    Returns:
        Formatted SRT timestamp string.
    """
    hours = int(seconds // 3600)
    minutes = int((seconds % 3600) // 60)
    secs = int(seconds % 60)
    millis = int((seconds % 1) * 1000)
    return f"{hours:02d}:{minutes:02d}:{secs:02d},{millis:03d}"


# Entry point for running the MCP server standalone
if __name__ == "__main__":
    mcp_server.run()
