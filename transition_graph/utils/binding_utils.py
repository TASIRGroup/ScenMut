"""
Utilities for binding text input events to data entities.

Used by MR-Data and dynamic assertion generation to determine which
`DataEntity` each `TextInputEvent` in a path is bound to, so the
verification-side LLM and dynamic assertions know "who was changed".
"""
from typing import List, Tuple, Optional

from transition_graph import ScriptPath, PathNode, StateNode
from transition_graph.events.event import TextInputEvent
from transition_graph.data.data_entity import DataEntity
from transition_graph.manager.graph_manager import GraphManager


def _locator_value_match(event_xpath: str, entity_locator: dict) -> bool:
    """Check whether an event xpath matches a DataEntity locator value."""
    if not event_xpath or not entity_locator:
        return False
    val = entity_locator.get("value")
    if isinstance(val, str) and val.strip():
        return event_xpath.strip() == val.strip()
    return False


def get_input_event_data_entity_binding(
    path: ScriptPath,
    graph_mgr: Optional[GraphManager] = None,
) -> List[Tuple[int, PathNode, TextInputEvent, Optional[DataEntity]]]:
    """
    For each `TextInputEvent` in the path, resolve which `DataEntity` it is bound to.

    Args:
        path: Script path.
        graph_mgr: Graph manager (currently not used for extra queries; kept for API consistency).

    Returns:
        List of `(path_node_index, path_node, text_input_event, data_entity_or_None)`.
        If an exact match cannot be found, `data_entity` may be `None`.
        If a heuristic fallback exists, it returns the unique entity.
    """
    result: List[Tuple[int, PathNode, TextInputEvent, Optional[DataEntity]]] = []
    arr = path.to_array()

    for idx, node in enumerate(arr):
        if not isinstance(node, PathNode) or node.event is None:
            continue
        event = node.event
        if getattr(event, "type", None) != "text_input" or not isinstance(event, TextInputEvent):
            continue
        state = node.state
        if not isinstance(state, StateNode):
            continue

        # Consider only entities of type `input` / `input_output`.
        input_entities = [
            e for e in (getattr(state, "data_entities", None) or [])
            if getattr(e, "type", "") in ("input", "input_output")
        ]

        bound_entity: Optional[DataEntity] = None
        event_xpath = getattr(event, "xpath", "") or ""

        for entity in input_entities:
            loc = getattr(entity, "locator", None) or {}
            if _locator_value_match(event_xpath, loc):
                bound_entity = entity
                break

        # Heuristic fallback: same state, same page, and only one input entity.
        if bound_entity is None and len(input_entities) == 1:
            bound_entity = input_entities[0]

        result.append((idx, node, event, bound_entity))

    return result
