"""
MR-State: state-dependent path injection (new approach).

Prerequisite: local subgraph pruning (intersection of BFS + reverse BFS).
Stage 1: LLM semantic planning (one call generating 3~10 intent sequences).
Stage 2: semantic alignment instantiation (pure algorithm validates continuity
and generates expansion paths).

The verification-side LLM (`mr_state_side_effect`) and dynamic assertions are
invoked uniformly by the Generator.
"""
from typing import List, Optional, Dict, Any

from transition_graph import GraphManager, ScriptPath, StateNode, PageNode
from mutator.generator.mrs.mr import MetamorphicRelation
from mutator.generator.mrs.utils import (
    extract_page_sequence,
    extract_state_sequence,
    build_script_path_from_states,
    concatenate_path_segments,
    clone_path_segment,
    build_local_candidate_subgraph,
    build_subgraph_semantic_summary,
    build_edge_by_id,
    align_intent_sequence_to_path,
)


def _build_mutation_description(
    p_k: PageNode,
    p_next: PageNode,
    injected_pages: List[PageNode],
    insertion_states: List,
    insertion_events: List,
    suffix_states: List,
) -> Dict[str, Any]:
    """Build an MR-State mutation description for the verification side; keep fields consistent with downstream `get_mutation_description`."""
    intent_k = getattr(p_k, "semantic_label", "") or getattr(p_k, "name", "")
    intent_k_plus_1 = getattr(p_next, "semantic_label", "") or getattr(p_next, "name", "")
    injected_intents = [getattr(p, "semantic_label", "") or getattr(p, "name", "") for p in injected_pages]
    injected_page_set = set(id(p) for p in injected_pages)
    event_descriptions = []
    for idx, ev in enumerate(insertion_events):
        if idx >= len(insertion_states) - 1:
            break
        s = insertion_states[idx]
        if isinstance(s, StateNode) and getattr(s, "parent_page_node", None) and id(s.parent_page_node) in injected_page_set:
            lb = getattr(ev, "semantic_label", "") or getattr(ev, "xpath", "") or f"event_{idx}"
            event_descriptions.append(lb)
    injected_events_and_effects = "; ".join(event_descriptions) if event_descriptions else str(injected_intents)
    subsequent = [
        {
            "mutated_state_id": s.id,
            "state_intent": (getattr(s.parent_page_node, "semantic_label", "") if isinstance(s, StateNode) and s.parent_page_node else "") or getattr(s, "name", ""),
            "data_entities": [
                {"key": getattr(e, "key", ""), "type": getattr(e, "type", ""), "value": getattr(e, "value", "")}
                for e in (getattr(s, "data_entities", []) or [])
            ],
        }
        for s in suffix_states
    ]
    return {
        "intent_k": intent_k,
        "intent_k_plus_1": intent_k_plus_1,
        "injected_intents": str(injected_intents),
        "injected_events_and_effects": injected_events_and_effects,
        "subsequent_states_data_entities": subsequent,
    }


