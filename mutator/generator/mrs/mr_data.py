"""
MR-Data: semantically equivalent data mutation.

Identify `TextInputEvent` in the path, use the generation-side LLM to generate mutated
values, and construct mutation paths with consistent topology.

The verification-side LLM and dynamic assertions are invoked by the Generator after
obtaining `π_aug`.
"""
from typing import List, Optional, Dict, Any

from transition_graph import GraphManager, ScriptPath, PathNode, StateNode
from transition_graph.events.event import TextInputEvent
from transition_graph.utils.mock_strategy import MockStrategy
from transition_graph.utils.binding_utils import get_input_event_data_entity_binding

from .mr import MetamorphicRelation
from .utils import clone_script_path


class MRData(MetamorphicRelation):
    """Semantic-equivalent data mutation: generate equivalent-class/boundary mutations for each `TextInputEvent` while keeping the topology unchanged."""

    def __init__(self, graph_mgr: GraphManager, config: Optional[dict] = None):
        super().__init__(
            name="MRData",
            description="Semantic equivalent data mutation for text inputs",
            mr_type="MRData",
            graph_mgr=graph_mgr,
        )
        self.config = config or {}
        self._llm = None

    def _get_llm(self):
        if self._llm is None:
            from llm.providers import get_qwen_client
            cfg = self.config.get("mutation", {}).get("llm", {})
            model_type = cfg.get("generation_model") or "simple"
            temp = cfg.get("temperature")
            client = get_qwen_client()
            self._llm = client.get_llm(model_type, temperature=temp)
        return self._llm

    def apply(self, original: ScriptPath) -> List[ScriptPath]:
        from llm.methods import MRDataGenerationMethod

        variants_paths: List[ScriptPath] = []
        path_arr = original.to_array()
        bindings = get_input_event_data_entity_binding(original, self.graph_mgr)

        for path_index, path_node, event, data_entity in bindings:
            if not isinstance(event, TextInputEvent):
                continue
            state = path_node.state
            if not isinstance(state, StateNode):
                continue
            page = getattr(state, "parent_page_node", None)
            page_intent = getattr(page, "semantic_label", "") if page else ""
            input_label = getattr(data_entity, "key", "input") if data_entity else "input"
            event_label = getattr(event, "semantic_label", "")
            current_value = getattr(event, "text", "") or ""
            if current_value is None:
                current_value = ""
            field_type = getattr(data_entity, "type", "input") if data_entity else "input"
            required_hint = "Yes"  # Default: treat as required to avoid generating empty values.

            try:
                app_name = (self.config.get("appium") or {}).get("appPackage")
                method = MRDataGenerationMethod(self._get_llm(), app_name=app_name)
                out = method.invoke({
                    "page_intent": page_intent,
                    "input_label": input_label,
                    "event_label": event_label,
                    "current_value": current_value,
                    "field_type": field_type,
                    "required_hint": required_hint,
                })
            except Exception as e:
                print(f"MRData generation LLM failed for path_index={path_index}: {e}")
                continue

            variants = getattr(out, "variants", []) or []
            for v in variants:
                val = getattr(v, "value", None)
                if val is None or (isinstance(val, str) and not val.strip()):
                    continue
                # Clone the path and replace the event at this node.
                cloned = clone_script_path(original)
                arr = cloned.to_array()
                if path_index >= len(arr):
                    continue
                node = arr[path_index]
                if not isinstance(node, PathNode) or node.event is None:
                    continue
                old_ev = node.event
                mock = getattr(old_ev, "mock_strategy", None)
                if mock is not None and hasattr(mock, "to_dict"):
                    mock = MockStrategy.from_dict(mock.to_dict())
                else:
                    mock = MockStrategy("letter", 3)
                new_event = TextInputEvent(
                    state,
                    getattr(old_ev, "xpath", ""),
                    mock,
                    text=str(val),
                )
                new_event.semantic_label = getattr(old_ev, "semantic_label", "")
                new_event.has_data_side_effect = getattr(old_ev, "has_data_side_effect", False)
                arr[path_index] = PathNode(node.state, new_event, getattr(node, "oracles", None) or [])
                new_path = ScriptPath(path_array=arr)
                new_path_name = f"{original.path_name}__MRData__{len(variants_paths)}"
                new_path.set_path_name(new_path_name)
                new_path.set_mutation_description({
                    "page_intent": page_intent,
                    "mutation_state_event": getattr(old_ev, "semantic_label", "") or getattr(old_ev, "xpath", "") or f"path_index={path_index}",
                    "input_label": input_label,
                    "original_value": getattr(old_ev, "text", None) or "",
                    "new_value": val,
                    "mutated_state_path_indices": [path_index],
                    "subsequent_states_data_entities": [
                        {
                            "mutated_state_id": n.state.id,
                            "path_index": idx,
                            "state_intent": (getattr(n.state.parent_page_node, "semantic_label", "") if isinstance(n.state, StateNode) and n.state.parent_page_node else "") or getattr(n.state, "name", ""),
                            "data_entities": [
                                {
                                    "key": getattr(e, "key", ""),
                                    "type": getattr(e, "type", ""),
                                    "value": getattr(e, "value", "")
                                }
                                for e in (getattr(n.state, "data_entities", []) or [])
                            ],
                        }
                        for idx, n in enumerate(arr[path_index + 1 :], start=path_index + 1)
                        if isinstance(n, PathNode) and isinstance(n.state, StateNode)
                    ],
                })
                variants_paths.append(new_path)

        return variants_paths

    def get_mutation_description(
        self, original: ScriptPath, path: ScriptPath
    ) -> Dict[str, Any]:
        """
        Provide the MR-Data mutation description for the verification-side LLM and dynamic assertions.

        Downstream fields: `page_intent`, `mutation_state_event`, `input_label`, `original_value`, `new_value`,
        `subsequent_states_data_entities`.
        """
        return path.mutation_description
