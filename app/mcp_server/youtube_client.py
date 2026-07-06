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
import tempfile
import uuid
from pathlib import Path

logger = logging.getLogger(__name__)

YOUTUBE_UPLOAD_SCOPE = ["https://www.googleapis.com/auth/youtube.upload"]


class YouTubeClientError(Exception):
    """Raised when YouTube upload fails."""


async def _download_remote_file(url: str, suffix: str = ".mp4") -> str:
    """Download a remote URL to a local temp file and return the path.

    Args:
        url: The remote HTTP/HTTPS URL to download.
        suffix: File extension for the temp file.

    Returns:
        Absolute path to the downloaded temp file.

    Raises:
        YouTubeClientError: If download fails.
    """
    try:
        import aiohttp

        temp_dir = tempfile.gettempdir()
        temp_filename = f"vibecast_{uuid.uuid4().hex[:8]}{suffix}"
        temp_path = os.path.join(temp_dir, temp_filename)

        logger.info("Downloading remote file: %s -> %s", url, temp_path)

        async with aiohttp.ClientSession() as session:
            async with session.get(url) as resp:
                if resp.status != 200:
                    raise YouTubeClientError(
                        f"Failed to download {url}: HTTP {resp.status}"
                    )
                with open(temp_path, "wb") as f:
                    async for chunk in resp.content.iter_chunked(8192):
                        f.write(chunk)

        file_size = os.path.getsize(temp_path)
        logger.info(
            "Downloaded %s (%.1f MB) to %s",
            url, file_size / (1024 * 1024), temp_path,
        )
        return temp_path

    except YouTubeClientError:
        raise
    except Exception as exc:
        raise YouTubeClientError(
            f"Failed to download remote file {url}: {exc}"
        ) from exc


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

        # Track temp files for cleanup
        temp_files: list[str] = []

        try:
            # --- Download remote video URL to local temp file ---
            local_video_path = video_path
            if video_path.startswith(("http://", "https://")):
                local_video_path = await _download_remote_file(
                    video_path, suffix=".mp4"
                )
                temp_files.append(local_video_path)

            if not Path(local_video_path).exists():
                raise YouTubeClientError(
                    f"Video file not found: {local_video_path}"
                )

            # --- Download remote thumbnail URL to local temp file ---
            local_thumbnail_path = thumbnail_path
            if thumbnail_path and thumbnail_path.startswith(
                ("http://", "https://")
            ):
                local_thumbnail_path = await _download_remote_file(
                    thumbnail_path, suffix=".png"
                )
                temp_files.append(local_thumbnail_path)

            import asyncio
            import json as json_module
            from google_auth_oauthlib.flow import InstalledAppFlow
            from google.oauth2.credentials import Credentials
            from googleapiclient.discovery import build
            from googleapiclient.http import MediaFileUpload

            # --- Token caching: avoid re-auth on every upload ---
            token_path = Path(self.client_secret_path).parent / "vibecast_youtube_token.json"
            credentials = None

            # Try loading cached token
            if token_path.exists():
                try:
                    credentials = Credentials.from_authorized_user_file(
                        str(token_path), YOUTUBE_UPLOAD_SCOPE
                    )
                    logger.info("Loaded cached YouTube OAuth token from %s", token_path)
                except Exception as e:
                    logger.warning("Failed to load cached token: %s", e)
                    credentials = None

            # Refresh if expired
            if credentials and credentials.expired and credentials.refresh_token:
                try:
                    from google.auth.transport.requests import Request
                    await asyncio.to_thread(credentials.refresh, Request())
                    logger.info("Refreshed expired YouTube OAuth token")
                except Exception as e:
                    logger.warning("Token refresh failed, re-authorizing: %s", e)
                    credentials = None

            # If no valid credentials, run the full OAuth flow
            if not credentials or not credentials.valid:
                flow = InstalledAppFlow.from_client_secrets_file(
                    self.client_secret_path,
                    scopes=YOUTUBE_UPLOAD_SCOPE,
                )
                logger.info(
                    "Starting YouTube OAuth flow — a browser window will open. "
                    "Please sign in and authorize VibeCast."
                )
                # Run in thread to avoid blocking the async event loop
                credentials = await asyncio.to_thread(
                    flow.run_local_server, port=0, open_browser=True
                )

                # Cache the token for next time
                try:
                    token_path.write_text(credentials.to_json())
                    logger.info("Saved YouTube OAuth token to %s", token_path)
                except Exception as e:
                    logger.warning("Failed to save token cache: %s", e)

            youtube = await asyncio.to_thread(
                build, "youtube", "v3", credentials=credentials
            )

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
                media_body=MediaFileUpload(local_video_path, resumable=True),
            )
            # Run the upload in a thread — it's a synchronous HTTP call
            response = await asyncio.to_thread(request.execute)
            video_id = response["id"]
            logger.info("YouTube video uploaded: %s", video_id)

            if local_thumbnail_path and Path(local_thumbnail_path).exists():
                thumb_req = youtube.thumbnails().set(
                    videoId=video_id,
                    media_body=MediaFileUpload(local_thumbnail_path),
                )
                await asyncio.to_thread(thumb_req.execute)

            return {
                "video_id": video_id,
                "video_url": f"https://youtu.be/{video_id}",
                "status": "success",
                "privacy_status": privacy_status,
                "message": "YouTube upload completed.",
            }
        except YouTubeClientError:
            raise
        except Exception as exc:
            raise YouTubeClientError(f"YouTube upload failed: {exc}") from exc
        finally:
            # Clean up temp files
            for temp_file in temp_files:
                try:
                    if os.path.exists(temp_file):
                        os.remove(temp_file)
                        logger.info("Cleaned up temp file: %s", temp_file)
                except OSError as e:
                    logger.warning(
                        "Failed to clean up temp file %s: %s", temp_file, e
                    )
