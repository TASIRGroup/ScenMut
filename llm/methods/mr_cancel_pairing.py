from typing import Any, List

from langchain_core.messages import HumanMessage
from pydantic import BaseModel, Field

from .base_method import BaseMethod
from llm.prompts.mr_cancel_pairing import MR_CANCEL_PAIRING_PROMPT


class MRCancelPairItem(BaseModel):
    forward: str = Field(..., description="Forward event semantic label")
    inverse: str = Field(..., description="Inverse operation semantic label")
    rollback_feasible: bool = Field(..., description="Whether rollback is feasible")
    reason: str = Field(default="", description="Reason")


class MRCancelPairingOutput(BaseModel):
    pairs: List[MRCancelPairItem] = Field(default_factory=list, description="配对列表")


class MRCancelPairingMethod(BaseMethod):
    """MR-Cancel inverse operation pairing (generation-side LLM)."""

    def _build_prompt(self, input_data: dict[str, Any], attempt: int) -> list:
        prompt_text = MR_CANCEL_PAIRING_PROMPT.format(
            event_semantic_labels=input_data.get("event_semantic_labels", ""),
            state_data_entity_summaries=input_data.get("state_data_entity_summaries", ""),
            candidate_inverse_labels=input_data.get("candidate_inverse_labels", ""),
        )
        if attempt > 0:
            prompt_text += "\n\nNote: Please strictly output JSON, include the `pairs` array."
        return [HumanMessage(content=prompt_text)]

    def _parse_output(self, output_text: str) -> MRCancelPairingOutput:
        return self._parse_json_to_model(
            self._extract_json(output_text),
            MRCancelPairingOutput,
        )
