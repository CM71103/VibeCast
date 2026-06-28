# Copyright 2026 VibeCast Team
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     https://www.apache.org/licenses/LICENSE-2.0

"""Unit tests for VibeCast Pydantic schemas."""

import pytest
from pydantic import ValidationError

from app.schemas import (
    GeneratedAssets,
    IntakeResult,
    PublishingSuggestions,
    ResearchResult,
    Script,
    ScriptSegment,
    Storyboard,
    StoryboardScene,
    ThumbnailResult,
    YouTubeUploadResult,
)


class TestIntakeResult:
    """Tests for the IntakeResult schema."""

    def test_valid_intake(self):
        result = IntakeResult(
            topic="Quantum Computing Basics",
            target_audience="Tech enthusiasts aged 18-35",
            video_length_seconds=90,
            style="educational",
            platform="youtube",
        )
        assert result.topic == "Quantum Computing Basics"
        assert result.video_length_seconds == 90

    def test_invalid_style_rejected(self):
        with pytest.raises(ValidationError):
            IntakeResult(
                topic="Test",
                target_audience="Everyone",
                video_length_seconds=60,
                style="invalid_style",
                platform="youtube",
            )

    def test_invalid_platform_rejected(self):
        with pytest.raises(ValidationError):
            IntakeResult(
                topic="Test",
                target_audience="Everyone",
                video_length_seconds=60,
                style="news",
                platform="myspace",
            )


class TestResearchResult:
    """Tests for the ResearchResult schema."""

    def test_valid_research(self):
        result = ResearchResult(
            key_facts=["Fact 1", "Fact 2", "Fact 3"],
            sources=["https://example.com"],
            trending_points=["AI adoption is accelerating"],
            summary="A brief summary of the research.",
        )
        assert len(result.key_facts) == 3
        assert result.summary != ""


class TestScript:
    """Tests for the Script schema."""

    def test_valid_script_with_segments(self):
        segments = [
            ScriptSegment(
                segment_number=1,
                narration="Welcome to our video!",
                duration_seconds=5,
                visual_description="Opening title card with animation",
                on_screen_text="VibeCast Presents",
            ),
            ScriptSegment(
                segment_number=2,
                narration="Today we explore quantum computing.",
                duration_seconds=10,
                visual_description="Animated quantum circuits",
                on_screen_text="Quantum Computing 101",
            ),
        ]
        script = Script(
            title="Quantum Computing Explained",
            hook="What if computers could solve the unsolvable?",
            segments=segments,
            call_to_action="Subscribe for more tech explainers!",
            total_duration_seconds=15,
        )
        assert len(script.segments) == 2
        assert script.title == "Quantum Computing Explained"


class TestStoryboard:
    """Tests for the Storyboard schema."""

    def test_valid_storyboard(self):
        scenes = [
            StoryboardScene(
                scene_number=1,
                visual_prompt="Cinematic wide shot of a glowing quantum processor",
                narration_text="Welcome to the future of computing.",
                duration_seconds=5,
                transition="fade",
            ),
        ]
        board = Storyboard(
            scenes=scenes,
            total_duration_seconds=5,
        )
        assert len(board.scenes) == 1
        assert board.scenes[0].transition == "fade"

    def test_invalid_transition_rejected(self):
        with pytest.raises(ValidationError):
            StoryboardScene(
                scene_number=1,
                visual_prompt="Test prompt",
                narration_text="Test narration",
                duration_seconds=5,
                transition="spin",  # Not a valid transition
            )


class TestGeneratedAssets:
    """Tests for the GeneratedAssets schema."""

    def test_valid_assets(self):
        assets = GeneratedAssets(
            video_clips=[
                {"scene_number": 1, "video_url": "https://mock.url/1.mp4",
                 "status": "success"},
            ],
            voiceover_clips=[
                {"scene_number": 1, "audio_url": "https://mock.url/1.mp3",
                 "status": "success"},
            ],
            subtitle_srt="1\n00:00:00,000 --> 00:00:05,000\nHello\n",
            thumbnail={
                "image_url": "https://mock.url/thumb.png",
                "status": "success",
            },
            asset_manifest={"total_scenes": 1, "videos_generated": 1},
        )
        assert len(assets.video_clips) == 1
        assert assets.thumbnail["status"] == "success"
        assert assets.asset_manifest["videos_generated"] == 1

    def test_valid_thumbnail_result(self):
        thumbnail = ThumbnailResult(
            image_url="https://mock.url/thumb.png",
            prompt_used="Bold cinematic thumbnail",
            status="success",
        )
        assert thumbnail.status == "success"

    def test_valid_youtube_upload_result(self):
        upload = YouTubeUploadResult(
            video_id="abc123",
            video_url="https://youtu.be/abc123",
            status="success",
            privacy_status="private",
            message="Uploaded",
        )
        assert upload.privacy_status == "private"


class TestPublishingSuggestions:
    """Tests for the PublishingSuggestions schema."""

    def test_valid_publishing(self):
        pub = PublishingSuggestions(
            title="Quantum Computing Explained in 60 Seconds",
            description="A quick dive into quantum computing basics.",
            tags=["quantum", "computing", "tech", "science"],
            thumbnail_concept="Glowing quantum chip with futuristic overlay",
            best_upload_time="Tuesday 2pm EST",
            social_media_posts={"twitter": "Check out our new video!"},
            hashtags=["#quantum", "#tech", "#science"],
        )
        assert len(pub.tags) == 4
        assert "twitter" in pub.social_media_posts
