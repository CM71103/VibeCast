"""Custom function tools for VibeCast agents.

These tools are plain function tools (not built-in tools) and therefore
compatible with ADK's function calling mechanism.
"""

from __future__ import annotations

import json
import logging

logger = logging.getLogger(__name__)

# Global search client (lazy initialized)
_search_client = None


def _get_search_client():
    global _search_client
    if _search_client is None:
        from app.mcp_server.web_search_client import WebSearchClient
        _search_client = WebSearchClient()
    return _search_client


async def web_search(query: str, num_results: int = 5) -> str:
    """Search the web for current information on a topic.

    Use this tool to find real, up-to-date facts, sources,
    and trending information. Returns a JSON string with
    title, url, and snippet for each result.

    Args:
        query: The search query string.
        num_results: Number of results to return (1-10, default 5).

    Returns:
        JSON string containing search results.
    """
    try:
        client = _get_search_client()
        results = await client.search(query, num_results=min(num_results, 10))
        return json.dumps(results, indent=2)
    except Exception as e:
        logger.error("Web search failed for query '%s': %s", query, e)
        return json.dumps([
            {
                "title": f"Information about {query}",
                "url": "",
                "snippet": f"Search results are currently unavailable: {e}",
            }
        ])
