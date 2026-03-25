import re
import xml.etree.ElementTree as ET
from typing import Any

from langchain_core.messages import HumanMessage
from langchain_openai import ChatOpenAI
from pydantic import BaseModel, Field

from .base_method import BaseMethod
from llm.prompts.state_semantic_understanding import STATE_SEMANTIC_UNDERSTANDING_PROMPT

from transition_graph.events.event import AbstractEvent

# Control class names that may contain data (consistent with `event_parser`).
_DATA_WIDGET_CLASSES = {
    "android.widget.EditText",
    "android.widget.AutoCompleteTextView",
    "android.widget.TextView",
}


def _build_indexed_component_tree(component_tree: str) -> tuple[str, dict[str, str]]:
    """
    Traverse the component tree and assign a global unique index `[node_N]` to nodes that
    are visible and likely to contain data.

    Return a compact indexed tree string and a mapping `node_id -> xpath` (used for
    later reverse parsing).
    """
    if not (component_tree or component_tree.strip()):
        return "", {}

    try:
        root = ET.fromstring(component_tree)
    except ET.ParseError:
        return "", {}

    index_to_xpath: dict[str, str] = {}
    node_counter = [0]  # Use a list so it can be modified during recursion.

    def _is_visible(element: ET.Element) -> bool:
        attrib = element.attrib
        if attrib.get("visible-to-user") == "false":
            return False
        bounds = attrib.get("bounds", "")
        if bounds == "0,0-0,0" or not bounds:
            return True  # Do not filter when bounds are missing.
        return True

    def _is_data_capable(element: ET.Element) -> bool:
        tag = element.tag
        cls = element.attrib.get("class", "")
        return tag in _DATA_WIDGET_CLASSES or cls in _DATA_WIDGET_CLASSES

    def _collect_and_index(parent_el: ET.Element, parent_ref: ET.Element | None) -> list[str]:
        lines: list[str] = []
        for child in parent_el:
            child.attrib["parent"] = parent_el
            if _is_data_capable(child) and _is_visible(child):
                node_id = f"node_{node_counter[0]}"
                node_counter[0] += 1
                try:
                    from transition_graph.utils.event_parser import _get_xpath
                    xpath = _get_xpath(child)
                    index_to_xpath[node_id] = xpath
                except Exception:
                    pass
                tag = child.tag
                rid = child.attrib.get("resource-id", "")
                text = (child.attrib.get("text") or "")[:80]
                content_desc = (child.attrib.get("content-desc") or "")[:80]
                parts = [f"[{node_id}]", tag]
                if rid:
                    parts.append(f'resource-id="{rid}"')
                if text:
                    parts.append(f'text="{text}"')
                if content_desc:
                    parts.append(f'content-desc="{content_desc}"')
                lines.append(" ".join(parts))
            lines.extend(_collect_and_index(child, parent_el))
        return lines

    lines = _collect_and_index(root, None)
    indexed_tree_str = "\n".join(lines) if lines else ""

    return indexed_tree_str, index_to_xpath


def _get_value_from_component_tree(component_tree: str, xpath: str) -> str:
    """
    Locate a node by xpath in the component-tree XML and extract its `value`.

    For data controls like `TextView` / `EditText` / `AutoCompleteTextView`,
    `value` is taken from the `text` attribute first, and falls back to `content-desc`.
    """
    if not (component_tree or component_tree.strip()) or not (xpath or xpath.strip()):
        return ""
    try:
        root = ET.fromstring(component_tree)
    except ET.ParseError:
        return ""
    # ElementTree's `findall` needs a leading `.` to start from the current node; change `//` to `.//`.
    inner_xpath = xpath
    index = 0
    match = re.match(r"^\((.*)\)\[(\d+)\]$", xpath.strip())
    if match:
        inner_xpath = match.group(1).strip()
        index = int(match.group(2), 10) - 1
        if index < 0:
            index = 0
    path_for_find = ("." + inner_xpath) if inner_xpath.startswith("//") else inner_xpath
    try:
        elements = root.findall(path_for_find)
    except (SyntaxError, TypeError):
        return ""
    if not elements or index >= len(elements):
        return ""
    el = elements[index]
    # Data controls usually use `text` for content, then `content-desc` (e.g., accessibility description).
    value = (el.attrib.get("text") or "").strip()
    if not value:
        value = (el.attrib.get("content-desc") or "").strip()
    return value


