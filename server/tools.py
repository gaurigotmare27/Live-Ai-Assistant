import os
import requests
from typing import Dict, Any, List
from pathlib import Path
from dotenv import load_dotenv

# Load environment variables from the root .env file relative to this file
env_path = Path(__file__).resolve().parent.parent / '.env'
load_dotenv(dotenv_path=env_path)

def web_search(query: str, max_results: int = 5) -> Dict[str, Any]:
    """
    Search the web for a given query and return a structured dictionary of results.
    Supports Tavily search API as default, with a fallback custom search structure.
    
    Returns:
        Dict[str, Any]: A dictionary containing a "results" list of search items
                        and a "success" boolean or error/warning details.
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
                return {
                    "results": [
                        {"title": r.get("title"), "url": r.get("url"), "content": r.get("content")}
                        for r in results
                    ],
                    "success": True
                }
        except Exception as e:
            return {"results": [], "success": False, "error": f"Tavily search failed: {str(e)}"}
            
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
                return {
                    "results": [
                        {"title": item.get("title"), "url": item.get("link"), "content": item.get("snippet")}
                        for item in items
                    ],
                    "success": True
                }
        except Exception as e:
            return {"results": [], "success": False, "error": f"Google CSE failed: {str(e)}"}

    # Stub response if no keys are set
    return {
        "results": [{
            "title": "Local Mock Search Result",
            "url": "https://example.com/mock",
            "content": f"Mock result for query: '{query}'. Set TAVILY_API_KEY or GOOGLE_SEARCH_API_KEY in .env to search the web live."
        }],
        "success": True,
        "warning": "Using local mock search result because live APIs are not fully configured."
    }

def list_workspace_files() -> List[str]:
    """
    List all relevant files in the workspace (excluding binary, vendor, and cache directories).
    Returns a list of relative file paths.
    """
    base_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
    ignored_dirs = {".git", ".venv", "__pycache__", "venv"}
    ignored_files = {"live_assistant.db", ".env"}
    
    file_list = []
    for root, dirs, files in os.walk(base_dir):
        # Modify dirs in-place to avoid walking down ignored directories
        dirs[:] = [d for d in dirs if d not in ignored_dirs]
        for file in files:
            if file in ignored_files:
                continue
            abs_path = os.path.join(root, file)
            rel_path = os.path.relpath(abs_path, base_dir)
            file_list.append(rel_path.replace("\\", "/"))
            
    return file_list

def read_workspace_file(filepath: str) -> str:
    """
    Read the content of a file from the workspace.
    Args:
        filepath: Relative path of the file to read (e.g. 'server/main.py').
    Returns:
        The text content of the file or an error message.
    """
    base_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
    target_path = os.path.abspath(os.path.join(base_dir, filepath))
    
    if not target_path.startswith(base_dir):
        return "Error: Cannot read files outside the workspace root."
        
    if not os.path.exists(target_path):
        return f"Error: File '{filepath}' does not exist."
        
    if not os.path.isfile(target_path):
        return f"Error: Path '{filepath}' is not a file."
        
    try:
        with open(target_path, "r", encoding="utf-8", errors="replace") as f:
            return f.read()
    except Exception as e:
        return f"Error: Failed to read file '{filepath}': {str(e)}"

def search_workspace_code(query: str) -> List[Dict[str, Any]]:
    """
    Perform a case-insensitive search for a query string in workspace text files.
    Args:
        query: The search term to locate.
    Returns:
        List of dicts, each with 'file', 'line', and 'content'.
    """
    base_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
    files = list_workspace_files()
    matches = []
    
    for filepath in files:
        target_path = os.path.join(base_dir, filepath)
        try:
            with open(target_path, "r", encoding="utf-8", errors="ignore") as f:
                for i, line in enumerate(f, 1):
                    if query.lower() in line.lower():
                        matches.append({
                            "file": filepath,
                            "line": i,
                            "content": line.strip()
                        })
                        if len(matches) >= 50:  # Cap at 50 results
                            return matches
        except Exception:
            continue
            
    return matches

def write_workspace_file(filepath: str, content: str) -> str:
    """
    Create or overwrite a file in the workspace with new text content.
    Args:
        filepath: Relative path of the file to write (e.g. 'tests/new_test.py').
        content: The text content to write.
    Returns:
        A status message indicating success or failure.
    """
    base_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
    target_path = os.path.abspath(os.path.join(base_dir, filepath))
    
    if not target_path.startswith(base_dir):
        return "Error: Cannot write files outside the workspace root."
        
    # Security exclusions
    sensitive_files = {".env", "requirements.txt", "live_assistant.db"}
    filename = os.path.basename(target_path)
    
    if filename in sensitive_files:
        return f"Error: Modifying '{filename}' is restricted for safety reasons."
        
    if any(ignored in target_path for ignored in [".git", ".venv", "venv", "__pycache__"]):
        return "Error: Cannot write to hidden configuration or environment folders."
        
    try:
        os.makedirs(os.path.dirname(target_path), exist_ok=True)
        with open(target_path, "w", encoding="utf-8") as f:
            f.write(content)
        return f"Success: File '{filepath}' written successfully ({len(content)} characters)."
    except Exception as e:
        return f"Error: Failed to write file '{filepath}': {str(e)}"

def get_agent_tools() -> list:
    """Return a list of tool functions callable by the Gemini API SDK."""
    return [
        web_search,
        list_workspace_files,
        read_workspace_file,
        search_workspace_code,
        write_workspace_file
    ]
