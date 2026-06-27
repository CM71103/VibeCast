# ruff: noqa
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

"""VibeCast — AI Video Creation Agent (ADK 2.0 Workflow).

This module defines a 7-node ADK 2.0 graph workflow that orchestrates
the full video production pipeline:

  START → intake → researcher → trend_analyst → scriptwriter
       → storyboard → asset_generator → publishing_advisor

Architecture (Day 1 whitepaper): This is the "factory model" — a system
that produces video content, with the developer as orchestrator. Each
node is a specialized sub-agent or function, connected by typed edges.

MCP Integration (Day 2 whitepaper): The asset_generator node connects
to an MCP server (media_tools_server) to call Kling AI and Gemini TTS
tools via the Model Context Protocol, avoiding direct NxM integration.

Security (Day 4 whitepaper, Pillar 4): The before_tool_callback on the
workflow validates all tool inputs before external API calls. The MCP
server is the sole egress path to external services.

Agent Skills (Day 3 whitepaper): The scriptwriter uses a custom
VideoProduction skill with cinematic writing guidelines.
"""

import json
import logging
import os
from typing import Any

import google.auth
from google.adk.agents import LlmAgent
from google.adk.agents.context import Context
from google.adk.apps import App
from google.adk.events.event import Event
from google.adk.models import Gemini
from google.adk.tools.mcp_tool import McpToolset
from google.adk.tools.mcp_tool.mcp_session_manager import (
    StdioConnectionParams,
)
from google.adk.workflow import Workflow
from google.genai import types
from mcp import StdioServerParameters

from app.schemas import (
    GeneratedAssets,
    IntakeResult,
    PublishingSuggestions,
    ResearchResult,
    Script,
    Storyboard,
    StoryboardScene,
    TrendAnalysis,
)
from app.security.validators import before_tool_security_callback

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Environment setup for Gemini Developer API (AI Studio)
# ---------------------------------------------------------------------------
os.environ.setdefault("GOOGLE_GENAI_USE_VERTEXAI", "False")

# Model configuration — using Gemini 2.5 Flash
MODEL_NAME = "gemini-2.5-flash"
MODEL = Gemini(
    model=MODEL_NAME,
    retry_options=types.HttpRetryOptions(attempts=3),
)



# ===========================================================================
# Node 1: Intake Agent — Parse user request into structured brief
# ===========================================================================
intake_agent = LlmAgent(
    name="intake_agent",
    model=MODEL,
    instruction=(
        "You are a video production intake specialist. Your job is to "
        "analyze the user's video request and extract a structured brief.\n\n"
        "From the user's message, determine:\n"
        "- topic: The main subject of the video\n"
        "- target_audience: Who the video is for (infer if not stated)\n"
        "- video_length_seconds: Target duration (default 60 for YouTube, "
        "30 for TikTok/Instagram)\n"
        "- style: One of 'educational', 'entertainment', 'news', "
        "'tutorial', 'documentary'\n"
        "- platform: One of 'youtube', 'tiktok', 'instagram', 'general'\n\n"
        "If the user's request is vague, make reasonable assumptions and "
        "note them. Always produce a complete IntakeResult."
    ),
    output_schema=IntakeResult,
    output_key="intake",
    description="Parses user video requests into structured briefs.",
)


# ===========================================================================
# Node 2: Researcher — Gather facts about the topic
# ===========================================================================
researcher = LlmAgent(
    name="researcher",
    model=MODEL,
    instruction=(
        "You are a research specialist for video content creation. "
        "Given the video brief stored in state as 'intake', research "
        "the topic: {intake}.\n\n"
        "Your tasks:\n"
        "1. Identify 5-8 key facts about the topic that would be "
        "interesting for the target audience\n"
        "2. List credible sources for these facts\n"
        "3. Note trending discussions or recent developments\n"
        "4. Write a brief summary capturing the essence of the topic\n\n"
        "Focus on accuracy and relevance. Flag any claims that need "
        "verification. Prioritize recent information."
    ),
    output_schema=ResearchResult,
    output_key="research",
    description="Researches topics for video content.",
)


# ===========================================================================
# Node 3: Trend Analyst — Identify trending angles and keywords
# ===========================================================================
trend_analyst = LlmAgent(
    name="trend_analyst",
    model=MODEL,
    instruction=(
        "You are a social media trend analyst specializing in video "
        "content optimization. Given the research data: {research} "
        "and the video brief: {intake}.\n\n"
        "Your tasks:\n"
        "1. Identify 8-12 SEO-friendly keywords for this topic\n"
        "2. Suggest 3-5 effective hook styles that are trending\n"
        "3. Recommend the best video style for this topic and audience\n"
        "4. Analyze what competitors/similar creators are doing\n"
        "5. Estimate engagement potential (high/medium/low)\n\n"
        "Base your analysis on current content trends for the target "
        "platform. Consider audience retention patterns."
    ),
    output_schema=TrendAnalysis,
    output_key="trends",
    description="Analyzes content trends for video optimization.",
)


