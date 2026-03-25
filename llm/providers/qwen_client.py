"""
Qwen client wrapper.

Based on LangChain's `ChatOpenAI` interface.
"""
import os
from dotenv import load_dotenv
from typing import Literal
from langchain_openai import ChatOpenAI

# Model configuration.
MODEL_CONFIGS = {
    "vision": {
        "model": "qwen3.5-flash-2026-02-23",  # Vision tasks
        "temperature": 0.2,
    },
    "gui_vision": {
        "model": "gui-plus",  # GUI-optimized vision tasks
        "temperature": 0.2,
    },
    "simple": {
        "model": "qwen-turbo-latest",  # Simple text tasks
        "temperature": 0.2,
    },
    "complex": {
        "model": "qwen-max-latest",  # Complex reasoning tasks
        "temperature": 0.7,
    },
    "latest": {
        "model": "qwen3.5-plus-2026-02-15",
        "temperature": 0.7
    }
}


class QwenClient:
    """Qwen client."""
    
    def __init__(self, api_key: str | None = None, base_url: str | None = None):
        """
        Initialize the client.
        
        Args:
            api_key: API key. If not provided, read from `DASHSCOPE_API_KEY`.
            base_url: API base URL. Defaults to the Qwen dashscope-compatible mode URL.
        """
        load_dotenv()
        self.api_key = api_key or os.getenv("DASHSCOPE_API_KEY") 
        if not self.api_key:
            raise ValueError("API key is required. Set DASHSCOPE_API_KEY environment variable or pass api_key parameter.")
        
        self.base_url = base_url or "https://dashscope.aliyuncs.com/compatible-mode/v1"
        self._llm_cache: dict[str, ChatOpenAI] = {}
    
    def get_llm(
        self,
        task_type: Literal["vision", "gui_vision", "simple", "complex", "latest"] = "complex",
        temperature: float | None = None,
        max_retries: int = 5,
    ) -> ChatOpenAI:
        """
        Get an LLM instance for the specified task type.
        
        Args:
            task_type: Task type; determines which model to use.
            temperature: Temperature parameter; uses the default if not specified.
            max_retries: Maximum retry count.
            
        Returns:
            A `ChatOpenAI` instance.
        """
        config = MODEL_CONFIGS.get(task_type, MODEL_CONFIGS["complex"])
        model_name = config["model"]
        temp = temperature if temperature is not None else config["temperature"]
        
        # Build cache key.
        cache_key = f"{task_type}_{model_name}_{temp}_{max_retries}"
        
        if cache_key not in self._llm_cache:
            self._llm_cache[cache_key] = ChatOpenAI(
                model=model_name,
                temperature=temp,
                openai_api_key=self.api_key,
                openai_api_base=self.base_url,
                max_retries=max_retries,
                streaming=False,  # Default to non-streaming for easier JSON parsing.
            )
        
        return self._llm_cache[cache_key]
    
    def clear_cache(self):
        """Clear the LLM cache."""
        self._llm_cache.clear()


# Global client instance (singleton mode).
_global_client: QwenClient | None = None


def get_qwen_client() -> QwenClient:
    """Get the global Qwen client instance."""
    global _global_client
    if _global_client is None:
        _global_client = QwenClient()
    return _global_client

def init_qwen_client(api_key: str | None = None, base_url: str | None = None):
    """
    Initialize the global client instance.
    
    Args:
        api_key: API key.
        base_url: API base URL.
    """
    global _global_client
    _global_client = QwenClient(api_key=api_key, base_url=base_url)