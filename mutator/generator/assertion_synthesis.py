"""
Dynamic assertion synthesis orchestration: for each MR-generated `pi_aug`, call the
verification-side LLM and the assertion-generation LLM, and write the results back to
`PathNode.oracles`.
"""
from typing import Optional, Dict, Any, List, Tuple, Set

from transition_graph import ScriptPath, PathNode, StateNode, InternalStateNode
from transition_graph.events.event import AbstractEvent
from transition_graph.manager.graph_manager import GraphManager
from transition_graph.oracles.oracle import TextOracle, AttributeOracle, DisplayOracle

from mutator.generator.context_extraction import (
    extract_context,
    ContextExtractionResult,
    MUTATION_TYPE_DATA,
    MUTATION_TYPE_STATE,
    MUTATION_TYPE_CANCEL,
)


def _config_app_name(config: Optional[dict]) -> Optional[str]:
    if not config:
        return None
    return (config.get("appium") or {}).get("appPackage")


def _run_verification_llm(
    mutation_type: str,
    context: ContextExtractionResult,
    config: Optional[dict] = None,
) -> Optional[List[Dict[str, Any]]]:
    """Call the corresponding verification-side LLM based on mutation type and return an `effects`
    list that includes `path_index`.
    """
    cfg = (config or {}).get("mutation", {}).get("llm", {})
    model_type = cfg.get("verification_model") or "simple"
    try:
        from llm.providers import get_qwen_client
        from llm.methods import (
            MRDataSideEffectMethod,
            MRStateSideEffectMethod,
            MRCancelRollbackMethod,
        )
        client = get_qwen_client()
        llm = client.get_llm(model_type)
        md = context.mutation_description

        an = _config_app_name(config)
        if mutation_type == MUTATION_TYPE_DATA:
            method = MRDataSideEffectMethod(llm, app_name=an)
            out = method.invoke({
                "page_intent": md.get("page_intent", ""),
                "mutation_state_event": md.get("mutation_state_event", ""),
                "input_label": md.get("input_label", ""),
                "original_value": md.get("original_value", ""),
                "new_value": md.get("new_value", ""),
                "subsequent_states_data_entities": md.get("subsequent_states_data_entities", ""),
            })
        elif mutation_type == MUTATION_TYPE_STATE:
            method = MRStateSideEffectMethod(llm, app_name=an)
            out = method.invoke({
                "intent_k": md.get("intent_k", ""),
                "intent_k_plus_1": md.get("intent_k_plus_1", ""),
                "injected_intents": md.get("injected_intents", ""),
                "injected_events_and_effects": md.get("injected_events_and_effects", ""),
                "subsequent_states_data_entities": md.get("subsequent_states_data_entities", ""),
            })
        elif mutation_type == MUTATION_TYPE_CANCEL:
            method = MRCancelRollbackMethod(llm, app_name=an)
            out = method.invoke({
                "forward_event_label": md.get("forward_event_label", ""),
                "inverse_event_label": md.get("inverse_event_label", ""),
                "before_values": md.get("before_values", ""),
                "after_forward_values": md.get("after_forward_values", ""),
                "subsequent_states_data_entities": md.get("subsequent_states_data_entities", ""),
            })
        else:
            return None
        # Verification-side output is normalized to `effects: [{field_key, path_index, expected_value}, ...]`.
        if hasattr(out, "model_dump"):
            d = out.model_dump()
            return d.get("effects", []) or []
        if hasattr(out, "effects"):
            effects = getattr(out, "effects") or []
            # Compatibility: if `effects` contains Pydantic items, convert them to plain dicts.
            out_effects: List[Dict[str, Any]] = []
            for e in effects:
                if hasattr(e, "model_dump"):
                    out_effects.append(e.model_dump())
                elif isinstance(e, dict):
                    out_effects.append(e)
            return out_effects
        return []
    except Exception as e:
        print(f"Verification LLM failed ({mutation_type}): {e}")
        return None


