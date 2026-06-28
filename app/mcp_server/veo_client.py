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

"""Google GenAI Veo client for text-to-video generation."""

from __future__ import annotations

import logging
import os
import tempfile
import uuid

logger = logging.getLogger(__name__)

DEFAULT_VEO_MODEL = "veo-3.1-generate-preview"


class VeoClientError(Exception):
    """Raised when Veo generation fails."""


class VeoClient:
    """Client for Google Veo video generation."""

    def __init__(
        self,
        model: str | None = None,
        mock_mode: bool | None = None,
    ):
        self.model = model or DEFAULT_VEO_MODEL
        self.mock_mode = mock_mode if mock_mode is not None else (
            os.environ.get("VIBECAST_MOCK_MODE", "true").lower() == "true"
        )

    async def generate_video(
        self,
        prompt: str,
        duration: int = 8,
        aspect_ratio: str = "16:9",
    ) -> str:
        if self.mock_mode:
            mock_id = uuid.uuid4().hex[:8]
            mock_url = f"https://mock.vibecast.ai/videos/{mock_id}.mp4"
            logger.info("Mock mode: generated video -> %s", mock_url)
            return mock_url

        try:
            import asyncio

            from google import genai
            from google.genai import types

            client = genai.Client()
            operation = client.models.generate_videos(
                model=self.model,
                prompt=prompt,
                config=types.GenerateVideosConfig(
                    aspect_ratio=aspect_ratio,
                ),
            )

            while not operation.done:
                await asyncio.sleep(10)
                operation = client.operations.get(operation)

            generated_video = operation.response.generated_videos[0]
            with tempfile.NamedTemporaryFile(
                suffix=".mp4", delete=False
            ) as tmp_file:
                client.files.download(
                    file=generated_video.video,
                    destination=tmp_file.name,
                )
                saved_path = tmp_file.name

            logger.info("Generated Veo video saved to %s", saved_path)
            return saved_path
        except Exception as exc:
            raise VeoClientError(f"Video generation failed: {exc}") from exc
