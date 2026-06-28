# Copyright 2026 VibeCast Team
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     https://www.apache.org/licenses/LICENSE-2.0

"""Google Imagen client for thumbnail generation."""

from __future__ import annotations

import logging
import os
import tempfile
import uuid

logger = logging.getLogger(__name__)

DEFAULT_IMAGEN_MODEL = "imagen-4.0-generate-preview-06-06"


class ImagenClientError(Exception):
    """Raised when thumbnail generation fails."""


class ImagenClient:
    """Client for Google Imagen thumbnail generation."""

    def __init__(
        self,
        model: str | None = None,
        mock_mode: bool | None = None,
    ):
        self.model = model or DEFAULT_IMAGEN_MODEL
        self.mock_mode = mock_mode if mock_mode is not None else (
            os.environ.get("VIBECAST_MOCK_MODE", "true").lower() == "true"
        )

    async def generate_thumbnail(self, prompt: str) -> dict[str, str]:
        """Generate a thumbnail image and return status metadata."""
        if self.mock_mode:
            mock_id = uuid.uuid4().hex[:8]
            image_url = f"https://mock.vibecast.ai/thumbnails/{mock_id}.png"
            logger.info("Mock mode: generated thumbnail -> %s", image_url)
            return {
                "image_url": image_url,
                "prompt_used": prompt,
                "status": "success",
            }

        try:
            from google import genai
            from google.genai import types

            client = genai.Client()
            response = client.models.generate_images(
                model=self.model,
                prompt=prompt,
                config=types.GenerateImagesConfig(number_of_images=1),
            )
            image = response.generated_images[0].image

            with tempfile.NamedTemporaryFile(
                suffix=".png",
                delete=False,
            ) as tmp_file:
                image.save(tmp_file.name)
                image_path = tmp_file.name

            logger.info("Generated Imagen thumbnail saved to %s", image_path)
            return {
                "image_url": image_path,
                "prompt_used": prompt,
                "status": "success",
            }
        except Exception as exc:
            raise ImagenClientError(
                f"Thumbnail generation failed: {exc}"
            ) from exc
