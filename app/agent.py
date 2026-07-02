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

"""VibeCast — AI Video Creation Agent.

Conversational AI video creation system built with Google ADK 2.0.

Architecture (Day 1 whitepaper): Root is a conversational LlmAgent
orchestrator with human-in-the-loop review before production.

MCP Integration (Day 2 whitepaper): asset_generator calls Google Veo,
Gemini TTS, and Imagen via the MCP media tools server.

Security (Day 4 whitepaper, Pillar 4): before_tool_callback validates
all tool inputs. MCP server is the sole egress path to external APIs.

Agent Skills (Day 3 whitepaper): scriptwriter uses a VideoProduction
skill with cinematic writing guidelines.

NOTE on output_schema + tools conflict:
  Gemini rejects requests that combine function calling (tools=[...])
  with response_mime_type=application/json (set by output_schema).
  Agents that use tools (researcher, trend_analyst) therefore drop
  output_schema and instead format JSON via their instruction text.
"""

import logging
import os
from collections.abc import AsyncGenerator
from typing import Any

from google.adk.agents import LlmAgent
from google.adk.agents.base_agent import BaseAgent
from google.adk.agents.context import Context
from google.adk.apps import App
from google.adk.events.event import Event
from google.adk.events.event_actions import EventActions
from google.adk.models import Gemini
from google.adk.tools import request_input
from google.adk.workflow import Workflow
from google.genai import types

from app.security.validators import before_tool_security_callback
from app.tools import web_search

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Environment setup for Gemini Developer API (AI Studio)
# Force False so the Gemini client uses API key auth, not Vertex AI.
# ---------------------------------------------------------------------------
os.environ["GOOGLE_GENAI_USE_VERTEXAI"] = "False"

# Model configuration
# Free tier quotas (as of 2026):
#   gemini-3-flash:   20 req/day (AI Studio free tier)
#   gemini-3.5-flash:  20 req/day (AI Studio free tier)
MODEL_NAME = os.environ.get("VIBECAST_MODEL", "gemini-3-flash-preview")
MODEL = Gemini(
    model=MODEL_NAME,
    retry_options=types.HttpRetryOptions(attempts=3),
)

# Scene generation limit to prevent exceeding credit quotas
MAX_SCENES_LIMIT = int(os.environ.get("VIBECAST_MAX_SCENES_LIMIT", "1"))


# ===========================================================================
# Node 1: Intake Agent — Parse user request into structured brief
# output_schema REMOVED: ADK injects transfer tools into sub-agents which
# conflicts with response_mime_type=application/json. Use instruction JSON.
# ===========================================================================
intake_agent = LlmAgent(
    name="intake_agent",
    model=MODEL,
    instruction=(
        "You are a video production intake specialist. Your job is to "
        "analyze the user's video request and extract a structured brief.\n\n"
        "Reply with a JSON object with these exact keys:\n"
        "  topic (str), target_audience (str), "
        "video_length_seconds (int), style (str), platform (str)\n\n"
        "Rules:\n"
        "- style must be one of: educational, entertainment, news, tutorial, documentary\n"
        "- platform must be one of: youtube, tiktok, instagram, general\n"
        "- video_length_seconds default: 60 for YouTube, 30 for TikTok/Instagram\n"
        "- If the user's request is vague, make reasonable assumptions.\n"
        "- Always produce a complete JSON object — no markdown, no explanation."
    ),
    output_key="intake",
    description="Parses user video requests into structured briefs.",
)


# ===========================================================================
# Node 2: Researcher — Gather facts about the topic
# HAS tools=[google_search] → output_schema REMOVED (Gemini 400 conflict).
# Structured output enforced via instruction text instead.
# ===========================================================================
researcher = LlmAgent(
    name="researcher",
    model=MODEL,
    tools=[web_search],
    before_tool_callback=before_tool_security_callback,
    instruction=(
        "You are a research specialist for video content creation. "
        "Use the web_search tool to find current, verifiable information "
        "about the video brief stored in state as 'intake': {intake}.\n\n"
        "Your tasks:\n"
        "1. Identify 5-8 key facts about the topic that would be "
        "interesting for the target audience\n"
        "2. List credible source URLs or named references for these facts\n"
        "3. Note trending discussions or recent developments\n"
        "4. Write a brief summary capturing the essence of the topic\n\n"
        "Focus on accuracy and relevance. Flag any claims that need "
        "verification. Prioritize recent information.\n\n"
        "Reply with a JSON object with these exact keys:\n"
        "  summary (str), key_facts (list of str), "
        "sources (list of str), trending_angles (list of str)."
    ),
    output_key="research",
    description="Researches topics for video content using web search.",
)