def _oracles_from_assertion_items(
    assertion_items: List[Dict[str, Any]],
    path_arr: List,
) -> Dict[int, List]:
    """Group the LLM output `assertions` by `path_index` and convert them to Oracle instances."""
    by_index: Dict[int, List] = {}
    for item in assertion_items:
        idx = item.get("path_index", 0)
        if idx < 0 or idx >= len(path_arr):
            continue
        node = path_arr[idx]
        if not isinstance(node, PathNode):
            continue
        state = node.state
        if not isinstance(state, StateNode):
            continue
        locator = item.get("locator") or {}
        if locator.get("method") != "AppiumBy.XPATH" and locator.get("value"):
            locator = {"method": "AppiumBy.XPATH", "value": locator.get("value", "")}
        t = (item.get("type") or "text").strip().lower()
        try:
            if t == "text":
                o = TextOracle(state, locator, item.get("text") or "", item.get("validation_type") or "exact")
            elif t == "attribute":
                o = AttributeOracle(state, locator, item.get("attribute") or "", item.get("value") or "")
            elif t == "display":
                o = DisplayOracle(state, locator, bool(item.get("display", False)))
            else:
                continue
            by_index.setdefault(idx, []).append(o)
        except Exception:
            continue
    return by_index

TRUNCATED_VALUE_LENGTH = 80
def _truncate_value(value: str) -> str:
    if len(value) > TRUNCATED_VALUE_LENGTH:
        return value[:TRUNCATED_VALUE_LENGTH] + "[TRUNCATED]"
    return value


def _get_state_intent(state: Any) -> str:
    """Extract semantic intent from `StateNode`; `InternalStateNode` has no intent."""
    if isinstance(state, InternalStateNode) or not isinstance(state, StateNode):
        return ""
    page = getattr(state, "parent_page_node", None)
    return (getattr(page, "semantic_label", "") if page else "") or ""
def _get_state_event_summary(event: AbstractEvent) -> str:
    """Extract an event summary from an `Event`."""
    from transition_graph.events.event import InternalEvent, ClickEvent, TextInputEvent, BackEvent
    if event is None:
        return ""
    if isinstance(event, InternalEvent):
        return "Internal event executed"
    if isinstance(event, ClickEvent):
        return f"Clicked element {event.semantic_label if event.semantic_label else event.xpath}"
    if isinstance(event, TextInputEvent):
        return f"Entered text '{_truncate_value(event.text or '')}' into element {event.semantic_label if event.semantic_label else event.xpath}"
    if isinstance(event, BackEvent):
        return "Performed back operation"
    return "Unknown event"

def _get_state_data_entities(state: Any) -> List[Dict[str, Any]]:
    """Extract a serializable summary of `data_entities`."""
    if isinstance(state, InternalStateNode) or not isinstance(state, StateNode):
        return []
    out: List[Dict[str, Any]] = []
    for de in getattr(state, "data_entities", []) or []:
        out.append(
            {
                "key": getattr(de, "key", ""),
                "type": getattr(de, "type", ""),
                "value": _truncate_value(getattr(de, "value", "")),
            }
        )
    return out