class MRState(MetamorphicRelation):
    """Inject a sub-scenario path with data side effects between adjacent semantic page pairs."""

    def __init__(self, graph_mgr: GraphManager, config: Optional[dict] = None):
        super().__init__(
            name="MRState",
            description="State-dependent path injection between adjacent semantic pages",
            mr_type="MRState",
            graph_mgr=graph_mgr,
        )
        self.config = config or {}
        self._llm = None
        mr_cfg = self.config.get("mutation", {}).get("mrState", {})
        self.max_candidates = mr_cfg.get("maxCandidates", 5)
        self.subgraph_max_depth = mr_cfg.get("subgraphMaxDepth", 6)
        self.subgraph_max_edges = mr_cfg.get("subgraphMaxEdges", 50)
        self.alignment_max_retry = mr_cfg.get("alignmentMaxRetry", 2)

    def _get_llm(self):
        if self._llm is None:
            from llm.providers import get_qwen_client
            cfg = self.config.get("mutation", {}).get("llm", {})
            model_type = cfg.get("generation_model") or "complex"
            client = get_qwen_client()
            self._llm = client.get_llm(model_type)
        return self._llm

    def apply(self, original: ScriptPath) -> List[ScriptPath]:
        from llm.methods import MRStateSemanticPlanningMethod

        variants: List[ScriptPath] = []
        pages = extract_page_sequence(original)
        states = extract_state_sequence(original)
        if len(pages) < 2:
            return []

        for i in range(len(states) - 1):
            s_k = states[i]
            s_next = states[i + 1]
            
            if not isinstance(s_k, StateNode) or not isinstance(s_next, StateNode):
                continue # ensure both are regular state nodes

            p_k = s_k.parent_page_node
            p_next = s_next.parent_page_node

            if p_k is None or p_next is None or p_k == p_next:
                continue # ensure both are valid page nodes and not the same page

            exit_state = s_k
            entry_state = s_next
            if len(variants) >= self.max_candidates:
                break

            # Prune a local subgraph (path granularity) to ensure it is connected and focused.
            nodes_set, edges_with_id = build_local_candidate_subgraph(
                self.graph_mgr,
                exit_state,
                entry_state,
                max_depth=self.subgraph_max_depth,
                max_edges_limit=self.subgraph_max_edges,
            )
            if not edges_with_id:
                continue

            edge_summaries = build_subgraph_semantic_summary(edges_with_id)
            edges_semantic_list = "\n".join(
                f"Edge '{eid}': {desc}" for eid, desc in edge_summaries
            )
            intent_k = getattr(p_k, "semantic_label", "") or getattr(p_k, "name", "")
            intent_k_plus_1 = getattr(p_next, "semantic_label", "") or getattr(p_next, "name", "")
            print(f"MRState intent_k: {intent_k}, intent_k_plus_1: {intent_k_plus_1} [variants: {len(variants)}]")

            # Stage 1: LLM semantic planning (single call).
            intent_sequences_raw: Optional[List[List[Any]]] = None
            for attempt in range(self.alignment_max_retry + 1):
                try:
                    app_name = (self.config.get("appium") or {}).get("appPackage")
                    method = MRStateSemanticPlanningMethod(self._get_llm(), app_name=app_name)
                    out = method.invoke({
                        "intent_k": intent_k,
                        "intent_k_plus_1": intent_k_plus_1,
                        "edges_semantic_list": edges_semantic_list,
                    })
                    raw = getattr(out, "intent_sequences", None) or []
                    if isinstance(raw, list) and len(raw) > 0:
                        intent_sequences_raw = raw
                        break
                except Exception as e:
                    print(f"MRState semantic planning LLM failed (attempt {attempt + 1}): {e}")
                intent_sequences_raw = None

            if not intent_sequences_raw:
                continue

            edge_by_id = build_edge_by_id(edges_with_id)

            # Stage 2: semantic alignment instantiation (pure algorithm).
            for seq in intent_sequences_raw:
                if len(variants) >= self.max_candidates:
                    break
                steps = seq if isinstance(seq, list) else []
                aligned = align_intent_sequence_to_path(
                    steps, edge_by_id, exit_state, entry_state
                )
                if aligned is None:
                    continue
                insertion_states, insertion_events = aligned
                if len(insertion_states) < 2:
                    continue

                orig_states = extract_state_sequence(original)
                prefix_end = None
                suffix_start = None
                for i, state in enumerate(orig_states):
                    if state.id == exit_state.id:
                        prefix_end = i
                    if prefix_end is not None and state.id == entry_state.id:
                        suffix_start = i
                        break
                if prefix_end is None or suffix_start is None:
                    continue

                prefix = clone_path_segment(original, 0, max(0, prefix_end - 1))
                suffix = clone_path_segment(original, suffix_start, len(original.to_array()) - 1)
                middle_states = insertion_states[:-1]
                if len(insertion_events) != len(middle_states):
                    continue
                middle_path = build_script_path_from_states(middle_states, insertion_events)
                combined = concatenate_path_segments(prefix, middle_path, suffix)
                if combined.start_path_node is None:
                    continue

                injected_pages = []
                seen_page_ids = set()
                for s in insertion_states[1:-1]:
                    if isinstance(s, StateNode) and getattr(s, "parent_page_node", None):
                        pid = id(s.parent_page_node)
                        if pid not in seen_page_ids:
                            seen_page_ids.add(pid)
                            injected_pages.append(s.parent_page_node)
                suffix_states = extract_state_sequence(suffix)
                mutation_description = _build_mutation_description(
                    p_k, p_next, injected_pages, insertion_states, insertion_events, suffix_states
                )
                # Pass through the mutation injection locations (`path_index`) required by downstream.
                combined_arr = combined.to_array()
                prefix_arr = prefix.to_array() if prefix and prefix.start_path_node else []
                middle_arr = middle_path.to_array() if middle_path and middle_path.start_path_node else []
                injection_start = len(prefix_arr)

                mutated_state_path_indices = list(range(injection_start, injection_start + len(middle_arr)))
                # If the first state of the middle segment and the last state of `prefix` are the same instance
                # (boundary duplication), do not mark it as "new"/"mutation injection".
                if prefix_arr and middle_arr and getattr(middle_arr[0], "state", None) is getattr(prefix_arr[-1], "state", None):
                    mutated_state_path_indices = [i for i in mutated_state_path_indices if i != injection_start]
                mutation_description["mutated_state_path_indices"] = mutated_state_path_indices

                # Attach `path_index` (index in the mutated path) to each entry of `subsequent_states_data_entities`.
                state_obj_to_path_index = {id(node.state): idx for idx, node in enumerate(combined_arr) if hasattr(node, "state")}
                suffix_path_indices = [state_obj_to_path_index.get(id(s)) for s in suffix_states]
                subsequent = mutation_description.get("subsequent_states_data_entities", []) or []
                for entry, pidx in zip(subsequent, suffix_path_indices):
                    if pidx is not None:
                        entry["path_index"] = int(pidx)
                combined.set_mutation_description(mutation_description)
                combined.set_path_name(f"{original.path_name}__MRState__{len(variants)}")
                variants.append(combined)

        return variants[: self.max_candidates]

    def get_mutation_description(
        self, original: ScriptPath, path: ScriptPath
    ) -> Dict[str, Any]:
        """
        Provide an MR-State mutation description for the verification-side LLM and dynamic assertions.

        If `mutation_description` has already been written during mutation, return it directly;
        otherwise infer it from the path using the original logic.
        """
        return path.mutation_description