# ===========================================================================
# Node 3: Trend Analyst — Identify trending angles and keywords
# HAS tools=[google_search] → output_schema REMOVED (Gemini 400 conflict).
# Structured output enforced via instruction text instead.
# ===========================================================================
trend_analyst = LlmAgent(
    name="trend_analyst",
    model=MODEL,
    tools=[web_search],
    before_tool_callback=before_tool_security_callback,
    instruction=(
        "You are a social media trend analyst specializing in video "
        "content optimization. Use the web_search tool to ground your "
        "trend analysis. Given the research data: {research} "
        "and the video brief: {intake}.\n\n"
        "Your tasks:\n"
        "1. Identify 8-12 SEO-friendly keywords for this topic\n"
        "2. Suggest 3-5 effective hook styles that are trending\n"
        "3. Recommend the best video style for this topic and audience\n"
        "4. Analyze what competitors/similar creators are doing\n"
        "5. Estimate engagement potential (high/medium/low)\n\n"
        "Base your analysis on current content trends for the target "
        "platform. Consider audience retention patterns.\n\n"
        "Reply with a JSON object with these exact keys:\n"
        "  keywords (list of str), hook_styles (list of str), "
        "recommended_style (str), competitor_analysis (str), "
        "engagement_potential (str)."
    ),
    output_key="trends",
    description="Analyzes content trends for video optimization.",
)


# ===========================================================================
# Node 4: Scriptwriter — Generate engaging video script
# output_schema REMOVED: ADK transfer tools + output_schema = 400 error.
# ===========================================================================
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
        f"2. SEGMENTS: Break the content into {MAX_SCENES_LIMIT} segment(s). "
        f"CRITICAL: Generate EXACTLY {MAX_SCENES_LIMIT} segment(s) to conserve generation credits.\n"
        f"3. PACING: Vary segment lengths to maintain engagement\n"
        f"4. CTA: End with a clear call-to-action\n\n"
        f"Reply with a JSON object with these exact keys:\n"
        f"  title (str), hook (str), segments (list of objects with: "
        f"segment_number, narration, on_screen_text, duration_seconds), "
        f"cta (str), total_duration_seconds (int)\n\n"
        f"- Use conversational, energetic language\n"
        f"- Each segment should be 5-15 seconds\n"
        f"- Total duration should match the brief: {{intake}}\n"
        f"- The hook should use one of these trending styles: {{trends}}\n"
        f"- No markdown, no explanation — pure JSON only."
    ),
    output_key="script",
    description="Creates engaging video scripts with hooks and CTAs.",
)


# ===========================================================================
# Node 5: Storyboard Agent — Break script into visual scenes
# output_schema REMOVED: ADK transfer tools + output_schema = 400 error.
# ===========================================================================
storyboard_agent = LlmAgent(
    name="storyboard_agent",
    model=MODEL,
    instruction=(
        f"You are a visual storyboard director. Convert the video "
        f"script: {{script}} into a detailed storyboard.\n\n"
        f"CRITICAL: Generate EXACTLY {MAX_SCENES_LIMIT} scene(s) to conserve generation credits.\n\n"
        f"Reply with a JSON object with one key 'scenes' containing a list. "
        f"Each scene object must have:\n"
        f"  scene_number (int, starting at 1), visual_prompt (str), "
        f"narration_text (str), duration_seconds (int), "
        f"transition (str: cut/fade/dissolve/wipe/zoom)\n\n"
        f"visual_prompt best practices:\n"
        f"- Start with the subject/action\n"
        f"- Include camera angle, lighting, color palette, motion\n"
        f"- Specify camera movement (pan, zoom, tracking shot)\n"
        f"- Include style keywords (cinematic, documentary, vibrant)\n"
        f"- Keep under 200 words per prompt\n"
        f"- No markdown, no explanation — pure JSON only."
    ),
    output_key="storyboard",
    description="Creates visual storyboards from scripts.",
)


