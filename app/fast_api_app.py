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
