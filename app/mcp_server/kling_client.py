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

"""Kling AI async REST client for text-to-video generation.

This module provides an async HTTP client that communicates with the
Kling AI API (https://api-singapore.klingai.com) to generate video
clips from text prompts. It supports both real API calls and a mock
mode for development/demo purposes.

Security: All prompts are validated before submission. API keys are
loaded from environment variables only — never hardcoded.
"""

import asyncio
import logging
import os
import uuid
from typing import Any

import httpx

logger = logging.getLogger(__name__)

# Kling AI API base URL
KLING_API_BASE = "https://api-singapore.klingai.com"

# Maximum poll attempts before timeout (each attempt waits ~5 seconds)
MAX_POLL_ATTEMPTS = 60


class KlingClientError(Exception):
    """Raised when a Kling AI API call fails."""


class KlingClient:
    """Async client for the Kling AI video generation API.

    Attributes:
        api_key: The Kling AI API key for authentication.
        mock_mode: If True, returns simulated responses without API calls.
        base_url: The Kling AI API base URL.
    """

    def __init__(
        self,
        api_key: str | None = None,
        mock_mode: bool | None = None,
    ):
        """Initialize the Kling AI client.

        Args:
            api_key: Kling API key. Falls back to KLING_API_KEY env var.
            mock_mode: Enable mock mode. Falls back to VIBECAST_MOCK_MODE env var.
        """
        self.api_key = api_key or os.environ.get("KLING_API_KEY", "")
        self.mock_mode = mock_mode if mock_mode is not None else (
            os.environ.get("VIBECAST_MOCK_MODE", "true").lower() == "true"
        )
        self.base_url = KLING_API_BASE

        if not self.mock_mode and not self.api_key:
            raise KlingClientError(
                "KLING_API_KEY is required when mock mode is disabled. "
                "Set VIBECAST_MOCK_MODE=true for demo/development."
            )

    def _get_headers(self) -> dict[str, str]:
        """Build authorization headers for Kling API requests."""
        return {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

    async def submit_video_task(
        self,
        prompt: str,
        model: str = "kling-v3",
        duration: int = 5,
        aspect_ratio: str = "16:9",
    ) -> str:
        """Submit a text-to-video generation task to Kling AI.

        Args:
            prompt: Visual description for the video (max 2500 chars).
            model: Kling model version (kling-v3, kling-v3-turbo).
            duration: Video duration in seconds (5 or 10).
            aspect_ratio: Output aspect ratio (16:9, 9:16, 1:1).

        Returns:
            task_id: The ID of the submitted generation task.

        Raises:
            KlingClientError: If the API returns an error response.
        """
        if self.mock_mode:
            mock_id = f"mock-task-{uuid.uuid4().hex[:8]}"
            logger.info("Mock mode: Simulated video task %s", mock_id)
            return mock_id

        payload = {
            "model_name": model,
            "prompt": prompt,
            "duration": str(duration),
            "aspect_ratio": aspect_ratio,
        }

        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(
                f"{self.base_url}/v1/videos/text2video",
                json=payload,
                headers=self._get_headers(),
            )

            if response.status_code != 200:
                raise KlingClientError(
                    f"Kling API error {response.status_code}: {response.text}"
                )

            data = response.json()
            task_id = data.get("data", {}).get("task_id")
            if not task_id:
                raise KlingClientError(
                    f"No task_id in Kling response: {data}"
                )

            logger.info("Submitted Kling video task: %s", task_id)
            return task_id

    async def poll_task_status(
        self, task_id: str
    ) -> dict[str, Any]:
        """Poll a Kling AI task until completion or failure.

        Args:
            task_id: The task ID returned by submit_video_task.

        Returns:
            dict with 'status' and 'video_url' keys.

        Raises:
            KlingClientError: If polling times out or task fails.
        """
        if self.mock_mode:
            # Simulate a brief processing delay
            await asyncio.sleep(1)
            mock_url = (
                f"https://mock.kling.ai/videos/{task_id}.mp4"
            )
            logger.info("Mock mode: Video ready at %s", mock_url)
            return {"status": "completed", "video_url": mock_url}

        async with httpx.AsyncClient(timeout=30.0) as client:
            for attempt in range(MAX_POLL_ATTEMPTS):
                response = await client.get(
                    f"{self.base_url}/v1/videos/text2video/{task_id}",
                    headers=self._get_headers(),
                )

                if response.status_code != 200:
                    raise KlingClientError(
                        f"Poll error {response.status_code}: "
                        f"{response.text}"
                    )

                data = response.json()
                task_data = data.get("data", {})
                status = task_data.get("task_status", "unknown")

                if status == "succeed":
                    videos = task_data.get("task_result", {}).get(
                        "videos", []
                    )
                    video_url = (
                        videos[0].get("url", "") if videos else ""
                    )
                    logger.info(
                        "Kling task %s completed: %s",
                        task_id,
                        video_url,
                    )
                    return {
                        "status": "completed",
                        "video_url": video_url,
                    }
                elif status == "failed":
                    raise KlingClientError(
                        f"Kling task {task_id} failed: "
                        f"{task_data.get('task_status_msg', 'Unknown')}"
                    )

                # Still processing — wait before next poll
                logger.debug(
                    "Task %s status: %s (attempt %d/%d)",
                    task_id,
                    status,
                    attempt + 1,
                    MAX_POLL_ATTEMPTS,
                )
                await asyncio.sleep(5)

        raise KlingClientError(
            f"Task {task_id} timed out after {MAX_POLL_ATTEMPTS} "
            f"poll attempts"
        )

    async def generate_video(
        self,
        prompt: str,
        model: str = "kling-v3",
        duration: int = 5,
        aspect_ratio: str = "16:9",
    ) -> str:
        """High-level method: submit task and wait for video URL.

        Args:
            prompt: Visual description for the video.
            model: Kling model version.
            duration: Video duration in seconds.
            aspect_ratio: Output aspect ratio.

        Returns:
            video_url: URL to the generated video file.
        """
        task_id = await self.submit_video_task(
            prompt=prompt,
            model=model,
            duration=duration,
            aspect_ratio=aspect_ratio,
        )
        result = await self.poll_task_status(task_id)
        return result["video_url"]
