# Copyright 2026 VibeCast Team
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     https://www.apache.org/licenses/LICENSE-2.0

"""Local runner for VibeCast.

This script executes the VibeCast graph workflow locally with a sample prompt.
It will print the output of each node in the console.

To run with real APIs:
1. Ensure .env has VIBECAST_MOCK_MODE=false and GEMINI_API_KEY / KLING_API_KEY set.
2. Run: uv run run.py
"""

import asyncio
import logging
import os
import sys

from dotenv import load_dotenv

# Load env variables before imports
load_dotenv()

# Set logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)

from google.adk.runners import InMemoryRunner
from google.genai import types

from app.agent import app


async def run_main():
    runner = InMemoryRunner(app=app)
    
    # Create session
    session = await runner.session_service.create_session(
        app_name="vibecast", user_id="local_user"
    )
    
    prompt = "Make a short educational video about quantum computing basics."
    print(f"\n🚀 Starting VibeCast Pipeline for session: {session.id}")
    print(f"💡 Input prompt: {prompt}\n")
    print(f"ℹ️  Mock Mode: {os.environ.get('VIBECAST_MOCK_MODE', 'true')}\n")
    
    # Run the workflow
    async for event in runner.run_async(
        user_id="local_user",
        session_id=session.id,
        new_message=types.Content(
            role="user",
            parts=[types.Part.from_text(text=prompt)]
        ),
    ):
        # Print results as nodes finish
        if event.author:
            print(f"--- Node '{event.author}' complete ---")
        if event.output is not None:
            # Format outputs for readability
            if isinstance(event.output, dict) and "video_clips" in event.output:
                print("🎬 Generated Assets Manifest:")
                print(f"  - Total Videos: {len(event.output.get('video_clips', []))}")
                if event.output.get('video_clips'):
                    first_clip = event.output['video_clips'][0]
                    print(f"  - Scene 1 Video URL: {first_clip.get('video_url')}")
                    print(f"  - Scene 1 Status: {first_clip.get('status')}")
            else:
                import json
                print(json.dumps(event.output, indent=2))
            print()

if __name__ == "__main__":
    asyncio.run(run_main())