def _format_available_events(available_events: list[AbstractEvent]) -> str:
    """Format `available_events` into a list string that the MLLM can choose from."""
    if not available_events:
        return "（当前无可用事件）"
    parts = []
    for ev in available_events:
        desc = getattr(ev, "xpath", "") or ""
        if isinstance(desc, str) and len(desc) > 60:
            desc = desc[:60] + "..."
        ev_type = getattr(ev, "type", "abstract")
        parts.append(f"  event_id={ev.event_id}, type={ev_type}, description={desc}")
    return "\n".join(parts)


# Result model exposed externally: `data_fields` includes `locator`, and `data_changing_events`
# includes `event_id` and `semantic_label`.
class StateSemanticUnderstandingResult(BaseModel):
    intent: str = Field(..., description="The semantic label representing the intent of the page")
    data_fields: list[dict[str, Any]] = Field(
        ...,
        description="A list of data fields on the page, each with key, type, and locator (see DataEntity for more details)",
    )
    data_changing_events: list[dict[str, Any]] = Field(
        ...,
        description="A list of events that may change the values of the data fields, each with event_id and semantic_label",
    )


# Raw LLM output model:
# `data_fields` uses `node_id`, and `data_changing_events` uses `event_id` (int).
class _StateSemanticUnderstandingLLMOutput(BaseModel):
    intent: str
    data_fields: list[dict[str, Any]]  # key, type, node_id
    data_changing_events: list[dict[str, Any]]  # event_id (int), semantic_label (str)


