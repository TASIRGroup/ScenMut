# MR-State side-effect inference (verifier-side LLM) prompt

MR_STATE_SIDE_EFFECT_PROMPT = """You are a mobile application testing expert. On a test path, a sub-scenario [intent_new_1, ..., intent_new_j] was injected between intent_k and intent_{{k+1}}, with key events and data changes inside the sub-scenario. Infer which fields in subsequent states are affected after injection and their new expected values.

**Current step intent**: {intent_k}
**Next step intent**: {intent_k_plus_1}
**Injected sub-scenario intent list**: {injected_intents}
**Summary of key events and data changes in the sub-scenario**: {injected_events_and_effects}
**Subsequent states and data entities (includes path_index; each item has at least path_index, data_entities[...])**: {subsequent_states_data_entities}

Output fields affected by the injection and their new expected values. Output strictly in the following JSON format (no other text):
{{
  "effects": [
    {{
      "field_key": "field_key_1",
      "path_index": 3,
      "expected_value": "new_expected_value_1"
    }},
    {{
      "field_key": "field_key_2",
      "path_index": 5,
      "expected_value": "new_expected_value_2"
    }}
  ]
}}
If no fields are affected, output: {{"effects": []}}
"""
