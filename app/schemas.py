# Copyright 2026 VibeCast Contributors
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""Pydantic v2 schemas for the VibeCast video creation agent workflow.

Each model maps to a node in the 7-step pipeline:
    Intake → Research → Trend Analysis → Script → Storyboard → Asset Generation → Publishing

All fields carry ``Field(description=...)`` metadata so downstream tooling
(OpenAPI docs, LangGraph state inspection, etc.) can introspect the schema
without reading source code.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

# ---------------------------------------------------------------------------
# Node 1 — Intake
# ---------------------------------------------------------------------------


class IntakeResult(BaseModel):
    """Parsed and validated user request for a new video.

    Produced by the **Intake** node, which normalises free-form user input
    into a structured brief that every downstream node can rely on.
    """

    topic: str = Field(
        ...,
        description="The subject of the video (e.g. 'quantum computing basics').",
    )
    target_audience: str = Field(
        ...,
        description="Who the video is intended for (e.g. 'college students').",
    )
    video_length_seconds: int = Field(
        default=60,
        ge=5,
        le=3600,
        description="Target video duration in seconds.",
    )
    style: Literal["educational", "entertainment", "news", "tutorial", "documentary"] = Field(
        ...,
        description="Creative style that governs tone, pacing, and visuals.",
    )
    platform: Literal["youtube", "tiktok", "instagram", "general"] = Field(
        ...,
        description="Target distribution platform; affects aspect ratio and length limits.",
    )


# ---------------------------------------------------------------------------
# Node 2 — Research
# ---------------------------------------------------------------------------


class ResearchResult(BaseModel):
    """Curated research payload for the requested topic.

    Produced by the **Research** node, which gathers and verifies facts,
    identifies sources, and highlights currently-trending angles.
    """

    key_facts: list[str] = Field(
        default_factory=list,
        description="Verified factual statements about the topic.",
    )
    sources: list[str] = Field(
        default_factory=list,
        description="URLs or named references that back up the key facts.",
    )
    trending_points: list[str] = Field(
        default_factory=list,
        description="Aspects of the topic that are currently trending online.",
    )
    summary: str = Field(
        ...,
        description="A concise overview synthesising the research findings.",
    )


# ---------------------------------------------------------------------------
# Node 3 — Trend Analysis
# ---------------------------------------------------------------------------


class TrendAnalysis(BaseModel):
    """Market and trend intelligence for the video topic.

    Produced by the **Trend Analysis** node, which examines SEO signals,
    competitor content, and audience behaviour to shape the creative brief.
    """

    keywords: list[str] = Field(
        default_factory=list,
        description="SEO and trending keywords to weave into the script.",
    )
    popular_hooks: list[str] = Field(
        default_factory=list,
        description="Effective opening-hook styles observed in similar content.",
    )
    recommended_style: str = Field(
        ...,
        description="Suggested video style informed by current platform trends.",
    )
    competitor_angles: list[str] = Field(
        default_factory=list,
        description="Notable approaches competitors are using for this topic.",
    )
    estimated_engagement: Literal["high", "medium", "low"] = Field(
        ...,
        description="Predicted engagement level based on trend signals.",
    )


# ---------------------------------------------------------------------------
# Node 4 — Script (segment + full script)
# ---------------------------------------------------------------------------


class ScriptSegment(BaseModel):
    """A single timed segment inside a video script.

    Each segment pairs narration with a visual direction note, making it
    easy for downstream nodes to generate matching media assets.
    """

    segment_number: int = Field(
        ...,
        ge=1,
        description="1-based ordinal position of this segment in the script.",
    )
    narration: str = Field(
        ...,
        description="Voiceover / narration text for this segment.",
    )
    duration_seconds: int = Field(
        ...,
        ge=1,
        description="How long this segment should last on screen.",
    )
    visual_description: str = Field(
        ...,
        description="Direction for what the viewer should see during this segment.",
    )
    on_screen_text: str = Field(
        default="",
        description="Text overlays displayed on screen (lower-thirds, titles, etc.).",
    )


class Script(BaseModel):
    """Complete video script assembled from ordered segments.

    Produced by the **Script** node, which turns research and trend
    insights into a shootable script with a hook and call-to-action.
    """

    title: str = Field(
        ...,
        description="Working title for the video.",
    )
    hook: str = Field(
        ...,
        description="Attention-grabbing opening line or sequence.",
    )
    segments: list[ScriptSegment] = Field(
        default_factory=list,
        description="Ordered list of script segments.",
    )
    call_to_action: str = Field(
        ...,
        description="Closing CTA (subscribe, visit link, etc.).",
    )
    total_duration_seconds: int = Field(
        ...,
        ge=1,
        description="Sum of all segment durations, in seconds.",
    )


