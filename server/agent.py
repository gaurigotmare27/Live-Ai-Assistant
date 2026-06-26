import os
import sys
from pathlib import Path
import yaml
from typing import Dict, Any, List
from google import genai
from google.genai import types
from sqlalchemy.orm import Session
from dotenv import load_dotenv

# Load environment variables from the root .env file relative to this file
env_path = Path(__file__).resolve().parent.parent / '.env'
load_dotenv(dotenv_path=env_path)

from server.memory import get_session_history, save_message
from server.tools import get_agent_tools, web_search

# Load agent configuration
CONFIG_PATH = os.path.join(os.path.dirname(__file__), "..", "config", "agent_config.yaml")

def load_config() -> Dict[str, Any]:
    """Helper to load config from the YAML file."""
    try:
        with open(CONFIG_PATH, "r") as f:
            return yaml.safe_load(f) or {}
    except Exception:
        return {}

class LiveAIAgent:
    """Agent orchestrator utilizing Google GenAI SDK to interact with Gemini."""
    
    def __init__(self):
        self.config = load_config()
        self.agent_cfg = self.config.get("agent", {})
        self.model_name = self.agent_cfg.get("model", "gemini-3.1-flash-lite")
        self.system_instruction = self.agent_cfg.get(
            "system_instruction", 
            "You are a helpful assistant."
        )
        
        # Initialize Google GenAI Client
        # Explicitly pass GEMINI_API_KEY to ensure the correct key is used
        gemini_key = os.getenv("GEMINI_API_KEY")
        if not gemini_key:
            # Fallback for testing environments where the API client is mocked
            is_testing = 'unittest' in sys.modules or 'pytest' in sys.modules
            if not is_testing:
                raise ValueError(
                    "GEMINI_API_KEY environment variable is not set or is empty. "
                    "Please ensure it is defined in your .env file at the project root."
                )
            gemini_key = "dummy_key_for_testing"
            
        # Clean up GOOGLE_API_KEY if present in environment to prevent SDK credentials collisions
        if "GOOGLE_API_KEY" in os.environ:
            del os.environ["GOOGLE_API_KEY"]
            
        self.client = genai.Client(api_key=gemini_key)
        
    def _prepare_history(self, db_history: List[Any]) -> List[types.Content]:
        """Convert stored ChatMessage database records into Gemini SDK Content objects."""
        contents = []
        for msg in db_history:
            role = "user" if msg.role == "user" else "model"
            contents.append(
                types.Content(
                    role=role,
                    parts=[types.Part.from_text(text=msg.content)]
                )
            )
        return contents

    def run(self, session_id: str, user_input: str, db: Session) -> str:
        """
        Executes the main agent loop:
        1. Saves user input to persistent memory.
        2. Retrieves past session history from database.
        3. Configures Gemini call with custom system instructions, chat history, and tools.
        4. Invokes the model (handling any automatic tool calling).
        5. Saves model response to memory and returns it.
        """
        # 1. Save user input to database
        save_message(db, session_id, role="user", content=user_input)
        
        # 2. Get history
        history_limit = self.config.get("memory", {}).get("recent_history_limit", 10)
        db_history = get_session_history(db, session_id, limit=history_limit)
        
        # Convert history for Gemini
        gemini_history = self._prepare_history(db_history[:-1]) # exclude the user_input we just added
        
        # 3. Setup tools
        tools_list = []
        if self.config.get("tools", {}).get("web_search", {}).get("enabled", False) or \
           self.config.get("tools", {}).get("custom_actions", {}).get("enabled", False):
            tools_list = get_agent_tools()
            
        # Define generation config
        config = types.GenerateContentConfig(
            system_instruction=self.system_instruction,
            temperature=self.agent_cfg.get("temperature", 0.2),
            max_output_tokens=self.agent_cfg.get("max_output_tokens", 2048),
            tools=tools_list,
        )
        
        # 4. Invoke model using the chat session or direct generate_content
        # Note: Under genai client, automatic tool calling is supported for direct python functions in tools list
        chat = self.client.chats.create(
            model=self.model_name,
            history=gemini_history,
            config=config
        )
        
        response = chat.send_message(user_input)
        response_text = response.text or ""
        
        # 5. Save response to memory
        save_message(db, session_id, role="model", content=response_text)
        
        return response_text
