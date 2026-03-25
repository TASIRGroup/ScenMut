from typing import Any, List

from langchain_core.messages import HumanMessage
from pydantic import BaseModel

from .base_method import BaseMethod
from llm.prompts.mr_data_side_effect import MR_DATA_SIDE_EFFECT_PROMPT


class MREffectItem(BaseModel):
    field_key: str
    path_index: int
    expected_value: str


class MRDataSideEffectOutput(BaseModel):
    """Verification-side output: effects = [{field_key, path_index, expected_value}, ...]."""
    effects: list[MREffectItem] = []


def _parse_side_effect_effects(output_text: str, extract_json_fn) -> List[MREffectItem]:
    """Parse into an `effects` list (supports a strict prompt structure)."""
    import json
    clean = extract_json_fn(output_text)
    data = json.loads(clean)
    if not isinstance(data, dict):
        return []
    raw_effects = data.get("effects", []) or []
    if not isinstance(raw_effects, list):
        return []
    effects: List[MREffectItem] = []
    for e in raw_effects:
        if not isinstance(e, dict):
            continue
        field_key = e.get("field_key")
        path_index = e.get("path_index")
        expected_value = e.get("expected_value")
        if field_key is None or expected_value is None or path_index is None:
            continue
        try:
            effects.append(
                MREffectItem(
                    field_key=str(field_key),
                    path_index=int(path_index),
                    expected_value=str(expected_value),
                )
            )
        except Exception:
            continue
    return effects


class MRDataSideEffectMethod(BaseMethod):
    """MR-Data data side-effect inference (verification-side LLM)."""

    def _build_prompt(self, input_data: dict[str, Any], attempt: int) -> list:
        prompt_text = MR_DATA_SIDE_EFFECT_PROMPT.format(
            page_intent=input_data.get("page_intent", ""),
            mutation_state_event=input_data.get("mutation_state_event", ""),
            input_label=input_data.get("input_label", ""),
            original_value=input_data.get("original_value", ""),
            new_value=input_data.get("new_value", ""),
            subsequent_states_data_entities=input_data.get("subsequent_states_data_entities", ""),
        )
        if attempt > 0:
            prompt_text += "\n\nNote: Please strictly output JSON, do not add any explanation."
        return [HumanMessage(content=prompt_text)]

    def _parse_output(self, output_text: str) -> BaseModel:
        effects = _parse_side_effect_effects(output_text, self._extract_json)
        return MRDataSideEffectOutput(effects=effects)
