STATE_SEMANTIC_UNDERSTANDING_PROMPT = """
You are a mobile application testing expert. Please analyze the current mobile app screenshot and component tree (controls that may contain data are marked with [node_N]). Answer three questions and output JSON:

(1) What is this page's functional intent? Give a concise English label in `verb_noun` or `noun_noun` form per the constraints below, e.g. `Login_Form`, `Product_Detail`, `Cart_Summary`;

(2) What are the key data fields on the page? From nodes marked [node_N] in the tree, list field name, type (input/output/input_output), and corresponding node ID (only node_N, e.g. node_0, node_12—do not invent xpath or resource-id);

(3) Which actions might change these data fields? From the "available events list" below, select events that may change data; only include their event_id (integer), and give each a short English semantic label (e.g. click_qty_plus).

The "available events list" format is: event_id, type, short description. In data_changing_events, only include these event_ids and corresponding semantic_labels.

{reference_keys_instruction}
---
Indexed component tree (only controls that may contain data; [node_N] is the node ID):
{indexed_component_tree}

---
Available events list (event_id is integer; you may only choose from these event_ids):
{available_events_list}
---

JSON output format (follow strictly):
{{
  "intent": "Cart_Summary",
  "data_fields": [
    {{"key": "item_price", "type": "output", "node_id": "node_0"}},
    {{"key": "item_qty", "type": "input_output", "node_id": "node_1"}},
    {{"key": "total_price", "type": "output", "node_id": "node_2"}}
  ],
  "data_changing_events": [
    {{"event_id": 0, "semantic_label": "click_qty_plus"}},
    {{"event_id": 1, "semantic_label": "click_qty_minus"}}
  ]
}}

Constraints:
- Choose the best-matching intent label from the existing labels below; if none fit, create a new label in English using underscore-separated `verb/noun_noun`, Title_Case.
- node_id in data_fields must be one of the [node_N] appearing in the tree above; do not invent.
- event_id in data_changing_events must be an integer from the available events list above; do not invent.
- If "similar state semantic keys" are provided below, prefer reusing existing keys for data_fields.key and data_changing_events.semantic_label (only create new keys when current semantics do not match any existing key) to keep naming consistent across states.
Existing labels: {available_semantic_labels}
"""
