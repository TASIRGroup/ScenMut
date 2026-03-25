from typing import Any, List

from langchain_core.messages import HumanMessage
from pydantic import BaseModel, Field

from .base_method import BaseMethod
from llm.prompts.mr_state_semantic_planning import MR_STATE_SEMANTIC_PLANNING_PROMPT


class IntentStep(BaseModel):
    """A single step in the intent sequence, including a natural-language description and an edge identifier."""
    description: str = Field(default="", description="Natural language step description")
    edge_id: str = Field(default="", description="Edge identifier in the local subgraph, e.g. E1, E2")


class MRStateSemanticPlanningOutput(BaseModel):
    """LLM output: multiple intent sequences, each represented as a step list with `edge_id`s."""
    intent_sequences: List[List[IntentStep]] = Field(
        default_factory=list,
        description="3~10 intent sequences, each represented as an ordered list of IntentStep",
    )


class MRStateSemanticPlanningMethod(BaseMethod):
    """MR-State semantic planning: based on local candidate subgraph semantic summaries, generate multiple intent sequences in one call."""

    def _build_prompt(self, input_data: dict[str, Any], attempt: int) -> list:
        prompt_text = MR_STATE_SEMANTIC_PLANNING_PROMPT.format(
            intent_k=input_data.get("intent_k", ""),
            intent_k_plus_1=input_data.get("intent_k_plus_1", ""),
            edges_semantic_list=input_data.get("edges_semantic_list", ""),
        )
        if attempt > 0:
            prompt_text += "\n\nNote: Please strictly output JSON, `intent_sequences` is a 2D array, each step contains `description` and `edge_id` (consistent with the identifiers in the above edge list)."
        return [HumanMessage(content=prompt_text)]

    def _parse_output(self, output_text: str) -> MRStateSemanticPlanningOutput:
        return self._parse_json_to_model(
            self._extract_json(output_text),
            MRStateSemanticPlanningOutput,
        )