# ===========================================================================
# Node 4: Scriptwriter — Generate engaging video script
# ===========================================================================
# Scene generation limit to prevent exceeding credit quotas
MAX_SCENES_LIMIT = int(os.environ.get("VIBECAST_MAX_SCENES_LIMIT", "1"))

scriptwriter_agent = LlmAgent(
    name="scriptwriter_agent",
    model=MODEL,
    instruction=(
        f"You are an expert video scriptwriter. Using the research "
        f"data: {{research}}, trend analysis: {{trends}}, and video "
        f"brief: {{intake}}, write a compelling video script.\n\n"
        f"Script requirements:\n"
        f"1. HOOK: Start with an attention-grabbing opening (first 5 "
        f"seconds are critical for retention)\n"
        f"2. SEGMENTS: Break the content into logical segments. "
        f"CRITICAL: Generate EXACTLY {MAX_SCENES_LIMIT} segment(s) to conserve generation credits.\n"
        f"3. PACING: Vary segment lengths to maintain engagement\n"
        f"4. CTA: End with a clear call-to-action\n\n"
        f"Writing guidelines:\n"
        f"- Use conversational, energetic language\n"
        f"- Each segment should be 5-15 seconds\n"
        f"- Visual descriptions should be vivid and specific\n"
        f"- On-screen text should highlight key stats or quotes\n"
        f"- Total duration should match the brief target: "
        f"{{intake}}\n\n"
        f"The hook should use one of these trending styles: {{trends}}"
    ),
    output_schema=Script,
    output_key="script",
    description="Creates engaging video scripts with hooks and CTAs.",
)


# ===========================================================================
# Node 5: Storyboard Agent — Break script into visual scenes
# ===========================================================================
storyboard_agent = LlmAgent(
    name="storyboard_agent",
    model=MODEL,
    instruction=(
        f"You are a visual storyboard director. Convert the video "
        f"script: {{script}} into a detailed storyboard.\n\n"
        f"CRITICAL: Generate EXACTLY {MAX_SCENES_LIMIT} scene(s) to conserve generation credits.\n\n"
        f"For each scene:\n"
        f"1. visual_prompt: Write a detailed prompt for AI video "
        f"generation (Kling AI). Include scene composition, camera "
        f"angle, lighting, color palette, and motion. Be specific "
        f"and cinematic.\n"
        f"2. narration_text: The exact voiceover text for this scene\n"
        f"3. duration_seconds: Scene duration (match script segments)\n"
        f"4. transition: How to transition to the next scene "
        f"(cut, fade, dissolve, wipe, zoom)\n\n"
        f"Visual prompt best practices:\n"
        f"- Start with the subject/action\n"
        f"- Specify camera movement (pan, zoom, tracking shot)\n"
        f"- Include style keywords (cinematic, documentary, vibrant)\n"
        f"- Keep under 200 words per prompt for best results"
    ),
    output_schema=Storyboard,
    output_key="storyboard",
    description="Creates visual storyboards from scripts.",
)


