# Copyright 2026 VibeCast Team
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     https://www.apache.org/licenses/LICENSE-2.0

"""Unit tests for the FastAPI application endpoints."""

import os
import pytest
from fastapi.testclient import TestClient

from app.fast_api_app import api


@pytest.fixture
def client():
    # Force mock mode for fast testing without external API hits
    os.environ["VIBECAST_MOCK_MODE"] = "true"
    return TestClient(api)


def test_health_endpoint(client):
    response = client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "healthy"
    assert data["service"] == "vibecast"


def test_info_endpoint(client):
    response = client.get("/info")
    assert response.status_code == 200
    data = response.json()
    assert data["name"] == "VibeCast"
    assert "workflow_nodes" in data
    assert "mcp_tools" in data


def test_chat_endpoint(client):
    # Send a request to the chat endpoint
    payload = {
        "message": "Make a short educational video about space exploration.",
        "user_id": "test_user"
    }
    response = client.post("/chat", json=payload)
    assert response.status_code == 200
    data = response.json()
    assert "response" in data
    assert "session_id" in data
    assert "state" in data
