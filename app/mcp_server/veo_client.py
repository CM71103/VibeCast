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

"""json2video client for programmatic video generation.

Uses Pexels stock video as cinematic backgrounds and json2video
to compose the final video with text overlays and TTS narration.
"""

from __future__ import annotations

import logging
import os
import re
import uuid

logger = logging.getLogger(__name__)

JSON2VIDEO_API_URL = "https://api.json2video.com/v2/movies"
PEXELS_API_URL = "https://api.pexels.com/videos/search"

# Curated fallback stock videos (royalty-free, publicly accessible)
FALLBACK_STOCK_VIDEOS = [
    "https://assets.json2video.com/assets/videos/earth-01.mp4",
]

# Number of stock clips to fetch per scene for dynamic B-roll cuts
STOCK_CLIPS_PER_SCENE = int(os.environ.get("VIBECAST_STOCK_CLIPS_PER_SCENE", "3"))


class VeoClientError(Exception):
    """Raised when video generation fails."""


def _extract_keywords(prompt: str) -> str:
    """Extract 2-3 meaningful search keywords from a visual prompt.

    Strips filler words and focuses on the subject matter so that
    Pexels returns relevant stock footage.
    """
    # Remove common cinematic/style filler words
    noise = {
        "cinematic", "visualization", "glowing", "dramatic", "dark",
        "transitioning", "showing", "depicting", "rendering", "scene",
        "footage", "video", "clip", "animation", "visual", "effect",
        "ultra", "realistic", "high", "quality", "stunning", "epic",
        "beautiful", "amazing", "incredible", "detailed", "abstract",
        "background", "overlay", "text", "on-screen", "bold",
    }
    # Keep only alphabetic words, lowercase
    words = re.findall(r"[a-zA-Z]+", prompt.lower())
    keywords = [w for w in words if w not in noise and len(w) > 2]
    # Take the first 3 meaningful keywords
    return " ".join(keywords[:3]) if keywords else "space universe"


def _extract_varied_keywords(prompt: str) -> list[str]:
    """Extract multiple keyword variations from a prompt for diverse stock footage.

    Returns up to 3 different keyword combinations so each Pexels search
    yields different stock clips for a more dynamic video.
    """
    noise = {
        "cinematic", "visualization", "glowing", "dramatic", "dark",
        "transitioning", "showing", "depicting", "rendering", "scene",
        "footage", "video", "clip", "animation", "visual", "effect",
        "ultra", "realistic", "high", "quality", "stunning", "epic",
        "beautiful", "amazing", "incredible", "detailed", "abstract",
        "background", "overlay", "text", "on-screen", "bold",
    }
    words = re.findall(r"[a-zA-Z]+", prompt.lower())
    keywords = [w for w in words if w not in noise and len(w) > 2]

    if len(keywords) < 2:
        return ["space universe", "technology future", "science abstract"]

    variations = []
    # Variation 1: first 2-3 keywords (main subject)
    variations.append(" ".join(keywords[:3]))
    # Variation 2: middle keywords (secondary angle)
    mid = len(keywords) // 2
    variations.append(" ".join(keywords[max(0, mid - 1):mid + 2]))
    # Variation 3: last keywords (tertiary angle)
    variations.append(" ".join(keywords[-3:] if len(keywords) >= 3 else keywords))

    # Deduplicate while preserving order
    seen = set()
    unique = []
    for v in variations:
        if v not in seen:
            seen.add(v)
            unique.append(v)

    return unique if unique else ["space universe"]


