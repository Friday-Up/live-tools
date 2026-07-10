# Bigscreen DOM Click Verification Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Keep 80% bigscreen zoom while making every Windows interaction independent of screen coordinates and verified after each click.

**Architecture:** Route all business actions through a DOM click helper using `element.click()`. Add bounded state polling and one retry for sidebar, tab, metric, dropdown, and product-sort actions so failed transitions stop quickly instead of cascading through later screenshots.

**Tech Stack:** Python 3.9, Playwright sync API, unittest

---

### Task 1: Replace coordinate clicks with DOM clicks

**Files:**
- Modify: `live-bigscreen-capture/tests/test_browser.py`
- Modify: `live-bigscreen-capture/bigscreen_capture/browser.py`

**Step 1: Write failing tests**

Add tests asserting sidebar, overview tab, flow metric, dropdown trigger, dropdown option, and table header actions use `evaluate("el => el.click()")`. Existing `click(force=True)` calls must make these tests fail.

**Step 2: Verify RED**

Run: `cd live-bigscreen-capture && python3 -m unittest tests.test_browser -v`

Expected: FAIL because production code still records coordinate click calls.

**Step 3: Implement DOM click helper**

Add a single `_dom_click(locator)` helper and route all business clicks through it. Keep `page_zoom="80%"` unchanged.

**Step 4: Verify GREEN**

Run: `cd live-bigscreen-capture && python3 -m unittest tests.test_browser -v`

Expected: PASS.

**Step 5: Commit**

```bash
git add live-bigscreen-capture/bigscreen_capture/browser.py live-bigscreen-capture/tests/test_browser.py
git commit -m "fix: use dom clicks for bigscreen controls"
```

### Task 2: Verify click state and retry once

**Files:**
- Modify: `live-bigscreen-capture/tests/test_browser.py`
- Modify: `live-bigscreen-capture/bigscreen_capture/browser.py`

**Step 1: Write failing tests**

Add tests for first-click failure followed by second-click success, and two failed clicks producing a clear runtime error. Cover sidebar selected state, overview radio checked state, flow metric selected state, and dropdown selected text.

**Step 2: Verify RED**

Run: `cd live-bigscreen-capture && python3 -m unittest tests.test_browser -v`

Expected: FAIL because the current implementation does not verify transitions.

**Step 3: Implement bounded verification**

Add short state polling with a 3-second timeout and 200 ms interval. Click at most twice. Preserve the existing 15-second wait only for locating/loading page elements, not for confirming a click that already happened.

**Step 4: Verify GREEN**

Run: `cd live-bigscreen-capture && python3 -m unittest tests.test_browser -v`

Expected: PASS and no coordinate click calls.

**Step 5: Commit**

```bash
git add live-bigscreen-capture/bigscreen_capture/browser.py live-bigscreen-capture/tests/test_browser.py
git commit -m "fix: verify bigscreen control transitions"
```

### Task 3: Full regression and release readiness

**Files:**
- Verify all changed files

**Step 1: Run regressions**

Run the complete `live-bigscreen-capture`, `live-web`, and root test suites plus `compileall` and `git diff --check`.

**Step 2: Review behavior**

Confirm 80% zoom is unchanged, no `locator.click(force=True)` remains in bigscreen browser actions, failed transitions retry once, and screenshot/file formats are untouched.

**Step 3: Integrate and publish**

After verification, merge to `master`, push, tag the next patch release, wait for the Windows Action, and verify the Release ZIP.
