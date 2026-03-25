# MR-Data data side-effect inference (verifier-side LLM) prompt

MR_DATA_SIDE_EFFECT_PROMPT = """You are a mobile application testing expert. An input mutation is known: on a page with data entities, input changed from v to v'. Infer which data fields in subsequent states will change because of this input mutation, and their new expected values.

**Page intent**: {page_intent}
**State/event where mutation occurred**: {mutation_state_event}
**Input field identifier**: {input_label}
**Mutation**: v = "{original_value}" -> v' = "{new_value}"
**Subsequent states and data entities per state (includes path_index; each item has at least path_index, data_entities[...])**:
{subsequent_states_data_entities}

Output fields that will change due to this input mutation and their new expected values. Analyze all data entities carefully, understand their meaning, and include only fields you are reasonably confident will change—do not guess.
Output strictly in the following JSON format (no other text):
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
If no fields change, output: {{"effects": []}}
"""
