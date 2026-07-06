# Copyright 2026 VibeCast Team
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     https://www.apache.org/licenses/LICENSE-2.0

"""Google Imagen client for thumbnail generation.

Falls back to Pexels stock images when Imagen is unavailable
(e.g., free-tier API keys that don't support image generation).
"""

from __future__ import annotations

import logging
import os
import re
import tempfile
import uuid

logger = logging.getLogger(__name__)

DEFAULT_IMAGEN_MODEL = "imagen-4.0-generate-001"
PEXELS_IMAGES_API_URL = "https://api.pexels.com/v1/search"


class ImagenClientError(Exception):
    """Raised when thumbnail generation fails."""


def _extract_thumbnail_keywords(prompt: str) -> str:
    """Extract 2-3 search keywords from a thumbnail prompt."""
    noise = {
        "youtube", "thumbnail", "bold", "high", "contrast", "cinematic",
        "readable", "small", "size", "text", "no", "for", "the", "and",
        "with", "vibrant", "dynamic", "engaging", "modern", "sleek",
        "design", "style", "eye", "catching", "click", "bait",
    }
    words = re.findall(r"[a-zA-Z]+", prompt.lower())
    keywords = [w for w in words if w not in noise and len(w) > 2]
    return " ".join(keywords[:3]) if keywords else "space universe"


class ImagenClient:
    """Client for Google Imagen thumbnail generation.

    Falls back to Pexels stock images when the Gemini API key
    doesn't support Imagen (free-tier limitation).
    """

    def __init__(
        self,
        model: str | None = None,
        mock_mode: bool | None = None,
    ):
        self.model = model or DEFAULT_IMAGEN_MODEL
        self.pexels_key = os.environ.get("PEXELS_API_KEY", "")
        self.mock_mode = mock_mode if mock_mode is not None else (
            os.environ.get("VIBECAST_MOCK_MODE", "true").lower() == "true"
        )

    async def _fetch_pexels_image(self, query: str) -> str:
        """Search Pexels for a landscape image and return the URL."""
        if not self.pexels_key:
            logger.warning("PEXELS_API_KEY not set — cannot fetch fallback image")
            return ""

        try:
            import aiohttp

            headers = {"Authorization": self.pexels_key}
            params = {
                "query": query,
                "per_page": 3,
                "orientation": "landscape",
                "size": "large",
            }

            async with aiohttp.ClientSession() as session:
                async with session.get(
                    PEXELS_IMAGES_API_URL, headers=headers, params=params
                ) as resp:
                    if resp.status != 200:
                        logger.warning("Pexels images API returned %d", resp.status)
                        return ""

                    data = await resp.json()
                    photos = data.get("photos", [])

                    if photos:
                        # Use the 'large2x' size for high-quality thumbnails
                        src = photos[0].get("src", {})
                        image_url = (
                            src.get("large2x")
                            or src.get("large")
                            or src.get("original", "")
                        )
                        if image_url:
                            logger.info(
                                "Pexels fallback image found: %s (query=%s)",
                                image_url, query,
                            )
                            return image_url

                    logger.warning("No Pexels images for '%s'", query)
                    return ""

        except Exception as exc:
            logger.warning("Pexels image fetch failed: %s", exc)
            return ""

    async def generate_thumbnail(self, prompt: str) -> dict[str, str]:
        """Generate a thumbnail image and return status metadata.

        Tries Google Imagen first, then falls back to Pexels stock images.
        """
        if self.mock_mode:
            mock_id = uuid.uuid4().hex[:8]
            image_url = f"https://mock.vibecast.ai/thumbnails/{mock_id}.png"
            logger.info("Mock mode: generated thumbnail -> %s", image_url)
            return {
                "image_url": image_url,
                "prompt_used": prompt,
                "status": "success",
            }

        # Try Google Imagen first
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
        except Exception as imagen_exc:
            logger.warning(
                "Imagen failed (likely free-tier): %s — trying Pexels fallback",
                imagen_exc,
            )

        # Fallback: Pexels stock image
        keywords = _extract_thumbnail_keywords(prompt)
        pexels_url = await self._fetch_pexels_image(keywords)

        if pexels_url:
            logger.info("Using Pexels fallback thumbnail: %s", pexels_url)
            return {
                "image_url": pexels_url,
                "prompt_used": prompt,
                "status": "success",
                "source": "pexels_fallback",
            }

        raise ImagenClientError(
            f"Thumbnail generation failed: Imagen unavailable and "
            f"Pexels fallback returned no results for '{keywords}'."
        )
