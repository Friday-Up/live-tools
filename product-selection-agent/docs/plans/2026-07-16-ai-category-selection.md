# AI Category Selection Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Send every category's complete candidate pool (up to 30 products) to AI once and let AI return an ordered, quality-filtered selection of at most 10 products, while preserving a fully auditable candidate-pool output.

**Architecture:** `selector.py` will build a ranked candidate pool instead of prematurely cutting to Top10. `recommender.py` will perform one selection request per category and validate the returned SKU order. `main.py` will separate `candidate_pool`, final `selection`, `recommendation`, diagnostics, and Excel exports; rule scoring remains an explicit fallback only.

**Tech Stack:** Python 3.9, standard-library `unittest`, OpenAI-compatible Chat Completions over `urllib`, SSE streaming, `openpyxl`.

---

### Task 1: Build a 30-item candidate pool

**Files:**
- Modify: `selector.py`
- Modify: `config.py`
- Test: `tests/test_core.py`

**Step 1: Write the failing test**

Add a test that creates 35 products in one category and asserts `build_candidate_pool()` returns 30, preserves a `candidate_rank`, and does not label those 30 as final Top10.

**Step 2: Run test to verify it fails**

Run: `python3 -m unittest tests.test_core.SelectionAndRecommendationTest.test_candidate_pool_keeps_up_to_thirty -v`

Expected: FAIL because `build_candidate_pool` does not exist.

**Step 3: Write minimal implementation**

Add `build_candidate_pool(items, max_candidates=None)` that reuses the existing dedup/group/sort logic, defaults to `MAX_CANDIDATES_PER_CATEGORY`, and writes `candidate_rank`. Keep `select_top()` as a compatibility wrapper when a rule Top10 is explicitly needed.

Update comments so `TOP_N_PER_CATEGORY` means final recommendation limit and `MAX_CANDIDATES_PER_CATEGORY` means AI input limit.

**Step 4: Run test to verify it passes**

Run the targeted test and then `python3 -m unittest discover -s tests -q`.

### Task 2: Define and validate the AI selection protocol

**Files:**
- Modify: `recommender.py`
- Test: `tests/test_core.py`

**Step 1: Write failing protocol tests**

Add tests for a response shaped as:

```python
{
    "selected": [
        {"sku_id": "7", "rank": 1, "reason": "相关且热销", "copy": "推荐文案"},
        {"sku_id": "2", "rank": 2, "reason": "价格有优势", "copy": "推荐文案"},
    ],
    "rejected": [{"sku_id": "1", "reason": "凑单专属"}],
    "shortfall_reason": "仅 2 个候选符合要求",
}
```

Assert unknown SKUs are dropped, duplicates are deduplicated, selected products are limited to 10, and selected order follows AI rank. Assert omitted candidates receive the default rejection reason.

**Step 2: Run tests to verify they fail**

Expected: FAIL because the current parser only understands `items` and does not model selected/rejected decisions.

**Step 3: Implement protocol helpers**

Add a response normalizer that returns:

```python
{
    "selected": [...validated decisions...],
    "rejected": {"sku": "reason"},
    "shortfall_reason": "...",
    "warnings": [...],
}
```

Only candidate SKUs may survive. Normalize rank locally from the returned order after sorting valid explicit ranks. Do not treat fewer than 10 selections as an error.

**Step 4: Run targeted and full tests**

Run: `python3 -m unittest discover -s tests -q`.

### Task 3: Send one complete category per model request

**Files:**
- Modify: `recommender.py`
- Modify: `config.py`
- Test: `tests/test_core.py`

**Step 1: Write failing behavior tests**

Add tests asserting:

- a 30-candidate category reaches the mocked model in one call;
- AI may return 7 products without a retry;
- returned AI order becomes final product order;
- a zero-item selection with `shortfall_reason` is valid;
- a network timeout falls back to rule Top10 and remains eligible for the existing network circuit breaker.

**Step 2: Run tests to verify they fail**

Expected: FAIL because the current recommender cuts to rule Top10 and retries missing SKUs.

**Step 3: Implement one-request category selection**

Replace Top10 copy enhancement with one category-selection request. Prompt AI to reject category mismatches, add-on-only products, service links, gifts, and non-products before considering sales, discount, price, and page/rank position.

The request facts must include only captured fields: SKU, name, prices, sales text/number, discount, source rank, good rate, self-operated flag, selling points, shop, and board name.

Remove missing-SKU compensation retries because omission now means rejection. Keep 5 category workers and the global 5 RPS limiter. Preserve the network-only circuit breaker.

**Step 4: Run targeted and full tests**

Run: `python3 -m unittest discover -s tests -q`.

### Task 4: Separate candidate pool from final selection

**Files:**
- Modify: `main.py`
- Test: `tests/test_core.py`

**Step 1: Write failing output tests**

Test a small synthetic run and assert:

- `candidate_pool` contains every candidate;
- `selection` contains only final recommended products;
- `recommendation` records `shortfall_reason` and protocol warnings;
- diagnostics contain candidate count, selected count, and short categories with reasons.

**Step 2: Run tests to verify they fail**

Expected: FAIL because the current payload has no `candidate_pool` and treats pre-AI Top10 as `selection`.

**Step 3: Implement payload assembly**

Build the candidate pool first, run recommendation on that pool, derive final selection from recommendation products, and calculate diagnostics against both structures. Update the contract string to state “每类目 AI 从最多 30 个候选中筛选最多 10 个；合格不足不补齐”.

**Step 4: Run targeted and full tests**

Run: `python3 -m unittest discover -s tests -q`.

### Task 5: Add auditable Excel output and documentation

**Files:**
- Modify: `main.py`
- Modify: `README.md`
- Test: `tests/test_core.py`

**Step 1: Write a failing workbook test**

Generate a temporary workbook and assert it contains `候选池`, `选品明细`, `推荐结果`, and `运行诊断`. Assert candidate rows include AI status, AI rank, rejection reason, and shortfall information.

**Step 2: Run test to verify it fails**

Expected: FAIL because `候选池` does not exist.

**Step 3: Implement workbook and README changes**

Add the candidate sheet without removing the existing final-result sheets. Document the one-request-per-category behavior, fewer-than-10 semantics, fallback behavior, and new JSON/Excel fields.

**Step 4: Run targeted and full tests**

Run: `python3 -m unittest discover -s tests -q`.

### Task 6: End-to-end verification

**Files:**
- Verify: `recommender.py`, `selector.py`, `main.py`, `config.py`, `README.md`, `tests/test_core.py`

**Step 1: Run all automated checks**

Run:

```bash
python3 -m unittest discover -s tests -v
python3 -m compileall -q .
```

Expected: all tests pass and compilation exits 0.

**Step 2: Run a real model smoke test**

Send one representative 30-item category to the configured model. Verify one request returns at most 10 valid candidate SKUs, preserves AI order, and records shortfall/rejections without a compensation retry.

**Step 3: Inspect the artifact contract**

Verify JSON counts and workbook sheet names programmatically. Confirm no secrets are written to output.

**Step 4: Commit only project files changed for this feature**

Because the project directory was initially untracked in the parent repository, inspect status carefully and stage exact paths only; never include model configuration, generated output, browser state, or unrelated `live` projects.
