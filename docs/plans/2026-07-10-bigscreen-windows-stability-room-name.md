# Bigscreen Windows Stability And Room Name Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Stabilize JD live bigscreen capture on slower Windows builds and report the right-side account name with capture monitoring events.

**Architecture:** Make browser navigation idempotent and wait for concrete DOM readiness instead of relying on fixed sleeps. Extract the account name in the capture service, carry it through the result and Web task state, then place it in the existing monitoring `extra` object without changing the remote contract.

**Tech Stack:** Python 3.9+, Playwright sync API, Flask, unittest

---

### Task 1: Stabilize bigscreen browser interactions

**Files:**
- Modify: `live-bigscreen-capture/tests/test_browser.py`
- Modify: `live-bigscreen-capture/bigscreen_capture/browser.py`

**Step 1: Write the failing tests**

Add tests proving that target locators wait for visibility, a selected sidebar is not clicked again, and `check_login_status` returns false when the shopping account passes but the live bigscreen never becomes ready.

**Step 2: Run tests to verify they fail**

Run: `cd live-bigscreen-capture && python3 -m unittest tests.test_browser -v`

Expected: FAIL because current locators use immediate `count()`, sidebar navigation always clicks, and login checks only the shared JD account.

**Step 3: Write minimal implementation**

Add a bounded locator wait helper, scope sidebar and metric selectors to their component containers, skip clicks for selected sidebars, and validate bigscreen readiness after the shared JD login check.

**Step 4: Run tests to verify they pass**

Run: `cd live-bigscreen-capture && python3 -m unittest tests.test_browser -v`

Expected: PASS.

**Step 5: Commit**

```bash
git add live-bigscreen-capture/tests/test_browser.py live-bigscreen-capture/bigscreen_capture/browser.py
git commit -m "fix: stabilize bigscreen capture on windows"
```

### Task 2: Carry the live room account name in capture results

**Files:**
- Modify: `live-bigscreen-capture/tests/test_service.py`
- Modify: `live-bigscreen-capture/bigscreen_capture/service.py`

**Step 1: Write the failing test**

Add a fake browser account-name result and assert `CaptureOnceResult.room_name` equals `京东青春采销`.

**Step 2: Run test to verify it fails**

Run: `cd live-bigscreen-capture && python3 -m unittest tests.test_service -v`

Expected: FAIL because `CaptureOnceResult` has no `room_name` field.

**Step 3: Write minimal implementation**

Read `[class*="header-index-currentUserName"]` after bigscreen readiness and add the value to `CaptureOnceResult`.

**Step 4: Run tests to verify they pass**

Run: `cd live-bigscreen-capture && python3 -m unittest tests.test_service -v`

Expected: PASS.

**Step 5: Commit**

```bash
git add live-bigscreen-capture/tests/test_service.py live-bigscreen-capture/bigscreen_capture/service.py
git commit -m "feat: capture live room account name"
```

### Task 3: Report the room name in monitoring events

**Files:**
- Modify: `live-web/tests/test_usage_reporting_routes.py`
- Modify: `live-web/tests/test_routes.py`
- Modify: `live-web/app.py`

**Step 1: Write the failing tests**

Set `FakeCaptureResult.room_name` and assert `task_finish.extra.room_name`, current status, and current-session `download.extra.room_name` all use the account name.

**Step 2: Run tests to verify they fail**

Run: `cd live-web && python3 -m unittest tests.test_usage_reporting_routes tests.test_routes -v`

Expected: FAIL because Web task state and monitoring extras currently only carry `room_id`.

**Step 3: Write minimal implementation**

Store the first non-empty result name in bigscreen status, then include it in finish and download event extras.

**Step 4: Run tests to verify they pass**

Run: `cd live-web && python3 -m unittest tests.test_usage_reporting_routes tests.test_routes -v`

Expected: PASS.

**Step 5: Commit**

```bash
git add live-web/tests/test_usage_reporting_routes.py live-web/tests/test_routes.py live-web/app.py
git commit -m "feat: report bigscreen room name"
```

### Task 4: Full verification

**Files:**
- Verify: all files changed above

**Step 1: Run module regressions**

Run:

```bash
cd live-bigscreen-capture && python3 -m unittest discover -s tests -p "test_*.py" -v
cd ../live-web && python3 -m unittest discover -s tests -p "test_*.py" -v
cd .. && python3 -m unittest discover -s tests -p "test_*.py" -v
```

Expected: all tests PASS.

**Step 2: Run static checks**

Run: `git diff --check && git status --short`

Expected: no whitespace errors and only intentional changes.
