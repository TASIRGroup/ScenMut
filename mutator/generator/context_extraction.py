"""
Context extraction.

Provides a unified structured context for dynamic assertion generation and
the verification-side LLM.

Input: original path, mutated path, mutation type, and mutation description.
Output: a JSON/string-serializable context used by the LLMs to synthesize
assertions.
"""
from typing import List, Dict, Any, Optional
from dataclasses import dataclass, field

from transition_graph import ScriptPath, PathNode, StateNode, InternalStateNode
from transition_graph.manager.graph_manager import GraphManager
from transition_graph.utils.binding_utils import get_input_event_data_entity_binding
from mutator.generator.mrs.utils import (
    extract_page_sequence,
    extract_state_sequence
)


# Mutation types.
MUTATION_TYPE_DATA = "MR-Data"
MUTATION_TYPE_STATE = "MR-State"
MUTATION_TYPE_CANCEL = "MR-Cancel"


@dataclass
class ContextExtractionResult:
    """The context extraction result; serializable to `dict` for LLM usage."""
    original_page_sequence: List[str] = field(default_factory=list)  # semantic_label
    original_state_intents: List[Dict[str, Any]] = field(default_factory=list)
    original_assertions: List[Dict[str, Any]] = field(default_factory=list)
    mutation_type: str = ""
    mutation_description: Dict[str, Any] = field(default_factory=dict)
    affected_state_summaries: List[Dict[str, Any]] = field(default_factory=list)
    input_event_bindings: List[Dict[str, Any]] = field(default_factory=list)  # Only MR-Data.
    # Verification-side LLM output (includes `path_index`):
    # [{field_key, path_index, expected_value}, ...]
    verification_llm_expected_values: Optional[List[Dict[str, Any]]] = None  # Filled in by the caller after verification-side LLM

    def to_dict(self) -> dict:
        return {
            "original_page_sequence": self.original_page_sequence,
            "original_state_intents": self.original_state_intents,
            "original_assertions": self.original_assertions,
            "mutation_type": self.mutation_type,
            "mutation_description": self.mutation_description,
            "affected_state_summaries": self.affected_state_summaries,
            "input_event_bindings": self.input_event_bindings,
            "verification_llm_expected_values": self.verification_llm_expected_values,
        }


def _state_intent_summary(state) -> Dict[str, Any]:
    """Summarize a single state's intent and its data entities."""
    if isinstance(state, InternalStateNode):
        return {"type": "internal", "id": state.id}
    if not isinstance(state, StateNode):
        return {}
    page = getattr(state, "parent_page_node", None)
    intent = getattr(page, "semantic_label", "") if page else ""
    entities = []
    for de in getattr(state, "data_entities", []) or []:
        entities.append({
            "key": getattr(de, "key", ""),
            "type": getattr(de, "type", ""),
            "value": getattr(de, "value", ""),
        })
    return {
        "type": "state",
        "id": state.id,
        "intent": intent,
        "data_entities": entities,
    }


def _oracle_summary(oracles) -> List[Dict[str, Any]]:
    """Convert an oracle list into a serializable summary."""
    if not oracles:
        return []
    out = []
    for o in oracles:
        d = o.to_dict() if hasattr(o, "to_dict") else {}
        out.append(d)
    return out


def extract_context(
    pi_orig: ScriptPath,
    pi_aug: ScriptPath,
    mutation_type: str,
    mutation_description: Dict[str, Any],
    graph_mgr: Optional[GraphManager] = None,
    include_bindings_for_data: bool = True,
) -> ContextExtractionResult:
    """
    Extract context from the original path and mutated path for the
    verification-side LLM and dynamic assertion synthesis.

    Args:
        pi_orig: Original path.
        pi_aug: Mutated path.
        mutation_type: One of `MUTATION_TYPE_DATA` / `MUTATION_TYPE_STATE` / `MUTATION_TYPE_CANCEL`.
        mutation_description: Mutation description (e.g., `v->v'`, injected page sequence, inverse-op equivalents, etc.).
        graph_mgr: Graph manager (optional, for extensibility).
        include_bindings_for_data: Whether to include input event bindings (only needed for MR-Data).

    Returns:
        `ContextExtractionResult`, including:
        original semantic page sequence, state intents, existing assertions,
        mutation info, affected state summaries, and optionally variable bindings.
    """
    # Original path: semantic page sequence.
    pages = extract_page_sequence(pi_orig)
    original_page_sequence = [
        getattr(p, "semantic_label", "") or getattr(p, "name", "") for p in pages
    ]

    # Original path: state intents and `data_entities`.
    states_orig = extract_state_sequence(pi_orig)
    original_state_intents = [_state_intent_summary(s) for s in states_orig]

    # Original path: existing assertions (collect from `PathNode.oracles`).
    original_assertions = []
    arr_orig = pi_orig.to_array()
    for i, node in enumerate(arr_orig):
        if isinstance(node, PathNode) and getattr(node, "oracles", None):
            for o in node.oracles:
                original_assertions.append({
                    "path_index": i,
                    "state_id": node.state.id,
                    "oracle": o.to_dict() if hasattr(o, "to_dict") else {},
                })

    # Affected states: states in `pi_aug` that have assertions or contain
    # `output` / `input_output` data entities.
    affected_state_summaries = []
    arr_aug = pi_aug.to_array()
    for i, node in enumerate(arr_aug):
        if not isinstance(node, PathNode):
            continue
        state = node.state
        if isinstance(state, InternalStateNode):
            continue
        has_oracles = bool(getattr(node, "oracles", None))
        entities = getattr(state, "data_entities", []) or []
        has_output = any(getattr(e, "type", "") in ("output", "input_output") for e in entities)
        if has_oracles or has_output:
            summary = _state_intent_summary(state)
            summary["path_index"] = i
            summary["oracles"] = _oracle_summary(getattr(node, "oracles", None) or [])
            affected_state_summaries.append(summary)

    # Variable bindings: only for MR-Data.
    input_event_bindings = []
    if include_bindings_for_data and mutation_type == MUTATION_TYPE_DATA:
        bindings = get_input_event_data_entity_binding(pi_aug, graph_mgr)
        for idx, pn, evt, entity in bindings:
            input_event_bindings.append({
                "path_index": idx,
                "event_xpath": getattr(evt, "xpath", ""),
                "event_text": getattr(evt, "text", ""),
                "data_entity_key": getattr(entity, "key", "") if entity else None,
                "data_entity_type": getattr(entity, "type", "") if entity else None,
            })

    return ContextExtractionResult(
        original_page_sequence=original_page_sequence,
        original_state_intents=original_state_intents,
        original_assertions=original_assertions,
        mutation_type=mutation_type,
        mutation_description=mutation_description,
        affected_state_summaries=affected_state_summaries,
        input_event_bindings=input_event_bindings,
    )