# MR-Cancel inverse-operation pairing (generator-side LLM) prompt

MR_CANCEL_PAIRING_PROMPT = """You are a mobile application testing expert. The path may contain operations with data side effects (e.g. add, modify). For each, match a semantic inverse operation (e.g. delete, cancel) and judge whether data can roll back to the pre-operation state after the inverse. If no pair exists, output an empty list.

**Semantic labels of events on the path**: {event_semantic_labels}
**Data entity summary per state where each event occurs**: {state_data_entity_summaries}
**Candidate inverse operations (semantic labels) in the graph**: {candidate_inverse_labels}

Output pairs of forward operations and inverse operations that can be paired. A pair is only used for injection when rollback_feasible is true.
Output strictly in the following JSON format (no other text):
{{
  "pairs": [
    {{
      "forward": "forward event semantic label",
      "inverse": "inverse operation semantic label",
      "rollback_feasible": true or false,
      "reason": "short reason"
    }}
  ]
}}
"""