# ---------------------------------------------------------------------------
# Node 5 — Storyboard (scene + full board)
# ---------------------------------------------------------------------------


class StoryboardScene(BaseModel):
    """A single visual scene in the storyboard.

    Each scene carries a generative-AI prompt for video synthesis (e.g.
    Google Veo) and the matching narration text for TTS rendering.
    """

    scene_number: int = Field(
        ...,
        ge=1,
        description="1-based ordinal position of this scene.",
    )
    visual_prompt: str = Field(
        ...,
        description="Prompt sent to the video generation model (e.g. Google Veo).",
    )
    narration_text: str = Field(
        ...,
        description="Text fed to the TTS engine for the voiceover track.",
    )
    duration_seconds: int = Field(
        ...,
        ge=1,
        description="Target duration for this scene in seconds.",
    )
    transition: Literal["cut", "fade", "dissolve", "wipe", "zoom"] = Field(
        default="cut",
        description="Transition effect leading into the next scene.",
    )


class Storyboard(BaseModel):
    """Complete storyboard comprising all visual scenes.

    Produced by the **Storyboard** node, which translates the script into
    a scene-by-scene plan ready for media generation.
    """

    scenes: list[StoryboardScene] = Field(
        default_factory=list,
        description="Ordered list of storyboard scenes.",
    )
    total_duration_seconds: int = Field(
        ...,
        ge=1,
        description="Combined duration of all scenes, in seconds.",
    )


# ---------------------------------------------------------------------------
# Node 6 — Asset Generation
# ---------------------------------------------------------------------------


class GeneratedAssets(BaseModel):
    """Manifest of all media assets produced for the video.

    Produced by the **Asset Generation** node, which orchestrates Google Veo
    video synthesis, TTS voiceover rendering, and SRT subtitle creation.
    """

    video_clips: list[dict[str, object]] = Field(
        default_factory=list,
        description=(
            "Generated video clips. Each dict contains 'scene_number' (int), "
            "'video_url' (str), and 'status' (str)."
        ),
    )
    voiceover_clips: list[dict[str, object]] = Field(
        default_factory=list,
        description=(
            "Generated voiceover audio clips. Each dict contains "
            "'scene_number' (int), 'audio_url' (str), and 'status' (str)."
        ),
    )
    subtitle_srt: str = Field(
        default="",
        description="Full SRT-formatted subtitle content for the video.",
    )
    thumbnail: dict[str, object] = Field(
        default_factory=dict,
        description="Generated thumbnail image metadata.",
    )
    asset_manifest: dict[str, object] = Field(
        default_factory=dict,
        description="Summary manifest mapping asset types to counts and paths.",
    )


class ThumbnailResult(BaseModel):
    """Generated thumbnail image for the video."""

    image_url: str = Field(
        default="",
        description="Path or URL to the generated thumbnail image.",
    )
    prompt_used: str = Field(
        default="",
        description="Sanitised Imagen prompt used for thumbnail generation.",
    )
    status: Literal["success", "error"] = Field(
        ...,
        description="Thumbnail generation status.",
    )


class YouTubeUploadResult(BaseModel):
    """Result of auto-uploading to YouTube."""

    video_id: str = Field(
        default="",
        description="YouTube video ID when an upload succeeds.",
    )
    video_url: str = Field(
        default="",
        description="Full YouTube URL when an upload succeeds.",
    )
    status: Literal["success", "error", "skipped"] = Field(
        ...,
        description="Upload status.",
    )
    privacy_status: Literal["private", "unlisted", "public"] = Field(
        default="private",
        description="YouTube privacy setting used for upload.",
    )
    message: str = Field(
        default="",
        description="Human-readable upload status message.",
    )


# ---------------------------------------------------------------------------
# Node 7 — Publishing
# ---------------------------------------------------------------------------


class PublishingSuggestions(BaseModel):
    """Publishing metadata and social-media copy for the finished video.

    Produced by the **Publishing** node, which generates platform-optimised
    titles, descriptions, tags, and cross-posting content.
    """

    title: str = Field(
        ...,
        description="SEO-optimised video title for the target platform.",
    )
    description: str = Field(
        ...,
        description="Video description with keywords, timestamps, and links.",
    )
    tags: list[str] = Field(
        default_factory=list,
        description="Discoverable tags / keywords for the video.",
    )
    thumbnail_concept: str = Field(
        ...,
        description="Creative direction for the thumbnail image.",
    )
    best_upload_time: str = Field(
        ...,
        description="Recommended upload window (e.g. 'Tuesday 14:00 UTC').",
    )
    social_media_posts: dict[str, str] = Field(
        default_factory=dict,
        description="Platform-keyed map of ready-to-post social copy (e.g. {'twitter': '...'}).",
    )
    hashtags: list[str] = Field(
        default_factory=list,
        description="Hashtags for cross-platform discoverability.",
    )