class StateSemanticUnderstandingMethod(BaseMethod):
    def __init__(
        self,
        llm: ChatOpenAI,
        max_retries: int = 3,
        debug: bool = False,
        app_name: str | None = None,
    ):
        super().__init__(llm, max_retries, debug, app_name=app_name)

    def _build_prompt(self, input_data: dict[str, Any], attempt: int) -> list[HumanMessage]:
        screenshots = input_data.get("screenshots", [])
        indexed_component_tree = input_data.get("indexed_component_tree", "")
        available_events_list = input_data.get("available_events_list", "（无）")
        available_semantic_labels = input_data.get("available_semantic_labels", [])
        existing_data_field_keys = input_data.get("existing_data_field_keys") or []
        existing_event_semantic_labels = input_data.get("existing_event_semantic_labels") or []

        if existing_data_field_keys or existing_event_semantic_labels:
            ref_keys_lines = [
                "Intent label normalization: similar states already have the following semantic keys; when generating `data_fields.key` and `data_changing_events.semantic_label`, prefer reusing existing keys (only create new keys when the semantics are truly different).",
                "- `data_fields` already has keys: " + ", ".join(sorted(set(existing_data_field_keys))) if existing_data_field_keys else "",
                "- `data_changing_events` already has semantic labels: " + ", ".join(sorted(set(existing_event_semantic_labels))) if existing_event_semantic_labels else "",
            ]
            reference_keys_instruction = "\n".join(line for line in ref_keys_lines if line).strip()
        else:
            reference_keys_instruction = ""

        prompt_text = STATE_SEMANTIC_UNDERSTANDING_PROMPT.format(
            reference_keys_instruction=reference_keys_instruction,
            indexed_component_tree=indexed_component_tree or "(No component tree)",
            available_events_list=available_events_list,
            available_semantic_labels=", ".join(available_semantic_labels) if available_semantic_labels else "None",
        )

        if attempt > 0:
            prompt_text += "\n\nNote: The previous output format was incorrect, please strictly output JSON according to the JSON Schema, do not add any explanation text."

        message_content = [{"type": "text", "text": prompt_text}]
        for screenshot_base64 in screenshots[:3]:
            if screenshot_base64:
                message_content.append({
                    "type": "image_url",
                    "image_url": {"url": f"data:image/png;base64,{screenshot_base64}"},
                })
        return [HumanMessage(content=message_content)]

    def _parse_output(self, output_text: str) -> _StateSemanticUnderstandingLLMOutput:
        return self._parse_json_to_model(output_text, _StateSemanticUnderstandingLLMOutput)

    def _load_screenshots_as_base64(self, screenshots_path: str) -> str:
        import base64
        try:
            with open(screenshots_path, "rb") as f:
                return base64.b64encode(f.read()).decode("utf-8")
        except Exception as e:
            print(f"Error loading screenshot: {e}")
            return ""

    def run(
        self,
        screenshots_path: str,
        component_tree: str,
        available_semantic_labels: list[str],
        available_events: list[AbstractEvent],
        existing_data_field_keys: list[str] | None = None,
        existing_event_semantic_labels: list[str] | None = None,
    ) -> StateSemanticUnderstandingResult:
        """
        Execute method.

        Internally, convert the full component tree into a compact indexed tree with `[node_N]`
        and pass it to the MLLM.

        The MLLM only outputs `node_id` and `event_id`, which are reverse-resolved here into
        `xpath` and a valid event list; the external interface remains unchanged.

        `existing_data_field_keys` / `existing_event_semantic_labels` are semantic keys that
        already exist in similar states, used to normalize intent labels.
        """
        indexed_tree_str, index_to_xpath = _build_indexed_component_tree(component_tree)
        available_events_list = _format_available_events(available_events)
        valid_event_ids = {ev.event_id for ev in available_events}

        input_data = {
            "screenshots": [self._load_screenshots_as_base64(screenshots_path)],
            "indexed_component_tree": indexed_tree_str,
            "available_events_list": available_events_list,
            "available_semantic_labels": available_semantic_labels,
            "existing_data_field_keys": existing_data_field_keys or [],
            "existing_event_semantic_labels": existing_event_semantic_labels or [],
        }
        raw: _StateSemanticUnderstandingLLMOutput = self.invoke(input_data)

        data_fields: list[dict[str, Any]] = []
        for item in raw.data_fields:
            node_id = item.get("node_id") or item.get("widget_id")
            key = item.get("key", "")
            typ = item.get("type", "output")
            if node_id and isinstance(node_id, str) and node_id in index_to_xpath:
                xpath_val = index_to_xpath[node_id]
                data_fields.append({
                    "key": key,
                    "type": typ,
                    "locator": {"method": "xpath", "value": xpath_val},
                    "value": _get_value_from_component_tree(component_tree, xpath_val),
                })
            elif node_id and isinstance(node_id, str):
                # The model returned an unknown `node_id`; skip it or keep key/type,
                # but the `locator` may be empty/placeholder.
                data_fields.append({
                    "key": key,
                    "type": typ,
                    "locator": {"method": "xpath", "value": ""},
                    "value": "",
                })

        data_changing_events: list[dict[str, Any]] = []
        for item in raw.data_changing_events:
            try:
                eid = item.get("event_id")
                if eid is None:
                    continue
                eid = int(eid)
            except (TypeError, ValueError):
                continue
            if eid not in valid_event_ids:
                continue
            label = item.get("semantic_label") or str(item.get("semantic_label", ""))
            data_changing_events.append({"event_id": eid, "semantic_label": label})

        return StateSemanticUnderstandingResult(
            intent=raw.intent,
            data_fields=data_fields,
            data_changing_events=data_changing_events,
        )
