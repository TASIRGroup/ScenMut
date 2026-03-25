from typing import Any, List

from langchain_core.messages import HumanMessage
from pydantic import BaseModel

from .base_method import BaseMethod
from llm.prompts.mr_cancel_rollback import MR_CANCEL_ROLLBACK_PROMPT


class MREffectItem(BaseModel):
    field_key: str
    path_index: int
    expected_value: str


class MRCancelRollbackOutput(BaseModel):
    """Verification-side output: effects = [{field_key, path_index, expected_value}, ...]."""
    effects: List[MREffectItem] = []


def _parse_side_effect_effects(output_text: str, extract_json_fn) -> List[MREffectItem]:
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


class MRCancelRollbackMethod(BaseMethod):
    """MR-Cancel rollback expected-value inference (verification-side LLM)."""

    def _build_prompt(self, input_data: dict[str, Any], attempt: int) -> list:
        prompt_text = MR_CANCEL_ROLLBACK_PROMPT.format(
            forward_event_label=input_data.get("forward_event_label", ""),
            inverse_event_label=input_data.get("inverse_event_label", ""),
            before_values=input_data.get("before_values", ""),
            after_forward_values=input_data.get("after_forward_values", ""),
            subsequent_states_data_entities=input_data.get("subsequent_states_data_entities", ""),
        )
        if attempt > 0:
            prompt_text += "\n\nNote: Please strictly output JSON."
        return [HumanMessage(content=prompt_text)]

    def _parse_output(self, output_text: str) -> BaseModel:
        effects = _parse_side_effect_effects(output_text, self._extract_json)
        return MRCancelRollbackOutput(effects=effects)