# ===========================================================================
# Node 6: Asset Generator — Call clients for media generation
# ===========================================================================
async def asset_generator(ctx: Context, node_input: Any) -> Event:
    """Generate video, audio, and subtitle assets via media clients.

    This function node reads the storyboard from workflow state and
    calls the media clients to generate:
    - Video clips via Google Veo (one per scene)
    - Voiceover clips via Gemini TTS (one per scene)
    - Thumbnail image via Google Imagen
    - SRT subtitles from all narration segments

    The MCP server handles security validation internally, and is
    the sole egress point to external APIs (Day 4, Pillar 4).
    """
    # Read storyboard from state
    storyboard_data = _state_to_dict(ctx.state.get("storyboard", {}))
    scenes = storyboard_data.get("scenes", [])[:MAX_SCENES_LIMIT]

    if not scenes:
        logger.warning("No scenes in storyboard — skipping asset gen")
        empty_assets = {
            "video_clips": [], "voiceover_clips": [],
            "subtitle_srt": "", "thumbnail": {},
            "asset_manifest": {},
        }
        return Event(
            output=empty_assets,
            actions=EventActions(state_delta={"assets": empty_assets}),
        )

    from app.mcp_server.imagen_client import ImagenClient
    from app.mcp_server.tts_client import GeminiTTSClient
    from app.mcp_server.veo_client import VeoClient
    from app.security.validators import (
        validate_thumbnail_prompt,
        validate_tts_text,
        validate_video_prompt,
    )

    imagen_client = ImagenClient()
    veo_real = VeoClient()
    tts_real = GeminiTTSClient()

    # Initialize mock clients for subsequent scenes to protect developer credits
    veo_mock = VeoClient(mock_mode=True)
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
        veo_client = veo_real if i == 0 else veo_mock
        tts_client = tts_real if i == 0 else tts_mock

        # Generate video clip
        try:
            clean_prompt = validate_video_prompt(visual_prompt)
            video_url = await veo_client.generate_video(
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

    publishing_data = _state_to_dict(ctx.state.get("publishing", {}))
    script_data = _state_to_dict(ctx.state.get("script", {}))
    thumbnail_prompt = publishing_data.get("thumbnail_concept") or (
        f"YouTube thumbnail for '{script_data.get('title', 'VibeCast video')}'. "
        "Bold, high-contrast, cinematic, readable at small size, no small text."
    )
    try:
        clean_thumbnail_prompt = validate_thumbnail_prompt(thumbnail_prompt)
        thumbnail = await imagen_client.generate_thumbnail(clean_thumbnail_prompt)
    except Exception as e:
        logger.error("Thumbnail generation failed: %s", e)
        thumbnail = {
            "image_url": "",
            "prompt_used": thumbnail_prompt,
            "status": "error",
            "error": str(e),
        }

    assets = {
        "video_clips": video_clips,
        "voiceover_clips": voiceover_clips,
        "subtitle_srt": srt_content,
        "thumbnail": thumbnail,
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

    return Event(
        output=assets,
        actions=EventActions(state_delta={"assets": assets}),
    )


async def auto_publisher(ctx: Context, node_input: Any) -> Event:
    """Upload the generated video to YouTube after metadata is ready."""
    from app.mcp_server.youtube_client import YouTubeClient

    assets = _state_to_dict(ctx.state.get("assets", {}))
    publishing = _state_to_dict(ctx.state.get("publishing", {}))
    video_clips = assets.get("video_clips", [])
    first_video = video_clips[0].get("video_url", "") if video_clips else ""

    if not first_video:
        result = {
            "video_id": "",
            "video_url": "",
            "status": "skipped",
            "privacy_status": "private",
            "message": "No generated video was available to upload.",
        }
        return Event(
            output=result,
            actions=EventActions(state_delta={"upload_result": result}),
        )

    thumbnail = _state_to_dict(assets.get("thumbnail", {}))
    client = YouTubeClient()
    result = await client.upload(
        video_path=first_video,
        title=publishing.get("title", "VibeCast Generated Video"),
        description=publishing.get("description", ""),
        tags=publishing.get("tags", []),
        thumbnail_path=thumbnail.get("image_url", ""),
        privacy_status=os.environ.get("YOUTUBE_PRIVACY_STATUS", "private"),
    )
    return Event(
        output=result,
        actions=EventActions(state_delta={"upload_result": result}),
    )


def _state_to_dict(value: Any) -> dict[str, Any]:
    """Normalise ADK state values from Pydantic models, plain dicts, or JSON strings."""
    if not value:
        return {}
    if isinstance(value, dict):
        return value
    if hasattr(value, "model_dump"):
        return value.model_dump()
    if isinstance(value, str):
        import json
        cleaned = value.strip()
        if cleaned.startswith("```json"):
            cleaned = cleaned[7:]
        elif cleaned.startswith("```"):
            cleaned = cleaned[3:]
        if cleaned.endswith("```"):
            cleaned = cleaned[:-3]
        cleaned = cleaned.strip()
        try:
            return json.loads(cleaned)
        except Exception as e:
            logger.error("Failed to parse state string as JSON: %s. Value: %r", e, value)
            return {}
    return {}


def _srt_time(seconds: float) -> str:
    """Format seconds as SRT timestamp HH:MM:SS,mmm."""
    h = int(seconds // 3600)
    m = int((seconds % 3600) // 60)
    s = int(seconds % 60)
    ms = int((seconds % 1) * 1000)
    return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"


# ===========================================================================
# Node 7: Publishing Advisor — Generate metadata and recommendations
# output_schema REMOVED: ADK transfer tools + output_schema = 400 error.
# ===========================================================================
publishing_advisor = LlmAgent(
    name="publishing_advisor",
    model=MODEL,
    instruction=(
        "You are a social media publishing strategist. Given the "
        "video script: {script}, generated assets: {assets}, and "
        "trend analysis: {trends}, create comprehensive publishing "
        "recommendations.\n\n"
        "Reply with a JSON object with these exact keys:\n"
        "  title (str, under 60 chars), description (str, under 5000 chars), "
        "tags (list of 15-20 str), thumbnail_concept (str), "
        "best_upload_time (str), social_media_posts (object with: "
        "twitter str, linkedin str, instagram str), "
        "hashtags (list of 10-15 str)\n\n"
        "- Integrate keywords naturally in the description\n"
        "- Base upload time on platform: {intake}\n"
        "- No markdown, no explanation — pure JSON only."
    ),
    output_key="publishing",
    description="Creates publishing metadata and social media strategy.",
)


# ===========================================================================
# HITL Gate — Formal script review using ADK request_input (Day 1 pattern)
# ===========================================================================
script_review_agent = LlmAgent(
    name="script_review_agent",
    model=MODEL,
    tools=[request_input],
    instruction=(
        "You are the script review gatekeeper for VibeCast.\n\n"
        "Your ONLY job is to present the script to the user and get their "
        "approval before production begins.\n\n"
        "1. Read the script from state: {script}\n"
        "2. Present a clear summary: title, hook, segment count, CTA\n"
        "3. Call the adk_request_input tool with a message asking the user "
        "to approve or request changes\n"
        "4. If the user approves, say 'Script approved! Proceeding to production.' "
        "and transfer to production_pipeline_agent\n"
        "5. If the user requests changes, note the feedback and transfer "
        "back to the orchestrator\n\n"
        "CRITICAL: You MUST call adk_request_input to formally pause the "
        "workflow and wait for human approval. This creates a formal "
        "suspension point in the workflow state."
    ),
    output_key="script_review_decision",
    description=(
        "Human-in-the-Loop gate that formally suspends the workflow "
        "using ADK request_input until the user approves the script."
    ),
)


# ===========================================================================
# Production Workflow — Deterministic pipeline after script approval
# ===========================================================================
production_pipeline = Workflow(
    name="production_pipeline",
    description=(
        "Deterministic production workflow: storyboard → Veo video → "
        "Gemini TTS → Imagen thumbnail → subtitles → publishing → YouTube."
    ),
    edges=[
        ("START", storyboard_agent),
        (storyboard_agent, asset_generator),
        (asset_generator, publishing_advisor),
        (publishing_advisor, auto_publisher),
    ],
)


# ---------------------------------------------------------------------------
# Workflow wrapper — ADK's LlmAgent.sub_agents requires BaseAgent instances.
# Workflow extends BaseNode but NOT BaseAgent, so we wrap it here.
# ---------------------------------------------------------------------------
class ProductionPipelineAgent(BaseAgent):
    """Thin BaseAgent wrapper that delegates to the production_pipeline Workflow.

    This lets the conversational orchestrator transfer control to the
    deterministic Workflow via the standard sub_agents mechanism.
    """

    workflow: Workflow

    async def _run_impl(
        self, *, ctx: Context, node_input: Any
    ) -> AsyncGenerator[Event, None]:
        """Stream events from the wrapped Workflow."""
        async for event in self.workflow.run(ctx=ctx, node_input=node_input):
            yield event


production_pipeline_agent = ProductionPipelineAgent(
    name="production_pipeline_agent",
    workflow=production_pipeline,
    description=(
        "Runs the full deterministic production pipeline: storyboard, "
        "Veo video, Gemini TTS voiceover, Imagen thumbnail, SRT subtitles, "
        "publishing metadata, and private YouTube upload."
    ),
)

production_coordinator = LlmAgent(
    name="production_coordinator",
    model=MODEL,
    sub_agents=[script_review_agent, production_pipeline_agent],
    instruction=(
        "You coordinate Phase 4 production for VibeCast.\n\n"
        "When the user is ready for production:\n"
        "1. First, transfer to 'script_review_agent' for formal HITL approval\n"
        "2. Once the script is approved, transfer to "
        "'production_pipeline_agent' to execute the deterministic pipeline\n\n"
        "The pipeline generates:\n"
        "* Storyboard from the approved script\n"
        "* Video clip via Google Veo\n"
        "* Voiceover via Gemini TTS\n"
        "* Thumbnail via Google Imagen\n"
        "* SRT subtitles\n"
        "* Publishing metadata (title, description, tags, hashtags)\n"
        "* Private YouTube upload"
    ),
    description="Coordinates HITL script review and deterministic production.",
)

root_agent = LlmAgent(
    name="vibecast_orchestrator",
    model=MODEL,
    sub_agents=[
        intake_agent,
        researcher,
        trend_analyst,
        scriptwriter_agent,
        production_coordinator,
    ],
    before_tool_callback=before_tool_security_callback,
    instruction=(
        "You are VibeCast, a conversational AI video creation orchestrator "
        "built for the Kaggle AI Agents capstone.\n\n"
        "PHASE 1 - INTAKE:\n"
        "- Ask for platform, target audience, style, and duration when missing.\n"
        "- Confirm the creative brief before proceeding.\n\n"
        "PHASE 2 - RESEARCH AND TRENDS:\n"
        "- Transfer to researcher for search-grounded facts and sources.\n"
        "- Transfer to trend_analyst for search-grounded hooks, keywords, "
        "and competitor angles.\n\n"
        "PHASE 3 - SCRIPT REVIEW (Human-in-the-Loop):\n"
        "- Transfer to scriptwriter_agent for the script.\n"
        "- Present the title, hook, segment plan, CTA to the user.\n"
        "- The production pipeline includes a formal HITL gate "
        "(script_review_gate) that suspends the workflow state using "
        "ADK RequestInput until the user explicitly approves.\n"
        "- If the user requests changes, transfer back to scriptwriter_agent "
        "with the feedback.\n\n"
        "PHASE 4 - PRODUCTION (Deterministic Pipeline):\n"
        "- After the user signals readiness, transfer to production_coordinator.\n"
        "- The pipeline will formally request approval via the HITL gate, "
        "then execute: storyboard → Veo video → Gemini TTS → Imagen thumbnail "
        "→ subtitles → publishing metadata → private YouTube upload.\n\n"
        "Be clear, practical, and demo-ready. Keep the user in the loop and "
        "surface approvals before expensive generation steps."
    ),
    description=(
        "Conversational VibeCast orchestrator with stateful HITL review gates."
    ),
)


# ===========================================================================
# ADK Application Container
# ===========================================================================
app = App(
    root_agent=root_agent,
    name="vibecast",
)
