# Copyright 2026 VibeCast Team
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     https://www.apache.org/licenses/LICENSE-2.0

"""FastAPI application wrapper for VibeCast ADK agent.

This module provides the HTTP entry point for Cloud Run deployment.
It wraps the ADK App with FastAPI middleware for health checks,
CORS, and request logging.

Deployment target: Google Cloud Run (Day 4 whitepaper).
"""

import logging
import os

from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from google.adk.runners import InMemoryRunner
from google.genai import types

# Load environment variables for health/info endpoints and local deployment.
load_dotenv()

logger = logging.getLogger(__name__)

# FastAPI wrapper for additional endpoints
api = FastAPI(
    title="VibeCast API",
    description="AI-powered video creation agent",
    version="0.1.0",
)

# CORS for local development
api.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://localhost:8080"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@api.get("/health")
async def health_check():
    """Health check endpoint for Cloud Run."""
    return {
        "status": "healthy",
        "service": "vibecast",
        "mock_mode": os.environ.get("VIBECAST_MOCK_MODE", "true"),
    }


@api.get("/info")
async def service_info():
    """Service information endpoint."""
    return {
        "name": "VibeCast",
        "version": "0.1.0",
        "description": "AI-powered video creation agent",
        "workflow_nodes": [
            "vibecast_orchestrator",
            "intake_agent",
            "researcher",
            "trend_analyst",
            "scriptwriter_agent",
            "production_coordinator",
            "production_pipeline_agent",
            "storyboard_agent",
            "asset_generator",
            "publishing_advisor",
            "auto_publisher",
        ],
        "mcp_tools": [
            "generate_video",
            "generate_voiceover",
            "generate_thumbnail",
            "generate_subtitles",
            "upload_to_youtube",
        ],
    }


# Initialize ADK runner lazily to avoid circular imports during app startup
_runner: InMemoryRunner | None = None

def _get_runner() -> InMemoryRunner:
    global _runner
    if _runner is None:
        from app.agent import app as vibecast_app
        _runner = InMemoryRunner(app=vibecast_app)
    return _runner


class ChatRequest(BaseModel):
    message: str
    session_id: str | None = None
    user_id: str = "default_user"


class ChatResponse(BaseModel):
    response: str
    session_id: str
    state: dict


@api.post("/chat", response_model=ChatResponse)
async def chat_endpoint(req: ChatRequest):
    """Invoke the ADK agent for a multi-turn session chat conversation."""
    runner = _get_runner()
    user_id = req.user_id or "default_user"

    if req.session_id:
        session_id = req.session_id
        try:
            session = await runner.session_service.get_session(
                app_name=runner.app_name, session_id=session_id, user_id=user_id
            )
        except Exception:
            session = await runner.session_service.create_session(
                app_name=runner.app_name, user_id=user_id, session_id=session_id
            )
    else:
        session = await runner.session_service.create_session(
            app_name=runner.app_name, user_id=user_id
        )
        session_id = session.id

    agent_response_parts = []

    async for event in runner.run_async(
        user_id=user_id,
        session_id=session_id,
        new_message=types.Content(
            role="user",
            parts=[types.Part.from_text(text=req.message)],
        ),
    ):
        if event.content:
            for part in event.content.parts or []:
                if part.text:
                    agent_response_parts.append(part.text)

    # Fetch updated state
    updated_session = await runner.session_service.get_session(
        app_name=runner.app_name, session_id=session_id, user_id=user_id
    )
    state_dict = {}
    if updated_session.state:
        if hasattr(updated_session.state, "model_dump"):
            state_dict = updated_session.state.model_dump()
        elif isinstance(updated_session.state, dict):
            state_dict = updated_session.state

    return ChatResponse(
        response="".join(agent_response_parts),
        session_id=session_id,
        state=state_dict,
    )
