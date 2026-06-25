import os
import requests
from typing import Dict, Any, List

def web_search(query: str, max_results: int = 5) -> List[Dict[str, Any]]:
    """
    Search the web for a given query.
    Supports Tavily search API as default, with a fallback custom search structure.
    """
    tavily_key = os.getenv("TAVILY_API_KEY")
    if tavily_key:
        try:
            url = "https://api.tavily.com/search"
            payload = {
                "api_key": tavily_key,
                "query": query,
                "max_results": max_results,
                "search_depth": "advanced",
                "include_answer": True
            }
            response = requests.post(url, json=payload, timeout=10)
            if response.status_code == 200:
                results = response.json().get("results", [])
                return [
                    {"title": r.get("title"), "url": r.get("url"), "content": r.get("content")}
                    for r in results
                ]
        except Exception as e:
            # Fallback on exception
            return [{"error": f"Tavily search failed: {str(e)}"}]
            
    # Placeholder for standard Google Search API / Custom Search Engine ID
    google_key = os.getenv("GOOGLE_SEARCH_API_KEY") or os.getenv("GOOGLE_API_KEY")
    google_cse = os.getenv("GOOGLE_CSE_ID")
    if google_key and google_cse:
        try:
            url = "https://www.googleapis.com/customsearch/v1"
            params = {
                "key": google_key,
                "cx": google_cse,
                "q": query,
                "num": max_results
            }
            response = requests.get(url, params=params, timeout=10)
            if response.status_code == 200:
                items = response.json().get("items", [])
                return [
                    {"title": item.get("title"), "url": item.get("link"), "content": item.get("snippet")}
                    for item in items
                ]
        except Exception as e:
            return [{"error": f"Google CSE failed: {str(e)}"}]

    # Stub response if no keys are set
    return [{
        "title": "Local Mock Search Result",
        "url": "https://example.com/mock",
        "content": f"Mock result for query: '{query}'. Set TAVILY_API_KEY or GOOGLE_SEARCH_API_KEY in .env to search the web live."
    }]

def get_agent_tools() -> list:
    """Return a list of tool functions callable by the Gemini API SDK."""
    return [web_search]
