# MR-Data input data generation (generator-side LLM) prompt

MR_DATA_GENERATION_PROMPT = """You are a mobile application testing expert. Based on the current page intent and input semantics, generate semantically equivalent mutated values for input fields for metamorphic testing.

**Current page intent**: {page_intent}
**Input semantics / field name**: {input_label}
**Action event semantic label**: {event_label}
**Current value**: {current_value}
**Field type**: {field_type}
**Required or not**: {required_hint}

Produce semantically valid, testable mutated values. Strategies include: equivalent-class substitution, boundary values, special characters, substring replacement. You may give one representative value per strategy.
Requirements: do not generate empty values for required fields; do not generate non-numeric values for numeric fields.

Output strictly in the following JSON format (no other text):
{{
  "variants": [
    {{ "value": "<string value>", "strategy": "equivalent_class" }},
    {{ "value": "<string value>", "strategy": "boundary" }},
    {{ "value": "<string value>", "strategy": "special_char" }},
    {{ "value": "<string value>", "strategy": "substring" }}
  ]
}}
strategy must be one of: equivalent_class, boundary, special_char, substring.
If a strategy does not apply, you may omit it, but return at least one variant.
"""
