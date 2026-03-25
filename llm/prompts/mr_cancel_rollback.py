# MR-Cancel rollback expectation inference (verifier-side LLM) prompt

MR_CANCEL_ROLLBACK_PROMPT = """You are a mobile application testing expert. After a forward operation, an inverse operation was executed on the path; data should roll back toward the pre-operation state. Provide expected values for relevant fields after the inverse (usually consistent with before the forward operation; if some fields such as timestamps do not roll back, state that separately).

**Forward operation**: {forward_event_label}
**Inverse operation**: {inverse_event_label}
**Relevant data entity values before the operation**: {before_values}
**Relevant data entity values after the forward operation**: {after_forward_values}
**Subsequent states and data entities (includes path_index; each item has at least path_index, data_entities[...])**: {subsequent_states_data_entities}

Output expected values per field after the inverse operation. Output strictly in the following JSON format (no other text):
{{
  "effects": [
    {{
      "field_key": "field_key_1",
      "path_index": 3,
      "expected_value": "expected_value_1"
    }},
    {{
      "field_key": "field_key_2",
      "path_index": 5,
      "expected_value": "expected_value_2"
    }}
  ]
}}
"""
