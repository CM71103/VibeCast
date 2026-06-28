# Copyright 2026 VibeCast Team
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     https://www.apache.org/licenses/LICENSE-2.0

"""YouTube Data API client for private video publishing."""

from __future__ import annotations

import logging
import os
import uuid
from pathlib import Path

logger = logging.getLogger(__name__)

YOUTUBE_UPLOAD_SCOPE = ["https://www.googleapis.com/auth/youtube.upload"]


class YouTubeClientError(Exception):
    """Raised when YouTube upload fails."""


class YouTubeClient:
    """Upload generated videos to YouTube, defaulting to private visibility."""

    def __init__(
        self,
        client_secret_path: str | None = None,
        enabled: bool | None = None,
        mock_mode: bool | None = None,
    ):
        self.client_secret_path = client_secret_path or os.environ.get(
            "YOUTUBE_CLIENT_SECRET_PATH",
            "",
        )
        self.enabled = enabled if enabled is not None else (
            os.environ.get("YOUTUBE_ENABLED", "false").lower() == "true"
        )
        self.mock_mode = mock_mode if mock_mode is not None else (
            os.environ.get("VIBECAST_MOCK_MODE", "true").lower() == "true"
        )

    async def upload(
        self,
        video_path: str,
        title: str,
        description: str,
        tags: list[str],
        thumbnail_path: str = "",
        privacy_status: str = "private",
    ) -> dict[str, str]:
        """Upload a video to YouTube or return a deterministic mock result."""
        if self.mock_mode:
            video_id = f"mock-{uuid.uuid4().hex[:8]}"
            return {
                "video_id": video_id,
                "video_url": f"https://youtu.be/{video_id}",
                "status": "success",
                "privacy_status": privacy_status,
                "message": "Mock YouTube upload completed.",
            }

        if not self.enabled:
            return {
                "video_id": "",
                "video_url": "",
                "status": "skipped",
                "privacy_status": privacy_status,
                "message": "YouTube upload skipped because YOUTUBE_ENABLED=false.",
            }

        if not self.client_secret_path:
            raise YouTubeClientError("YOUTUBE_CLIENT_SECRET_PATH is not set.")

        if not Path(video_path).exists():
            raise YouTubeClientError(f"Video file not found: {video_path}")

        try:
            from google_auth_oauthlib.flow import InstalledAppFlow
            from googleapiclient.discovery import build
            from googleapiclient.http import MediaFileUpload

            flow = InstalledAppFlow.from_client_secrets_file(
                self.client_secret_path,
                scopes=YOUTUBE_UPLOAD_SCOPE,
            )
            credentials = flow.run_local_server(port=0)
            youtube = build("youtube", "v3", credentials=credentials)

            body = {
                "snippet": {
                    "title": title,
                    "description": description,
                    "tags": tags,
                    "categoryId": "22",
                },
                "status": {"privacyStatus": privacy_status},
            }

            request = youtube.videos().insert(
                part="snippet,status",
                body=body,
                media_body=MediaFileUpload(video_path, resumable=True),
            )
            response = request.execute()
            video_id = response["id"]

            if thumbnail_path and Path(thumbnail_path).exists():
                youtube.thumbnails().set(
                    videoId=video_id,
                    media_body=MediaFileUpload(thumbnail_path),
                ).execute()

            return {
                "video_id": video_id,
                "video_url": f"https://youtu.be/{video_id}",
                "status": "success",
                "privacy_status": privacy_status,
                "message": "YouTube upload completed.",
            }
        except Exception as exc:
            raise YouTubeClientError(f"YouTube upload failed: {exc}") from exc
