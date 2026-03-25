import json
import logging
import time
from typing import Any, TypeVar, Type, Optional
from abc import ABC, abstractmethod
from pydantic import BaseModel, ValidationError
from langchain_core.messages import HumanMessage, SystemMessage
from langchain_openai import ChatOpenAI

T = TypeVar('T', bound=BaseModel)

def _messages_to_text(messages) -> str:
    """Serialize a list of messages into text for statistics and logging."""
    parts = []
    for m in messages:
        role = getattr(m, "type", type(m).__name__)
        content = getattr(m, "content", str(m))
        parts.append(f"[{role}]\n{content}")
    return "\n\n".join(parts)

class BaseMethod(ABC):
    """Base class for model methods (encapsulated LLM calls)."""
    
    def __init__(
        self,
        llm: ChatOpenAI,
        max_retries: int = 3,
        debug: bool = False,
        app_name: Optional[str] = None,
    ):
        """
        Initialize the encapsulated model method.
        
        Args:
            llm: LangChain LLM instance.
            max_retries: Maximum retry count.
            app_name: App package name (or similar identifier) written into call statistics.
        """
        self.llm = llm
        self.max_retries = max_retries
        self.debug = debug
        self._app_name = app_name
    
    def invoke(self, input_data: dict[str, Any]) -> BaseModel:
        """
        Invoke the encapsulated model method, run inference, and return structured output.
        
        Args:
            input_data: Input data dictionary.
            
        Returns:
            Parsed output object (a Pydantic model).
            
        Raises:
            RuntimeError: If retries are exhausted and a valid output is still not obtained.
        """
        for attempt in range(self.max_retries):
            start_time = time.time()
            input_tokens, output_tokens, cost, success = 0, 0, 0.0, False
            input_text, output_text = "", ""
            model_name = getattr(self.llm, "model_name", None) or "unknown"
            try:
                # Build prompt messages.
                messages = self._build_prompt(input_data, attempt)
                input_text = _messages_to_text(messages)
                if self.debug:
                    print("-" * 20)
                    print(f"Method {self.__class__.__name__} attempt {attempt + 1}/{self.max_retries}")
                    print(f"Prompt: {messages}")
                
                # Call the LLM.
                response = self.llm.invoke(messages)
                
                # Extract text content.
                output_text = response.content
                if self.debug:
                    print(f"LLM raw output: {output_text}")
                    print("-" * 20)
                
                # Parse the output.
                parsed_output = self._parse_output(output_text)
                
                print(f"Method {self.__class__.__name__} succeeded on attempt {attempt + 1}")
                return parsed_output
                
            except (json.JSONDecodeError, ValidationError) as e:
                print(f"Method {self.__class__.__name__} parsing failed on attempt {attempt + 1}: {e}")
                if attempt == self.max_retries - 1:
                    print(f"Method {self.__class__.__name__} failed after {self.max_retries} attempts")
                    raise RuntimeError(
                        f"Method {self.__class__.__name__} failed to produce valid output after {self.max_retries} attempts. "
                        f"Last error: {e}"
                    )
                # Retries add an error hint inside `_build_prompt`.
                continue
            except Exception as e:
                print(f"Method {self.__class__.__name__} unexpected error: {e}")
                raise
    
    @abstractmethod
    def _build_prompt(self, input_data: dict[str, Any], attempt: int) -> list[HumanMessage | SystemMessage]:
        """
        Build prompt messages.
        
        Args:
            input_data: Input data.
            attempt: Current attempt count (starting from 0).
            
        Returns:
            A list of messages.
        """
        pass
    
    @abstractmethod
    def _parse_output(self, output_text: str) -> BaseModel:
        """
        Parse LLM output text into a structured object.
        
        Args:
            output_text: LLM output text.
            
        Returns:
            A Pydantic model instance.
            
        Raises:
            json.JSONDecodeError: JSON parsing failed.
            ValidationError: Schema validation failed.
        """
        pass
    
    def _extract_json(self, text: str) -> str:
        """
        Extract JSON from text (handling possible markdown code fences, etc.).
        
        Args:
            text: Text containing JSON.
            
        Returns:
            A pure JSON string.
        """
        text = text.strip()
        
        # Remove possible markdown code fence markers.
        if text.startswith("```json"):
            text = text[7:]
        elif text.startswith("```"):
            text = text[3:]
        
        if text.endswith("```"):
            text = text[:-3]
        
        text = text.strip()
        
        # Try to find the first `{` and the last `}`.
        start = text.find('{')
        end = text.rfind('}')
        
        if start != -1 and end != -1 and start < end:
            return text[start:end+1]
        
        return text
    
    def _parse_json_to_model(self, json_str: str, model_class: Type[T]) -> T:
        """
        Parse a JSON string into a Pydantic model.
        
        Args:
            json_str: JSON string.
            model_class: Pydantic model class.
            
        Returns:
            Model instance.
        """
        # Extract pure JSON.
        clean_json = self._extract_json(json_str)
        
        # Parse JSON.
        data = json.loads(clean_json)
        
        # Validate and create the model.
        return model_class.model_validate(data)