class VeoClient:
    """Client for video generation via json2video API.

    Drop-in replacement for the original Google Veo client.
    Uses Pexels stock footage as video backgrounds and json2video
    for compositing with text overlays and TTS narration.
    """

    def __init__(
        self,
        model: str | None = None,
        mock_mode: bool | None = None,
    ):
        self.api_key = os.environ.get("JSON2VIDEO_API_KEY", "")
        self.pexels_key = os.environ.get("PEXELS_API_KEY", "")
        self.mock_mode = mock_mode if mock_mode is not None else (
            os.environ.get("VIBECAST_MOCK_MODE", "true").lower() == "true"
        )

    async def _fetch_pexels_video(self, query: str, min_duration: int = 5) -> str:
        """Search Pexels for a stock video and return the HD mp4 URL.

        Args:
            query: Search keywords for Pexels.
            min_duration: Minimum video duration in seconds.

        Returns:
            Direct URL to an HD mp4 video file, or a fallback URL.
        """
        if not self.pexels_key:
            logger.warning("PEXELS_API_KEY not set — using fallback stock video")
            return FALLBACK_STOCK_VIDEOS[0]

        try:
            import aiohttp

            headers = {"Authorization": self.pexels_key}
            params = {"query": query, "per_page": 5, "orientation": "landscape"}

            async with aiohttp.ClientSession() as session:
                async with session.get(
                    PEXELS_API_URL, headers=headers, params=params
                ) as resp:
                    if resp.status != 200:
                        logger.warning(
                            "Pexels API returned %d — using fallback", resp.status
                        )
                        return FALLBACK_STOCK_VIDEOS[0]

                    data = await resp.json()
                    videos = data.get("videos", [])

                    for video in videos:
                        vid_duration = video.get("duration", 0)
                        if vid_duration < min_duration:
                            continue
                        # Find the HD file
                        for vf in video.get("video_files", []):
                            quality = vf.get("quality", "")
                            width = vf.get("width", 0)
                            link = vf.get("link", "")
                            if quality == "hd" and width >= 1280 and link:
                                logger.info(
                                    "Pexels stock video found: %s (query=%s)",
                                    link, query,
                                )
                                return link
                        # If no HD, take any file
                        files = video.get("video_files", [])
                        if files:
                            link = files[0].get("link", "")
                            if link:
                                return link

                    logger.warning(
                        "No Pexels results for '%s' — using fallback", query
                    )
                    return FALLBACK_STOCK_VIDEOS[0]

        except Exception as exc:
            logger.warning("Pexels fetch failed: %s — using fallback", exc)
            return FALLBACK_STOCK_VIDEOS[0]

    async def _fetch_multiple_pexels_videos(
        self, query: str, count: int = 3, min_duration: int = 3
    ) -> list[str]:
        """Search Pexels and return multiple unique stock video URLs.

        Uses varied keyword searches to get diverse footage. Falls back
        to fewer clips if not enough are found.

        Args:
            query: Base search keywords for Pexels.
            count: How many distinct clips to return.
            min_duration: Minimum video duration in seconds per clip.

        Returns:
            List of direct URLs to HD mp4 video files.
        """
        if not self.pexels_key:
            logger.warning("PEXELS_API_KEY not set — using fallback stock video")
            return [FALLBACK_STOCK_VIDEOS[0]]

        try:
            import aiohttp

            # Generate varied search queries for diverse results
            keyword_variations = _extract_varied_keywords(query)
            collected_urls: list[str] = []
            seen_ids: set[int] = set()

            async with aiohttp.ClientSession() as session:
                for search_query in keyword_variations:
                    if len(collected_urls) >= count:
                        break

                    headers = {"Authorization": self.pexels_key}
                    params = {
                        "query": search_query,
                        "per_page": 10,
                        "orientation": "landscape",
                    }

                    async with session.get(
                        PEXELS_API_URL, headers=headers, params=params
                    ) as resp:
                        if resp.status != 200:
                            logger.warning(
                                "Pexels API returned %d for '%s'",
                                resp.status, search_query,
                            )
                            continue

                        data = await resp.json()
                        videos = data.get("videos", [])

                        for video in videos:
                            if len(collected_urls) >= count:
                                break

                            vid_id = video.get("id", 0)
                            if vid_id in seen_ids:
                                continue  # Skip duplicates

                            vid_duration = video.get("duration", 0)
                            if vid_duration < min_duration:
                                continue

                            # Find the HD file
                            best_link = ""
                            for vf in video.get("video_files", []):
                                quality = vf.get("quality", "")
                                width = vf.get("width", 0)
                                link = vf.get("link", "")
                                if quality == "hd" and width >= 1280 and link:
                                    best_link = link
                                    break
                            # Fallback to any file
                            if not best_link:
                                files = video.get("video_files", [])
                                if files:
                                    best_link = files[0].get("link", "")

                            if best_link:
                                collected_urls.append(best_link)
                                seen_ids.add(vid_id)
                                logger.info(
                                    "Pexels clip %d/%d: %s (query='%s')",
                                    len(collected_urls), count,
                                    best_link, search_query,
                                )

            if not collected_urls:
                logger.warning("No Pexels results found — using fallback")
                return [FALLBACK_STOCK_VIDEOS[0]]

            logger.info(
                "Fetched %d unique Pexels stock clips for scene",
                len(collected_urls),
            )
            return collected_urls

        except Exception as exc:
            logger.warning("Multi-Pexels fetch failed: %s — using fallback", exc)
            return [FALLBACK_STOCK_VIDEOS[0]]

    async def generate_video(
        self,
        prompt: str,
        duration: int = 8,
        aspect_ratio: str = "16:9",
        narration: str = "",
    ) -> str:
        """Generate a video and return the download URL.

        Composes sequential background videos within a single json2video
        scene to prevent audio cut-offs. Caption text overlay displays the
        narration and is properly sized and positioned at the bottom.

        Args:
            prompt: Visual description / on-screen text for the scene.
            duration: Duration in seconds.
            aspect_ratio: Video aspect ratio ("16:9", "9:16", "1:1").
            narration: Optional narration text for TTS voiceover in the video.

        Returns:
            The URL of the rendered video.
        """
        if self.mock_mode:
            mock_id = uuid.uuid4().hex[:8]
            mock_url = f"https://mock.vibecast.ai/videos/{mock_id}.mp4"
            logger.info("Mock mode: generated video -> %s", mock_url)
            return mock_url

        try:
            import asyncio
            import aiohttp

            if not self.api_key:
                raise VeoClientError(
                    "JSON2VIDEO_API_KEY environment variable is not set."
                )

            # Map aspect ratio to json2video resolution format
            res = "full-hd"
            font_size = "28px"
            if aspect_ratio == "9:16":
                res = "instagram"
                font_size = "36px"
            elif aspect_ratio == "1:1":
                res = "square"
                font_size = "32px"

            # Step 1: Fetch multiple stock videos from Pexels for B-roll
            num_clips = min(STOCK_CLIPS_PER_SCENE, 5)  # Cap at 5
            stock_video_urls = await self._fetch_multiple_pexels_videos(
                prompt, count=num_clips, min_duration=3,
            )
            logger.info(
                "Using %d stock video clips for scene (keywords from: %s)",
                len(stock_video_urls), prompt[:60],
            )

            # Step 2: Build a single scene containing multiple video backgrounds
            # sequenced using "start" times. This prevents the voice elements
            # from getting truncated when scenes transition.
            clip_count = len(stock_video_urls)
            per_clip_duration = max(3, duration // clip_count)
            remaining = duration - (per_clip_duration * clip_count)

            elements = []
            current_start = 0.0

            for i, stock_url in enumerate(stock_video_urls):
                clip_dur = per_clip_duration + (remaining if i == 0 else 0)
                
                # Background video element
                elements.append({
                    "type": "video",
                    "src": stock_url,
                    "start": current_start,
                    "duration": clip_dur,
                    "muted": True,  # Mute original audio from stock
                })
                current_start += clip_dur

            # Subtitle Overlay text - use the narration script, fallback to prompt
            caption_text = narration if narration.strip() else prompt[:120]
            elements.append({
                "type": "text",
                "text": caption_text,
                "start": 0,
                "duration": duration,
                "style": "001",
                "settings": {
                    "font-family": "Montserrat",
                    "font-size": font_size,
                    "font-weight": "700",
                    "color": "#FFFFFF",
                    "text-align": "center",
                    "background-color": "rgba(0,0,0,0.75)",
                    "padding": "16px 24px",
                    "border-radius": "10px",
                    "width": "80%",
                },
                "position": "bottom-center",
            })

            # Add TTS narration voice element (plays from the start)
            if narration:
                elements.append({
                    "type": "voice",
                    "text": narration,
                    "start": 0,
                    "voice": "en-US-EmmaMultilingualNeural",
                })

            movie_payload = {
                "resolution": res,
                "quality": "high",
                "scenes": [
                    {
                        "duration": duration,
                        "elements": elements,
                    }
                ],
            }

            headers = {
                "x-api-key": self.api_key,
                "Content-Type": "application/json",
            }

            # Submit the movie creation request
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    JSON2VIDEO_API_URL,
                    json=movie_payload,
                    headers=headers,
                ) as resp:
                    if resp.status != 200:
                        error_text = await resp.text()
                        raise VeoClientError(
                            f"json2video API error ({resp.status}): {error_text}"
                        )
                    result = await resp.json()

                project_id = result.get("project")
                if not project_id:
                    raise VeoClientError(
                        f"json2video did not return a project ID: {result}"
                    )

                logger.info("json2video project created: %s", project_id)

                # Poll for completion (max ~5 minutes)
                status_url = f"{JSON2VIDEO_API_URL}?project={project_id}"
                for attempt in range(60):
                    await asyncio.sleep(5)
                    async with session.get(
                        status_url, headers={"x-api-key": self.api_key}
                    ) as status_resp:
                        if status_resp.status != 200:
                            continue
                        status_data = await status_resp.json()
                        movie_data = status_data.get("movie", {})
                        render_status = movie_data.get("status", "")

                        if render_status == "done":
                            video_url = movie_data.get("url", "")
                            if video_url:
                                logger.info(
                                    "json2video render complete: %s",
                                    video_url,
                                )
                                return video_url
                            raise VeoClientError(
                                "json2video render done but no URL returned."
                            )
                        elif render_status == "error":
                            error_msg = movie_data.get(
                                "message", "Unknown render error"
                            )
                            raise VeoClientError(
                                f"json2video render failed: {error_msg}"
                            )
                        # Still rendering — keep polling
                        logger.debug(
                            "json2video status: %s (attempt %d)",
                            render_status,
                            attempt + 1,
                        )

                raise VeoClientError(
                    "json2video render timed out after 5 minutes."
                )

        except VeoClientError:
            raise
        except Exception as exc:
            raise VeoClientError(
                f"Video generation failed: {exc}"
            ) from exc

    async def stitch_videos(self, video_urls: list[str], aspect_ratio: str = "16:9") -> str:
        """Stitch/concatenate multiple video URLs into a single video.

        Args:
            video_urls: List of video clip URLs.
            aspect_ratio: Output aspect ratio ("16:9", "9:16", "1:1").

        Returns:
            The URL of the rendered stitched video.
        """
        if self.mock_mode:
            mock_id = uuid.uuid4().hex[:8]
            mock_url = f"https://mock.vibecast.ai/videos/stitched_{mock_id}.mp4"
            logger.info("Mock mode: generated stitched video -> %s", mock_url)
            return mock_url

        try:
            import asyncio
            import aiohttp

            if not self.api_key:
                raise VeoClientError(
                    "JSON2VIDEO_API_KEY environment variable is not set."
                )

            # Filter out empty URLs
            valid_urls = [url for url in video_urls if url]
            if not valid_urls:
                raise VeoClientError("No valid video URLs to stitch.")

            if len(valid_urls) == 1:
                return valid_urls[0]

            scenes = []
            for url in valid_urls:
                scenes.append({
                    "elements": [
                        {
                            "type": "video",
                            "src": url,
                        }
                    ]
                })

            res = "full-hd"
            if aspect_ratio == "9:16":
                res = "instagram"
            elif aspect_ratio == "1:1":
                res = "square"

            movie_payload = {
                "resolution": res,
                "quality": "high",
                "scenes": scenes,
            }

            headers = {
                "x-api-key": self.api_key,
                "Content-Type": "application/json",
            }

            # Submit the movie creation request
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    JSON2VIDEO_API_URL,
                    json=movie_payload,
                    headers=headers,
                ) as resp:
                    if resp.status != 200:
                        error_text = await resp.text()
                        raise VeoClientError(
                            f"json2video API error ({resp.status}): {error_text}"
                        )
                    result = await resp.json()

                project_id = result.get("project")
                if not project_id:
                    raise VeoClientError(
                        f"json2video did not return a project ID: {result}"
                    )

                logger.info("json2video stitch project created: %s", project_id)

                # Poll for completion (max ~5 minutes)
                status_url = f"{JSON2VIDEO_API_URL}?project={project_id}"
                for attempt in range(60):
                    await asyncio.sleep(5)
                    async with session.get(
                        status_url, headers={"x-api-key": self.api_key}
                    ) as status_resp:
                        if status_resp.status != 200:
                            continue
                        status_data = await status_resp.json()
                        movie_data = status_data.get("movie", {})
                        render_status = movie_data.get("status", "")

                        if render_status == "done":
                            video_url = movie_data.get("url", "")
                            if video_url:
                                logger.info(
                                    "json2video stitch complete: %s",
                                    video_url,
                                )
                                return video_url
                            raise VeoClientError(
                                "json2video stitch done but no URL returned."
                            )
                        elif render_status == "error":
                            error_msg = movie_data.get(
                                "message", "Unknown render error"
                            )
                            raise VeoClientError(
                                f"json2video stitch failed: {error_msg}"
                            )
                        # Still rendering — keep polling
                        logger.debug(
                            "json2video status: %s (attempt %d)",
                            render_status,
                            attempt + 1,
                        )

                raise VeoClientError(
                    "json2video stitch timed out after 5 minutes."
                )

        except VeoClientError:
            raise
        except Exception as exc:
            raise VeoClientError(
                f"Video stitching failed: {exc}"
            ) from exc
