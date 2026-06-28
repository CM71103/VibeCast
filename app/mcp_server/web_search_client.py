from __future__ import annotations

import logging
import os
import uuid

logger = logging.getLogger(__name__)


class WebSearchClientError(Exception):
    """Raised when web search fails."""


class WebSearchClient:
    """Web search client for grounding research with real data.

    In mock mode returns simulated results.
    In real mode uses the Google Custom Search API (or similar).
    """

    def __init__(self, mock_mode: bool | None = None):
        self.mock_mode = mock_mode if mock_mode is not None else (
            os.environ.get("VIBECAST_MOCK_MODE", "true").lower() == "true"
        )

    async def search(self, query: str, num_results: int = 5) -> list[dict]:
        if self.mock_mode:
            mock_id = uuid.uuid4().hex[:8]
            logger.info("Mock mode: web search for '%s'", query)
            return [
                {
                    "title": f"Result {i+1} about {query}",
                    "url": f"https://mock.vibecast.ai/search/{mock_id}/{i}",
                    "snippet": (
                        f"This is mock search result #{i+1} about '{query}'. "
                        "In mock mode, results are simulated. Set VIBECAST_MOCK_MODE=false "
                        "to use real web search with a configured API key."
                    ),
                }
                for i in range(num_results)
            ]

        try:
            import httpx

            api_key = os.environ.get("GOOGLE_CUSTOM_SEARCH_API_KEY", "")
            cx = os.environ.get("GOOGLE_CUSTOM_SEARCH_CX", "")
            if not api_key or not cx:
                raise WebSearchClientError(
                    "GOOGLE_CUSTOM_SEARCH_API_KEY and GOOGLE_CUSTOM_SEARCH_CX must be set"
                )

            url = "https://www.googleapis.com/customsearch/v1"
            params = {"key": api_key, "cx": cx, "q": query, "num": min(num_results, 10)}
            async with httpx.AsyncClient() as client:
                response = await client.get(url, params=params, timeout=15)
                response.raise_for_status()
                data = response.json()

            results = []
            for item in data.get("items", []):
                results.append({
                    "title": item.get("title", ""),
                    "url": item.get("link", ""),
                    "snippet": item.get("snippet", ""),
                })

            logger.info("Web search for '%s' returned %d results", query, len(results))
            return results

        except Exception as exc:
            raise WebSearchClientError(f"Web search failed: {exc}") from exc