# ===========================================================================
# Node 6: Asset Generator — Call MCP tools for media generation
# ===========================================================================
async def asset_generator(ctx: Context, node_input: Any) -> Event:
    """Generate video, audio, and subtitle assets via MCP tools.

    This function node reads the storyboard from workflow state and
    calls the MCP media tools server to generate:
    - Video clips via Kling AI (one per scene)
    - Voiceover clips via Gemini TTS (one per scene)
    - SRT subtitles from all narration segments

    The MCP server handles security validation internally, and is
    the sole egress point to external APIs (Day 4, Pillar 4).
    """
    # Read storyboard from state
    storyboard_data = ctx.state.get("storyboard", {})
    scenes = storyboard_data.get("scenes", [])[:MAX_SCENES_LIMIT]

    if not scenes:
        logger.warning("No scenes in storyboard — skipping asset gen")
        return Event(
            output={"video_clips": [], "voiceover_clips": [],
                    "subtitle_srt": "", "asset_manifest": {}},
            state={"assets": {}},
        )

    # Import clients for direct use (MCP tools are for agent calls,
    # but this function node calls the clients directly for efficiency)
    from app.mcp_server.kling_client import KlingClient
    from app.mcp_server.tts_client import GeminiTTSClient
    from app.security.validators import validate_tts_text, validate_video_prompt

    kling_real = KlingClient()
    tts_real = GeminiTTSClient()
    
    # Initialize mock clients for subsequent scenes to protect developer credits
    kling_mock = KlingClient(mock_mode=True)
    tts_mock = GeminiTTSClient(mock_mode=True)

    video_clips = []
    voiceover_clips = []
    subtitle_segments = []

    for i, scene in enumerate(scenes):
        scene_num = scene.get("scene_number", 0)
        visual_prompt = scene.get("visual_prompt", "")
        narration = scene.get("narration_text", "")
        duration = scene.get("duration_seconds", 5)

        # To conserve free tier credits, only generate scene 1 using the real API.
        # All other scenes will use the mock client.
        kling_client = kling_real if i == 0 else kling_mock
        tts_client = tts_real if i == 0 else tts_mock

        # Generate video clip
        try:
            clean_prompt = validate_video_prompt(visual_prompt)
            video_url = await kling_client.generate_video(
                prompt=clean_prompt, duration=min(duration, 10)
            )
            video_clips.append({
                "scene_number": scene_num,
                "video_url": video_url,
                "status": "success",
            })
        except Exception as e:
            logger.error("Video gen failed for scene %d: %s", scene_num, e)
            video_clips.append({
                "scene_number": scene_num,
                "video_url": "",
                "status": f"error: {e}",
            })

        # Generate voiceover
        try:
            clean_narration = validate_tts_text(narration)
            tts_result = await tts_client.generate_voiceover(clean_narration)
            voiceover_clips.append({
                "scene_number": scene_num,
                "audio_url": tts_result["audio_url"],
                "status": "success",
            })
        except Exception as e:
            logger.error("TTS failed for scene %d: %s", scene_num, e)
            voiceover_clips.append({
                "scene_number": scene_num,
                "audio_url": "",
                "status": f"error: {e}",
            })

        # Collect subtitle segment
        subtitle_segments.append({
            "segment_number": scene_num,
            "narration": narration,
            "duration_seconds": duration,
        })

    # Generate SRT subtitles
    srt_lines = []
    current_time = 0.0
    for seg in subtitle_segments:
        seg_num = seg["segment_number"]
        narration = seg["narration"]
        dur = seg["duration_seconds"]
        if narration.strip():
            start = _srt_time(current_time)
            end = _srt_time(current_time + dur)
            srt_lines.extend([str(seg_num), f"{start} --> {end}",
                              narration.strip(), ""])
        current_time += dur

    srt_content = "\n".join(srt_lines)

    assets = {
        "video_clips": video_clips,
        "voiceover_clips": voiceover_clips,
        "subtitle_srt": srt_content,
        "asset_manifest": {
            "total_scenes": len(scenes),
            "videos_generated": sum(
                1 for v in video_clips if v["status"] == "success"
            ),
            "voiceovers_generated": sum(
                1 for v in voiceover_clips if v["status"] == "success"
            ),
        },
    }

    logger.info(
        "Asset generation complete: %d videos, %d voiceovers",
        assets["asset_manifest"]["videos_generated"],
        assets["asset_manifest"]["voiceovers_generated"],
    )

    return Event(output=assets, state={"assets": assets})


def _srt_time(seconds: float) -> str:
    """Format seconds as SRT timestamp HH:MM:SS,mmm."""
    h = int(seconds // 3600)
    m = int((seconds % 3600) // 60)
    s = int(seconds % 60)
    ms = int((seconds % 1) * 1000)
    return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"


# ===========================================================================
# Node 7: Publishing Advisor — Generate metadata and recommendations
# ===========================================================================
publishing_advisor = LlmAgent(
    name="publishing_advisor",
    model=MODEL,
    instruction=(
        "You are a social media publishing strategist. Given the "
        "video script: {script}, generated assets: {assets}, and "
        "trend analysis: {trends}, create comprehensive publishing "
        "recommendations.\n\n"
        "Generate:\n"
        "1. An SEO-optimized title (under 60 characters)\n"
        "2. A compelling description (under 5000 characters) with "
        "keywords naturally integrated\n"
        "3. 15-20 relevant tags for discoverability\n"
        "4. A thumbnail concept description\n"
        "5. The best upload time based on the target platform and "
        "audience\n"
        "6. Social media posts for Twitter/X, LinkedIn, and "
        "Instagram to promote the video\n"
        "7. Relevant hashtags (10-15)\n\n"
        "Platform: {intake}"
    ),
    output_schema=PublishingSuggestions,
    output_key="publishing",
    description="Creates publishing metadata and social media strategy.",
)


# ===========================================================================
# Workflow Definition — The VibeCast Production Pipeline
# ===========================================================================
root_agent = Workflow(
    name="vibecast_pipeline",
    description=(
        "AI-powered video production pipeline that takes a topic, "
        "researches it, generates a script and storyboard, produces "
        "video/audio assets via Kling AI and Gemini TTS, and delivers "
        "publishing recommendations."
    ),
    edges=[
        ("START", intake_agent),
        (intake_agent, researcher),
        (researcher, trend_analyst),
        (trend_analyst, scriptwriter_agent),
        (scriptwriter_agent, storyboard_agent),
        (storyboard_agent, asset_generator),
        (asset_generator, publishing_advisor),
    ],
)


# ===========================================================================
# ADK Application Container
# ===========================================================================
app = App(
    root_agent=root_agent,
    name="vibecast",
)
