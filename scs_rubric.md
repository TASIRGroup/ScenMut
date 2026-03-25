## Human Scoring Rubric of Semantic Consistency Score (SCS)

### D1 Business Scenario Coherence

| Score | Description |
|-------|-------------|
| **2** | **Fully Coherent:** The operation sequence reconstructs a complete and realistic user interaction scenario (e.g., "login → search → add to cart → checkout"), with clear causal business relationships between consecutive steps, such that the removal of any single step would render subsequent steps meaningless. |
| **1** | **Partially Coherent:** The majority of steps exhibit business-level associations, but contain skipped transitions or isolated operations (e.g., a "view help page" click interspersed within a "create order" workflow with no semantic relevance to the primary flow). |
| **0** | **Incoherent:** The step sequence is assembled arbitrarily or driven purely by structural traversal (e.g., exhaustively iterating over all interactive controls), bearing no correspondence to any genuine user intent. |

> **Anchor question:** Can the test be described in a single sentence specifying *what type of user* it simulates and *what task* that user is performing?

### D2 Functional Coverage Precision

| Score | Description |
|-------|-------------|
| **2** | **Precise Coverage:** Test steps directly target the application's core functional paths (e.g., "edit personal information and save" rather than randomly clicking through settings), with each operation serving an explicit functional verification objective. |
| **1** | **Inefficient Coverage:** The target functional area is addressed, but the test contains substantial redundant or circuitous operations that dilute the core functionality under test (e.g., traversing all available tabs upon entering a feature page before executing the target operation). |
| **0** | **Unprecise Coverage:** The functional areas covered by the test path are indistinguishable from random exploration, and no specific business functionality point can be identified as the subject of verification. |

> **Anchor question:** For each individual step, is there a discernible functional verification rationale that justifies its inclusion?

### D3 Semantic Validity of Test Data

| Score | Description |
|-------|-------------|
| **2** | **Semantically Valid:** All input data (e.g., usernames, prices, dates) fall within the business-permissible range for their respective fields and are contextually consistent with the scenario (e.g., a purchase quantity of 1 rather than 0 or 999,999), with no internal contradictions among data values. |
| **1** | **Partially Valid:** The majority of input values are reasonable, but isolated instances of semantically inappropriate data are present (e.g., entering Chinese characters in a numeric-only field, or supplying a negative quantity), which would trigger validation errors in a real-world context. |
| **0** | **Semantically Invalid:** Meaningless placeholders or extreme values far outside business boundaries are used pervasively, rendering the data entirely disconnected from the scenario. |

> **Anchor question:** Do these input values resemble data that a genuine user would realistically enter?

### D4 Business Reasonableness of State Transitions

| Score | Description |
|-------|-------------|
| **2** | **Reasonable Transitions:** The page navigation sequence conforms to the application's standard business workflow, with no state transitions that are business-logically contradictory (e.g., navigating backward from a "payment successful" page into a "product detail" page to re-initiate a purchase, unless back-navigation is explicitly the scenario under test). |
| **1** | **Locally Anomalous:** Isolated unnatural page transitions occur (e.g., circumnavigating to unintended pages through repeated back-navigation), but the overall directional integrity of the business workflow is preserved. |
| **0** | **Transition Disorder:** The page navigation sequence does not conform to any recognizable business workflow. |

> **Anchor question:** At which step would a test engineer reviewing this path first experience a sense that "something is wrong here"?

### D5 Assertion Validity and Business Relevance

| Score | Description |
|-------|-------------|
| **2** | **Valid Assertions:** Assertions are present and directly verify the core business outcome of the target functionality (e.g., "after order submission, assert that the order number appears in the order list"), with a clearly established logical relationship between expected values and test data. |
| **1** | **Weakened Assertions:** Assertions are present but verify only surface-level states (e.g., "whether the page title contains a given string," "whether a button is visible"), failing to validate the actual data side effects produced by the operation; alternatively, expected values in assertions bear no relationship to input data (i.e., are hard-coded). |
| **0** | **Absent or Invalid Assertions:** No assertions are present (crash detection only), or assertions are demonstrably trivial (e.g., asserting a condition that is necessarily true), providing zero functional correctness verification. |

> **Anchor question:** If the application were to silently modify a particular piece of business logic, would this assertion be capable of detecting the change?

### Total Score and Rating

**Total Score = D1 + D2 + D3 + D4 + D5; each dimension is scored 0–2, for a maximum of 10 points.**

### Scoring Operational Guidelines

- **Independent scoring and deliberation:** Each test case is scored independently by two raters; scores are averaged. A inter-rater discrepancy of ≥ 3 points necessitates structured discussion and reconciliation.
- **Anchor examples:** Prior to scoring, raters are provided with calibration samples — at minimum one representative case at each score level (0, 1, and 2) per dimension — to establish a shared understanding of scoring criteria.
- **Blind review:** Raters are kept unaware of the provenance of each test case (e.g., whether it originates from a baseline or from ScenMut) to prevent source-based bias from influencing scores.
- **Exclusion of executability interference:** Scoring targets the test case itself (path and assertions) and does not consider execution outcomes (i.e., pass or fail status).
- **No penalty for justified complexity:** A high step count does not imply semantic incoherence; raters must distinguish between "multi-step workflows that are business-necessary" and "purposeless random traversal."
- **Distinction between execution failures and semantic errors:** If a test case produces an assertion failure attributable to an application defect, the semantic consistency score must not be reduced; semantic scoring evaluates the soundness of design intent exclusively, not execution outcomes.