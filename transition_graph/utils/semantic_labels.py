from transition_graph import StateNode
from llm.methods import StateSemanticUnderstandingResult, StateSemanticUnderstandingMethod
from llm.providers import get_qwen_client


def generate_semantic_understanding_result_for_state_node(
    state_node: StateNode,
    available_semantic_labels: list[str],
    existing_data_field_keys: list[str] | None = None,
    existing_event_semantic_labels: list[str] | None = None,
    app_name: str | None = None,
) -> StateSemanticUnderstandingResult:
    qwen_client = get_qwen_client()
    llm = qwen_client.get_llm("vision", temperature=0)
    method = StateSemanticUnderstandingMethod(llm, app_name=app_name)
    return method.run(
        screenshots_path=state_node.screenshot_path,
        component_tree=state_node.component_tree,
        available_semantic_labels=available_semantic_labels,
        available_events=state_node.available_events,
        existing_data_field_keys=existing_data_field_keys,
        existing_event_semantic_labels=existing_event_semantic_labels,
    )