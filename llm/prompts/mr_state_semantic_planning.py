# MR-State semantic planning (generator): from a local candidate subgraph, one call produces 3–10 diverse intent sequences.
# Input: insertion context (A, B state semantics), semantic summaries of local subgraph edges (with edge identifiers).
# Output: multiple intent sequences; each is a list of natural-language steps with edge_id for semantic alignment.

MR_STATE_SEMANTIC_PLANNING_PROMPT = """You are a mobile application testing expert. On a test path, the current step intent is **intent_k** and the next step intent is **intent_k_plus_1**. Plan several "sub-scenario paths" between them. Each path is a sequence of natural-language step intents; every step must correspond to one of the edge identifiers (edge_id) below so the system can map your output to real paths in the graph.

**Insertion context**
- Current step intent (leaving A): {intent_k}
- Next step intent (entering B): {intent_k_plus_1}

**Local candidate subgraph edge list** (you may only compose paths from these edges; each has a unique identifier):
{edges_semantic_list}

**Requirements**
1. Produce 0–10 distinct "intent sequences". Each sequence has 1–6 natural-language steps; use arrows to show order between steps.
2. Every step in a sequence must match some edge_id above (e.g. E1, E2), and the sequence must be connected on the graph: the "arrival state" of step i equals the "departure state" of step i+1; the first step departs from A (current step), and the last step arrives at B (next step).
3. Paths should be semantically plausible and match user habits. If no reasonable intent sequence exists, return an empty list.
4. Diversify (e.g. open settings → change avatar → save; browse product → add to cart → view cart).
5. Paths should preferably help surface potential defects.

Output **only** JSON, no other text. Format:
{{
  "intent_sequences": [
    [
      {{ "description": "natural-language step description", "edge_id": "Enumber" }},
      ...
    ],
    ...
  ]
}}

Example: if edges include E1(from [Home] to [Profile]), E2(from [Profile] to [Settings]), E3(from [Settings] to [Avatar]), a valid sequence is:
[{{ "description": "Open profile", "edge_id": "E1" }}, {{ "description": "Open settings", "edge_id": "E2" }}, {{ "description": "Change avatar", "edge_id": "E3" }}]
"""
