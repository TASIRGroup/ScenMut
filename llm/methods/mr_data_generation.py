import json
from typing import Any, List

from langchain_core.messages import HumanMessage
from pydantic import BaseModel, Field

from .base_method import BaseMethod
from llm.prompts.mr_data_generation import MR_DATA_GENERATION_PROMPT


class MRDataVariantItem(BaseModel):
    value: str = Field(..., description="Mutation value")
    strategy: str = Field(..., description="equivalent_class | boundary | special_char | substring")


class MRDataGenerationOutput(BaseModel):
    variants: List[MRDataVariantItem] = Field(..., description="Semantically equivalent mutation value list")


class MRDataGenerationMethod(BaseMethod):
    """MR-Data input data generation (generation-side LLM)."""

    def _build_prompt(self, input_data: dict[str, Any], attempt: int) -> list:
        page_intent = input_data.get("page_intent", "")
        input_label = input_data.get("input_label", "")
        event_label = input_data.get("event_label", "Unknown operation event")
        current_value = input_data.get("current_value", "")
        field_type = input_data.get("field_type", "string")
        required_hint = input_data.get("required_hint", "Unknown")

        prompt_text = MR_DATA_GENERATION_PROMPT.format(
            page_intent=page_intent,
            input_label=input_label,
            event_label=event_label,
            current_value=current_value,
            field_type=field_type,
            required_hint=required_hint,
        )
        if attempt > 0:
            prompt_text += "\n\nNote: Please strictly output JSON, do not add any explanation."
        return [HumanMessage(content=prompt_text)]

    def _parse_output(self, output_text: str) -> MRDataGenerationOutput:
        return self._parse_json_to_model(
            self._extract_json(output_text),
            MRDataGenerationOutput,
        )
