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

"""Google GenAI (Gemini) Text-to-Speech client for voiceover generation.

This module uses the Gemini TTS model (gemini-2.5-flash-preview-tts)
to convert narration text into speech audio. It supports voice selection,
and includes a mock mode for development.

Security: Text inputs are expected to be pre-sanitized by the security
validators layer before reaching this client.
"""

import base64
import logging
import os
import uuid

logger = logging.getLogger(__name__)

# Default TTS model — Gemini Flash TTS
DEFAULT_TTS_MODEL = "gemini-2.5-flash-preview-tts"

# Available voices for Gemini TTS
AVAILABLE_VOICES = [
    "Aoede", "Charon", "Fenrir", "Kore", "Puck",
    "Leda", "Orus", "Zephyr",
]


class TTSClientError(Exception):
    """Raised when TTS generation fails."""


class GeminiTTSClient:
    """Client for Google GenAI text-to-speech via Gemini models.

    Attributes:
        voice: The prebuilt voice name to use for generation.
        model: The Gemini TTS model identifier.
        mock_mode: If True, returns simulated audio data.
    """

    def __init__(
        self,
        voice: str | None = None,
        model: str | None = None,
        mock_mode: bool | None = None,
    ):
        """Initialize the Gemini TTS client.

        Args:
            voice: Voice name (e.g., "Kore"). Falls back to
                VIBECAST_TTS_VOICE env var, then "Kore".
            model: TTS model name. Falls back to DEFAULT_TTS_MODEL.
            mock_mode: Enable mock mode. Falls back to
                VIBECAST_MOCK_MODE env var.
        """
        self.voice = voice or os.environ.get(
            "VIBECAST_TTS_VOICE", "Kore"
        )
        self.model = model or DEFAULT_TTS_MODEL
        self.mock_mode = mock_mode if mock_mode is not None else (
            os.environ.get("VIBECAST_MOCK_MODE", "true").lower()
            == "true"
        )

        if self.voice not in AVAILABLE_VOICES:
            logger.warning(
                "Voice '%s' not in known list %s. Using anyway.",
                self.voice,
                AVAILABLE_VOICES,
            )

    async def generate_voiceover(
        self,
        text: str,
        voice: str | None = None,
    ) -> dict:
        """Generate speech audio from text using Gemini TTS.

        Args:
            text: The narration text to convert to speech.
            voice: Override voice name for this call.

        Returns:
            dict with:
                - audio_data: base64-encoded audio bytes
                - mime_type: audio MIME type (e.g., audio/mp3)
                - audio_url: URL or path if saved to storage

        Raises:
            TTSClientError: If generation fails.
        """
        selected_voice = voice or self.voice

        if self.mock_mode:
            mock_id = uuid.uuid4().hex[:8]
            mock_url = (
                f"https://mock.vibecast.ai/audio/{mock_id}.mp3"
            )
            logger.info(
                "Mock mode: Generated voiceover (%d chars, "
                "voice=%s) -> %s",
                len(text),
                selected_voice,
                mock_url,
            )
            # Return a small mock audio placeholder
            mock_audio = base64.b64encode(
                b"MOCK_AUDIO_DATA_PLACEHOLDER"
            ).decode()
            return {
                "audio_data": mock_audio,
                "mime_type": "audio/mp3",
                "audio_url": mock_url,
            }

        try:
            # Import here to avoid hard dependency in mock mode
            from google import genai
            from google.genai import types

            client = genai.Client()

            response = client.models.generate_content(
                model=self.model,
                contents=text,
                config=types.GenerateContentConfig(
                    response_modalities=["AUDIO"],
                    speech_config=types.SpeechConfig(
                        voice_config=types.VoiceConfig(
                            prebuilt_voice_config=(
                                types.PrebuiltVoiceConfig(
                                    voice_name=selected_voice
                                )
                            )
                        )
                    ),
                ),
            )

            # Extract audio data from response
            audio_part = response.candidates[0].content.parts[0]
            audio_bytes = audio_part.inline_data.data
            mime_type = audio_part.inline_data.mime_type or "audio/mp3"

            audio_b64 = base64.b64encode(audio_bytes).decode()

            logger.info(
                "Generated voiceover: %d bytes, voice=%s",
                len(audio_bytes),
                selected_voice,
            )

            return {
                "audio_data": audio_b64,
                "mime_type": mime_type,
                "audio_url": "",  # Could save to GCS and return URL
            }

        except ImportError as e:
            raise TTSClientError(
                f"google-genai SDK not installed: {e}"
            ) from e
        except Exception as e:
            raise TTSClientError(
                f"TTS generation failed: {e}"
            ) from e

    async def generate_voiceover_batch(
        self,
        segments: list[dict],
    ) -> list[dict]:
        """Generate voiceovers for multiple narration segments.

        Args:
            segments: List of dicts with 'scene_number' and
                'narration_text' keys.

        Returns:
            List of dicts with scene_number, audio_data, and
            audio_url for each segment.
        """
        results = []
        for segment in segments:
            scene_num = segment.get("scene_number", 0)
            text = segment.get("narration_text", "")

            if not text.strip():
                logger.warning(
                    "Skipping empty narration for scene %d",
                    scene_num,
                )
                continue

            result = await self.generate_voiceover(text)
            result["scene_number"] = scene_num
            results.append(result)

        logger.info(
            "Generated %d voiceover clips from %d segments",
            len(results),
            len(segments),
        )
        return results
