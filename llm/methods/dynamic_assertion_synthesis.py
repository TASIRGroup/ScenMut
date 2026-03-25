from typing import Any, Dict, List, Optional, Tuple

import json

from langchain_core.messages import HumanMessage
from pydantic import BaseModel, Field

from .base_method import BaseMethod
from llm.prompts.dynamic_assertion_synthesis import DYNAMIC_ASSERTION_SYNTHESIS_PROMPT


class AssertionItem(BaseModel):
    path_index: int = Field(..., description="State index in the path (index into the mutated path array)")
    type: str = Field(..., description="text | attribute | display")
    locator: dict = Field(default_factory=dict, description="Locator (resolved from field_key by the program)")
    field_key: Optional[str] = Field(
        default=None,
        description="Field identifier aligned with DataEntity.key; the LLM only outputs this field, which is mapped to a specific locator by the program.",
    )
    text: Optional[str] = None
    attribute: Optional[str] = None
    value: Optional[str] = None
    display: Optional[bool] = None
    validation_type: Optional[str] = None


class DynamicAssertionSynthesisOutput(BaseModel):
    assertions: List[AssertionItem] = Field(default_factory=list)


class _DynamicAssertionLLMItem(BaseModel):
    """Minimal LLM-side output: includes only `path_index`, `type`, `field_key`, and the assertion value; no `locator`/`xpath`."""

    path_index: int = Field(..., description="State index in the path (index into the mutated path array)")
    type: str = Field(..., description="text | attribute | display")
    field_key: str = Field(..., description="Key of the data_entity on the state")
    text: Optional[str] = None
    attribute: Optional[str] = None
    value: Optional[str] = None
    display: Optional[bool] = None
    validation_type: Optional[str] = None


class _DynamicAssertionLLMOutput(BaseModel):
    assertions: List[_DynamicAssertionLLMItem] = Field(default_factory=list)


class DynamicAssertionSynthesisMethod(BaseMethod):
    """Dynamic assertion synthesis: generate/update the assertion list based on mutation and verification-side expected values."""

    def _build_prompt(self, input_data: dict[str, Any], attempt: int) -> list:
        prompt_text = DYNAMIC_ASSERTION_SYNTHESIS_PROMPT.format(
            original_path_summary=input_data.get("original_path_summary", ""),
            mutated_path_summary=input_data.get("mutated_path_summary", ""),
            mutation_description=input_data.get("mutation_description", ""),
        )
        if attempt > 0:
            prompt_text += "\n\nNote: Please strictly output JSON, include the `assertions` array, and do not output any `xpath` / `locator` fields."
        return [HumanMessage(content=prompt_text)]

    def _parse_output(self, output_text: str) -> _DynamicAssertionLLMOutput:
        """Parse the raw LLM output into an intermediate result containing only `field_key`."""
        return self._parse_json_to_model(
            self._extract_json(output_text),
            _DynamicAssertionLLMOutput,
        )

    def run(
        self,
        ctx_dict: dict[str, Any],
        field_locator_index: Dict[Tuple[int, str], dict],
    ) -> DynamicAssertionSynthesisOutput:
        """
        Execute dynamic assertion synthesis:
        - Call the LLM to output `(path_index, field_key, type, value)` based on semantics.
        - Resolve `locator` on the program side from `graph`/`State.data_entities` using `(path_index, field_key)`,
          thereby fully avoiding the LLM fabricating `xpath`.
        """
        # Always inject the context as JSON text (shorter, clearer, and easier for the model to understand structurally).
        input_data = {
            "original_path_summary": json.dumps(
                ctx_dict.get("original_path_summary", ""),
                ensure_ascii=False,
                separators=(",", ":"),
            )
            if not isinstance(ctx_dict.get("original_path_summary", ""), str)
            else (ctx_dict.get("original_path_summary") or ""),
            "mutated_path_summary": json.dumps(
                ctx_dict.get("mutated_path_summary", ""),
                ensure_ascii=False,
                separators=(",", ":"),
            )
            if not isinstance(ctx_dict.get("mutated_path_summary", ""), str)
            else (ctx_dict.get("mutated_path_summary") or ""),
            "mutation_description": json.dumps(
                ctx_dict.get("mutation_description", ""),
                ensure_ascii=False,
                separators=(",", ":"),
            )
            if not isinstance(ctx_dict.get("mutation_description", ""), str)
            else (ctx_dict.get("mutation_description") or ""),
        }

        raw: _DynamicAssertionLLMOutput = self.invoke(input_data)  # type: ignore[assignment]

        assertions: List[AssertionItem] = []
        for item in raw.assertions:
            # Look up `locator` on the program side using only (`path_index`, `field_key`);
            # if not found, discard the assertion.
            if item.field_key is None or item.field_key == "":
                continue
            locator = field_locator_index.get((item.path_index, item.field_key), {})
            if locator == {}:
                continue
            assertions.append(
                AssertionItem(
                    path_index=item.path_index,
                    type=item.type,
                    field_key=item.field_key,
                    locator=locator or {},
                    text=item.text,
                    attribute=item.attribute,
                    value=item.value,
                    display=item.display,
                    validation_type=item.validation_type,
                )
            )

        return DynamicAssertionSynthesisOutput(assertions=assertions)
