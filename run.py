# ruff: noqa: E402
# Copyright 2026 VibeCast Team
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     https://www.apache.org/licenses/LICENSE-2.0

"""Local demo runner for VibeCast.

Handles multi-turn conversation with the agent for a hands-free demo.
"""

import asyncio
import json
import logging
import os
import sys

# CRITICAL: Set this BEFORE any ADK/GenAI imports to use AI Studio (Gemini Developer API)
# instead of Vertex AI (Google Cloud). Must be "False" for API key auth.
os.environ["GOOGLE_GENAI_USE_VERTEXAI"] = "False"

from dotenv import load_dotenv

load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)

from google.adk.runners import InMemoryRunner
from google.genai import types

from app.agent import app


def _get_agent_text(content: types.Content | None) -> str:
    """Extract text from a Content object."""
    if content is None:
        return ""
    parts_text = []
    for part in content.parts or []:
        if part.text:
            parts_text.append(part.text)
    return "\n".join(parts_text)


def _has_function_call(content: types.Content | None) -> bool:
    """Check if the content contains a function call (transfer_to_agent)."""
    if content is None:
        return False
    for part in content.parts or []:
        if part.function_call:
            return True
    return False


async def run_demo():
    runner = InMemoryRunner(app=app)

    session = await runner.session_service.create_session(
        app_name=runner.app_name, user_id="local_user"
    )

    initial_prompt = "Make a short educational video about quantum computing basics."
    mock_mode = os.environ.get("VIBECAST_MOCK_MODE", "true")

    sep = "=" * 70
    print(sep)
    print("VibeCast AI Video Creation Agent - Demo Run")
    print(f"Session: {session.id}")
    print(f"Mock Mode: {mock_mode}")
    print(sep)

    # Pre-programmed conversation for the demo
    follow_ups = iter([
        "Yes, the brief looks correct. Proceed with research.",
        "Looks great! Proceed with production.",
        "Yes, upload it.",
    ])

    current_msg = initial_prompt
    turn = 0
    max_turns = 10

    while turn < max_turns:
        print(f"\n--- Turn {turn + 1} ---")
        print(f">>> User: {current_msg}\n")

        events = []
        has_text_response = False

        async for event in runner.run_async(
            user_id="local_user",
            session_id=session.id,
            new_message=types.Content(
                role="user",
                parts=[types.Part.from_text(text=current_msg)],
            ),
        ):
            events.append(event)

            # Print state changes
            if event.actions and event.actions.state_delta:
                for key, value in event.actions.state_delta.items():
                    print(f"  [state:{key}] ", end="")
                    if isinstance(value, str):
                        print(value[:200])
                    elif isinstance(value, dict):
                        print(json.dumps(value, default=str)[:200])

            # Print agent text
            if event.content:
                text = _get_agent_text(event.content)
                if text:
                    has_text_response = True
                    for line in text.strip().split("\n"):
                        line = line.strip()
                        if line:
                            print(f"  {line}")

            if event.content:
                for part in event.content.parts or []:
                    if part.function_call:
                        print(f"  [call: {part.function_call.name}]")

            if event.actions and event.actions.end_of_agent:
                print(f"  [end: {event.author}]")

        # If the agent produced text, it's probably asking for input
        if has_text_response:
            try:
                current_msg = next(follow_ups)
            except StopIteration:
                print("\n[No more pre-programmed responses - ending demo]")
                break
        else:
            # Agent may have finished without output
            print("[No agent response - ending]")
            break

        turn += 1

    print(f"\n{sep}")
    print("Demo complete.")
    print(sep)


if __name__ == "__main__":
    asyncio.run(run_demo())
