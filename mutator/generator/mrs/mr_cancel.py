"""
MR-Cancel: close the data loop by injecting inverse operations.

Identify data-modification actions in the path, use the generation-side LLM to match the inverse operation,
and inject an inverse-operation sequence after the original operation.

The verification-side LLM and dynamic assertions are invoked uniformly by the Generator.
"""
from typing import List, Optional, Dict, Any

from transition_graph import GraphManager, ScriptPath, StateNode, InternalStateNode
from transition_graph import PathNode
from .mr import MetamorphicRelation
from .utils import (
    extract_state_sequence,
    extract_event_sequence,
    find_all_paths_between_states,
    get_transition_event,
    build_script_path_from_states,
    concatenate_path_segments,
    clone_path_segment,
    PathSearchConfig,
)


class MRCancel(MetamorphicRelation):
    """Inject a semantic inverse operation after a data-modification operation to roll back the data."""

    def __init__(self, graph_mgr: GraphManager, config: Optional[dict] = None):
        super().__init__(
            name="MRCancel",
            description="Inverse operation injection for data rollback",
            mr_type="MRCancel",
            graph_mgr=graph_mgr,
        )
        self.config = config or {}
        self._llm = None

    def _get_llm(self):
        if self._llm is None:
            from llm.providers import get_qwen_client
            cfg = self.config.get("mutation", {}).get("llm", {})
            model_type = cfg.get("generation_model") or "simple"
            client = get_qwen_client()
            self._llm = client.get_llm(model_type)
        return self._llm

    def _collect_candidate_inverse_labels(self) -> List[str]:
        from .utils import _filter_candidate_inverse_labels
        labels = []
        for page in self.graph_mgr.currentGraph.page_nodes:
            for state in page.state_nodes:
                for event in getattr(state, "available_events", []) or []:
                    if getattr(event, "has_data_side_effect", False):
                        lb = getattr(event, "semantic_label", "") or ""
                        labels.append(lb)
        return _filter_candidate_inverse_labels(list(set(labels)))

    def apply(self, original: ScriptPath) -> List[ScriptPath]:
        from llm.methods import MRCancelPairingMethod

        variants: List[ScriptPath] = []
        arr = original.to_array()
        states = extract_state_sequence(original)
        events = extract_event_sequence(original)

        event_labels = []
        state_summaries = []
        for i, node in enumerate(arr):
            if not isinstance(node, PathNode) or node.event is None:
                continue
            ev = node.event
            if not getattr(ev, "has_data_side_effect", False):
                continue
            lb = getattr(ev, "semantic_label", "") or f"event_{ev.event_id}"
            event_labels.append(lb)
            st = node.state
            if isinstance(st, StateNode):
                entities = getattr(st, "data_entities", []) or []
                state_summaries.append({getattr(e, "key", ""): getattr(e, "value", "") for e in entities})
            else:
                state_summaries.append({})

        if not event_labels:
            return []

        candidate_inverse = self._collect_candidate_inverse_labels()
        try:
            app_name = (self.config.get("appium") or {}).get("appPackage")
            method = MRCancelPairingMethod(self._get_llm(), app_name=app_name)
            out = method.invoke({
                "event_semantic_labels": str(event_labels),
                "state_data_entity_summaries": str(state_summaries),
                "candidate_inverse_labels": str(candidate_inverse),
            })
        except Exception as e:
            print(f"MRCancel pairing LLM failed: {e}")
            return []

        pairs = getattr(out, "pairs", []) or []
        for pair in pairs:
            if not getattr(pair, "rollback_feasible", False):
                continue
            forward_label = getattr(pair, "forward", "")
            inverse_label = getattr(pair, "inverse", "")
            forward_node_idx = None
            for i, node in enumerate(arr):
                if not isinstance(node, PathNode) or node.event is None:
                    continue
                if (getattr(node.event, "semantic_label", "") or "").strip() == forward_label.strip():
                    forward_node_idx = i
                    break
            if forward_node_idx is None:
                continue
            forward_state = arr[forward_node_idx].state
            if not isinstance(forward_state, StateNode):
                continue
            next_after_forward = forward_node_idx + 1
            if next_after_forward >= len(arr):
                continue
            next_state_orig = arr[next_after_forward].state
            inverse_state_candidates = []
            for page in self.graph_mgr.currentGraph.page_nodes:
                for st in page.state_nodes:
                    for ev in getattr(st, "available_events", []) or []:
                        if getattr(ev, "has_data_side_effect", False) and (getattr(ev, "semantic_label", "") or "").strip() == inverse_label.strip():
                            inverse_state_candidates.append((st, ev))
                            break
            if not inverse_state_candidates:
                continue
            inv_state, inv_event = inverse_state_candidates[0]
            config = PathSearchConfig(max_depth=20, max_results=5, prefer_shorter_paths=True)
            paths_to_inv = find_all_paths_between_states(self.graph_mgr, next_state_orig, inv_state, config)
            if not paths_to_inv:
                continue
            path_to_inv = paths_to_inv[0]
            paths_back = find_all_paths_between_states(self.graph_mgr, inv_state, next_state_orig, config)
            if not paths_back:
                continue
            path_back = paths_back[0]
            injection_states = path_to_inv + path_back[1:]
            injection_events = []
            for i in range(len(injection_states) - 1):
                e = get_transition_event(injection_states[i], injection_states[i + 1])
                if e is None:
                    break
                injection_events.append(e)
            else:
                if len(injection_events) != len(injection_states) - 1:
                    continue
                prefix = clone_path_segment(original, 0, forward_node_idx)
                injection_path = build_script_path_from_states(injection_states, injection_events)
                suffix = clone_path_segment(original, min(next_after_forward + 1, len(arr) - 1), len(arr) - 1)
                combined = concatenate_path_segments(prefix, injection_path, suffix)
                new_path_name = f"{original.path_name}__MRCancel__{len(variants)}"
                combined.set_path_name(new_path_name)

                prefix_arr = prefix.to_array() if prefix and prefix.start_path_node else []
                injection_start = len(prefix_arr)
                mutation_description = {
                    "forward_event_label": forward_label,
                    "inverse_event_label": inverse_label,
                    "before_values": str({getattr(e, "key", ""): getattr(e, "value", "") for e in forward_state.data_entities}),
                    "after_forward_values": str({getattr(e, "key", ""): getattr(e, "value", "") for e in next_state_orig.data_entities}),
                    "subsequent_states_data_entities": [
                        {
                            "mutated_state_id": state.id,
                            # `path_index` in `subsequent_states_data_entities` must be an index into the mutated-path array.
                            "path_index": injection_start + offset,
                            "state_intent": (getattr(state.parent_page_node, "semantic_label", "") if isinstance(state, StateNode) and state.parent_page_node else "") or getattr(state, "name", ""),
                            "data_entities": [
                                {
                                    "key": getattr(e, "key", ""),
                                    "type": getattr(e, "type", ""),
                                    "value": getattr(e, "value", "")
                                }
                                for e in (getattr(state, "data_entities", []) or [])
                            ],
                        }
                        for offset, state in enumerate(injection_states[1:], start=1)
                    ],
                    # Mutation injection/modification position (used by downstream to fill `is_mutated`).
                    "mutated_state_path_indices": list(
                        range(injection_start + 1, injection_start + len(injection_states))
                    )
                }
                combined.set_mutation_description(mutation_description)
                if combined.start_path_node is not None:
                    variants.append(combined)
                
        return variants

    def get_mutation_description(
        self, original: ScriptPath, path: ScriptPath
    ) -> Dict[str, Any]:
        """
        Provide the MR-Cancel mutation description for the verification-side LLM and dynamic assertions.

        Downstream fields:
        `forward_event_label`, `inverse_event_label`, `before_values`, `after_forward_values`, `subsequent_states_data_entities`.
        """
        return path.mutation_description