def _build_original_path_summary(pi_orig: ScriptPath, original_assertions: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Build the original-path summary (aggregate original assertions by `path_index`)."""
    assertions_by_idx: Dict[int, List[Dict[str, Any]]] = {}
    for a in original_assertions or []:
        idx = a.get("path_index")
        if not isinstance(idx, int):
            continue
        oracle = a.get("oracle") or {}
        # `oracle.to_dict()` structure is not fixed. Extract commonly used fields when possible;
        # leave missing ones empty.
        item = {
            "type": (oracle.get("type") or oracle.get("oracle_type") or ""),
            "field_key": oracle.get("field_key") or oracle.get("key") or None,
            "text": oracle.get("text") or None,
            "attribute": oracle.get("attribute") or None,
            "value": _truncate_value(oracle.get("value") or ""),
            "display": oracle.get("display") if "display" in oracle else None,
        }
        assertions_by_idx.setdefault(idx, []).append(item)

    out: List[Dict[str, Any]] = []
    arr = pi_orig.to_array()
    for i, node in enumerate(arr):
        if not isinstance(node, PathNode):
            continue
        st = node.state
        out.append(
            {
                "path_index": i,
                "state_intent": _get_state_intent(st),
                "data_entities": _get_state_data_entities(st),
                "event_summary": _get_state_event_summary(node.event),
                # In the prompt this field is explicitly described as "may be missing/empty";
                # output an array so the model can reference it consistently.
                "original_assertions": assertions_by_idx.get(i, []),
            }
        )
    return out


def _build_mutated_path_summary(
    pi_orig: ScriptPath,
    pi_aug: ScriptPath,
    verification_effects: Optional[List[Dict[str, Any]]],
    mutated_state_path_indices: Optional[List[int]],
) -> List[Dict[str, Any]]:
    """Build the mutated-path summary (including `is_mutated` and an optional
    `new_expected_value_after_mutation`).
    """
    mutated_idx_set: Set[int] = set(mutated_state_path_indices or [])

    # Fallback: if upstream does not provide `mutated_state_path_indices`, use the legacy
    # strategy: treat states as mutated if their `state.id` appears in the original path.
    orig_state_ids: Set[Any] = set()
    if not mutated_idx_set:
        for n in pi_orig.to_array():
            if (
                isinstance(n, PathNode)
                and isinstance(n.state, StateNode)
                and not isinstance(n.state, InternalStateNode)
            ):
                orig_state_ids.add(getattr(n.state, "id", None))

    expected_by_idx_and_key: Dict[Tuple[int, str], str] = {}
    fallback_by_field: Dict[str, str] = {}
    for eff in verification_effects or []:
        if not isinstance(eff, dict):
            continue
        idx = eff.get("path_index")
        field_key = eff.get("field_key")
        expected_value = _truncate_value(eff.get("expected_value") or "")
        if field_key is None or expected_value is None:
            continue
        field_key = str(field_key)
        expected_value = str(expected_value)
        if isinstance(idx, int) and idx >= 0:
            expected_by_idx_and_key[(idx, field_key)] = expected_value
        else:
            # Compatibility with legacy verification output (no `path_index`);
            # fall back to a global expected value per `field_key`.
            fallback_by_field[field_key] = expected_value

    out: List[Dict[str, Any]] = []
    for i, node in enumerate(pi_aug.to_array()):
        if not isinstance(node, PathNode):
            continue
        st = node.state
        data_entities = _get_state_data_entities(st)

        new_expected: Dict[str, str] = {}
        for d in data_entities:
            k = d.get("key")
            if not k:
                continue
            kk = str(k)
            if (i, kk) in expected_by_idx_and_key:
                new_expected[kk] = expected_by_idx_and_key[(i, kk)]
            elif kk in fallback_by_field:
                new_expected[kk] = fallback_by_field[kk]

        if mutated_idx_set:
            is_mutated = i in mutated_idx_set
        else:
            is_mutated = (
                (getattr(st, "id", None) not in orig_state_ids) if isinstance(st, StateNode) else True
            )
        item: Dict[str, Any] = {
            "path_index": i,
            "state_intent": _get_state_intent(st),
            "data_entities": data_entities,
            "event_summary": _get_state_event_summary(node.event),
            "is_mutated": is_mutated,
        }
        if new_expected:
            item["new_expected_value_after_mutation"] = new_expected
        out.append(item)
    return out

def run_assertion_synthesis(
    pi_orig: ScriptPath,
    pi_aug: ScriptPath,
    mutation_type: str,
    mutation_description: Dict[str, Any],
    graph_mgr: Optional[GraphManager] = None,
    config: Optional[dict] = None,
) -> None:
    """
    Execute on `pi_aug`: context extraction -> verification-side LLM -> assertion-generation LLM
    -> write back to `pi_aug`'s `PathNode.oracles`.
    """
    type_map = {"MRData": MUTATION_TYPE_DATA, "MRState": MUTATION_TYPE_STATE, "MRCancel": MUTATION_TYPE_CANCEL}
    mutation_type = type_map.get(mutation_type, mutation_type)

    context = extract_context(
        pi_orig,
        pi_aug,
        mutation_type,
        mutation_description,
        graph_mgr=graph_mgr,
        include_bindings_for_data=(mutation_type == MUTATION_TYPE_DATA),
    )
    expected_effects = _run_verification_llm(mutation_type, context, config)
    context.verification_llm_expected_values = expected_effects or []

    # Build an index `(path_index, data_entity.key) -> locator` based on the graph and
    # `State.data_entities`.
    #
    # This is used to reverse-resolve the LLM output `field_key` into a concrete xpath on the program side,
    # avoiding the LLM generating locators on its own.
    field_locator_index: Dict[Tuple[int, str], Dict[str, Any]] = {}
    arr_aug = pi_aug.to_array()
    for idx, node in enumerate(arr_aug):
        if not isinstance(node, PathNode):
            continue
        state = node.state
        if isinstance(state, InternalStateNode) or not isinstance(state, StateNode):
            continue
        for de in getattr(state, "data_entities", []) or []:
            key = getattr(de, "key", None)
            locator = getattr(de, "locator", None)
            if not key or not isinstance(locator, dict):
                continue
            field_locator_index[(idx, key)] = locator

    try:
        from llm.providers import get_qwen_client
        from llm.methods import DynamicAssertionSynthesisMethod

        client = get_qwen_client()
        cfg = (config or {}).get("mutation", {}).get("llm", {})
        model_type = cfg.get("verification_model") or "simple"
        llm = client.get_llm(model_type)
        method = DynamicAssertionSynthesisMethod(llm, app_name=_config_app_name(config))
        ctx_dict = context.to_dict()

        # -----------------------------
        # Assertion-generation LLM prompt context refactor:
        # reduce from the old 6 segments of redundant information to 3 segments
        # (two path summaries + mutation description).
        # -----------------------------
        original_path_summary = _build_original_path_summary(
            pi_orig,
            ctx_dict.get("original_assertions", []) or [],
        )
        mutation_desc = ctx_dict.get("mutation_description", {}) or {}
        mutated_state_path_indices = mutation_desc.get("mutated_state_path_indices", []) or []
        verification_effects = ctx_dict.get("verification_llm_expected_values", []) or []
        mutated_path_summary = _build_mutated_path_summary(
            pi_orig,
            pi_aug,
            verification_effects,
            mutated_state_path_indices,
        )

        md: Dict[str, Any] = dict(ctx_dict.get("mutation_description", {}) or {})
        # Remove redundant fields (previously used only in the verification-side prompt;
        # no longer inject them into the assertion-generation prompt).
        if "subsequent_states_data_entities" in md:
            md.pop("subsequent_states_data_entities", None)

        _raw_vev = ctx_dict.get("verification_llm_expected_values", []) or []
        verification_expected_for_prompt: List[Dict[str, Any]] = []
        for eff in _raw_vev:
            if isinstance(eff, dict):
                item = dict(eff)
                ev = item.get("expected_value")
                item["expected_value"] = _truncate_value("" if ev is None else str(ev))
                verification_expected_for_prompt.append(item)
            else:
                verification_expected_for_prompt.append(eff)

        mutation_description_for_prompt: Dict[str, Any] = {
            "mutation_type": mutation_type,
            "details": md,
            # Verification-side new expected values: allow the model to fix/add assertions near
            # mutation locations; the program side still filters them by state and places them into
            # `mutated_path_summary`.
            "verification_expected_values": verification_expected_for_prompt,
        }

        prompt_ctx = {
            "original_path_summary": original_path_summary,
            "mutated_path_summary": mutated_path_summary,
            "mutation_description": mutation_description_for_prompt,
        }
        out = method.run(prompt_ctx, field_locator_index)
    except Exception as e:
        print(f"Dynamic assertion synthesis LLM failed: {e}")
        return

    assertions = getattr(out, "assertions", []) or []
    assertion_dicts = []
    for a in assertions:
        if hasattr(a, "model_dump"):
            assertion_dicts.append(a.model_dump())
        elif isinstance(a, dict):
            assertion_dicts.append(a)
    path_arr = pi_aug.to_array()
    by_index = _oracles_from_assertion_items(assertion_dicts, path_arr)
    for idx, node in enumerate(path_arr):
        if not isinstance(node, PathNode):
            continue
        node.oracles = by_index.get(idx, [])
    pi_aug.from_array(path_arr)
