# AI Selection Quality Fixes Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Prevent valid category products from being eliminated for weak commercial metrics, accept legacy model response shapes, and report AI completeness independently from fetch completeness.

**Architecture:** Keep the existing one-request-per-category pipeline. Strengthen the model contract at the prompt boundary, normalize legacy `items` responses into the current `selected` schema, and derive AI-run diagnostics from final recommendation blocks in `main.py`.

**Tech Stack:** Python 3.9, standard-library `unittest`, OpenAI-compatible Chat Completions over `urllib`, SSE streaming, JSON/Excel outputs.

---

### Task 1: Make relevance the only product eligibility gate

**Files:**
- Modify: `recommender.py`
- Test: `tests/test_core.py`

**Step 1:** Write a failing test that captures the generated request and asserts the prompt says low sales, high price, weak discount, missing good rate, and non-self-operated status may only affect ranking and may not eliminate a category-relevant product.

**Step 2:** Run the targeted test and confirm it fails against the current prompt.

**Step 3:** Update the prompt to define hard rejection reasons and require exactly `min(10, relevant valid candidates)` selections. Add concrete medical-device/food and air-conditioner examples. Request rejected details only for hard-filtered candidates to shorten output.

**Step 4:** Run targeted and full tests.

### Task 2: Accept legacy `items` model responses

**Files:**
- Modify: `recommender.py`
- Test: `tests/test_core.py`

**Step 1:** Write failing tests for `{ "items": [...] }` and a top-level array. Assert both normalize to ordered `selected` decisions and add a legacy-protocol warning.

**Step 2:** Run targeted tests and confirm the current `selected` validation rejects them.

**Step 3:** Add a protocol coercion helper before `_normalize_ai_selection`. Preserve only candidate SKUs and require reason/copy. Add a bounded, single-line response preview to parse errors so future malformed output is diagnosable without logging credentials.

**Step 4:** Run targeted and full tests, including cumulative/multiple JSON response regressions.

### Task 3: Separate fetch completeness from AI completeness

**Files:**
- Modify: `main.py`
- Modify: `README.md`
- Test: `tests/test_core.py`

**Step 1:** Write failing tests for one mixed run and one all-AI run. Assert `fetch_complete`, `ai_complete`, and `ai_failed_categories` have independent values and that top-level `ai_complete` mirrors diagnostics.

**Step 2:** Run targeted tests and confirm the fields do not exist.

**Step 3:** Derive AI diagnostics from recommendation blocks and update final console output to print both states. Document the distinction and acceptance criteria.

**Step 4:** Run targeted and full tests.

### Task 4: Verification

**Files:**
- Verify: `recommender.py`, `main.py`, `README.md`, `tests/test_core.py`

**Step 1:** Run `python3 -m unittest discover -s tests -v`.

**Step 2:** Run `python3 -m compileall -q .` and `python3 main.py --help`.

**Step 3:** Re-run representative real model categories from the latest candidate pool where possible: 国家补贴/医疗器械, 国家补贴/空调, and one legacy-format failure category. Verify relevant products are ranked rather than removed for weak metrics and inspect `ai_complete`.

**Step 4:** Do not stage model credentials, generated outputs, browser state, or unrelated untracked files.
