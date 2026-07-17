# Playwright No-Shell Packaging Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Remove Chromium Headless Shell from Windows and macOS packages while preserving all headless and headed browser workflows through Playwright's Chromium channel.

**Architecture:** Keep the full Playwright Chrome for Testing binary and launch it with `channel="chromium"` for both headed and headless calls. Install Chromium with `--no-shell`, then make both packaging workflows fail if a Headless Shell directory appears in the final package.

**Tech Stack:** Python 3.11, Playwright Python, unittest, PyInstaller, GitHub Actions PowerShell/Bash.

---

### Task 1: Switch runtime launches to the Chromium channel

**Files:**
- Modify: `live-sku-price-audit/tests/test_browser_manager.py`
- Modify: `product-selection-agent/tests/test_core.py`
- Modify: `live-sku-price-audit/utils/browser_manager.py:78-84`
- Modify: `product-selection-agent/product_selection_agent/fetcher.py:561-562,589-590`

**Step 1: Write the failing tests**

- Change the BrowserManager launch expectation to `{"headless": True, "channel": "chromium"}`.
- Assert both isolated选品 browser helpers call `launch(headless=True, channel="chromium")`.

**Step 2: Run tests to verify they fail**

Run:

```bash
(cd live-sku-price-audit && python3 -m unittest tests.test_browser_manager.BrowserManagerLoginTests.test_start_passes_headless_flag_to_chromium_launch -v)
(cd product-selection-agent && python3 -m unittest tests.test_core.SourceAdapterTest -v)
```

Expected: FAIL because current calls do not provide the `channel` argument.

**Step 3: Write minimal implementation**

Add `channel="chromium"` to the shared BrowserManager launch kwargs and both selection launch calls. Do not change `headless`, args, contexts, or business logic.

**Step 4: Run tests to verify they pass**

Run the two commands from Step 2. Expected: PASS.

**Step 5: Commit**

```bash
git add live-sku-price-audit/utils/browser_manager.py live-sku-price-audit/tests/test_browser_manager.py product-selection-agent/product_selection_agent/fetcher.py product-selection-agent/tests/test_core.py
git commit -m "refactor: use Chromium channel for browser launches"
```

### Task 2: Remove Headless Shell from packaged browsers

**Files:**
- Modify: `tests/test_windows_packaging.py`
- Modify: `tests/test_macos_packaging.py`
- Modify: `.github/workflows/build-windows.yml`
- Modify: `.github/workflows/build-macos.yml`

**Step 1: Write the failing tests**

- Require both workflows to run `playwright install chromium --no-shell`.
- Require Windows verification to reject `chromium_headless_shell*` directories.
- Require macOS verification to reject `chromium_headless_shell*` directories from copied browser cache.

**Step 2: Run tests to verify they fail**

```bash
python3 -m unittest tests.test_windows_packaging tests.test_macos_packaging -v
```

Expected: FAIL because workflows still install and accept Headless Shell.

**Step 3: Write minimal implementation**

- Add `--no-shell` to both install steps.
- Add final package checks that print the unexpected directory and fail the build.

**Step 4: Run tests to verify they pass**

Run the command from Step 2. Expected: PASS.

**Step 5: Commit**

```bash
git add .github/workflows/build-windows.yml .github/workflows/build-macos.yml tests/test_windows_packaging.py tests/test_macos_packaging.py
git commit -m "build: omit Playwright Headless Shell"
```

### Task 3: Full verification and packaged builds

**Files:**
- Verify only; no intended production edits.

**Step 1: Run all repository tests**

Run every module's unittest suite plus root tests. Expected: all pass.

**Step 2: Validate workflow syntax and diff**

Run YAML parsing, `git diff --check`, and secret packaging tests. Expected: exit 0.

**Step 3: Merge to master and push**

Merge the implementation branch into `master` and push to trigger Windows and macOS workflows.

**Step 4: Monitor GitHub Actions**

Wait for Windows, Intel macOS, and Apple Silicon macOS builds. Confirm runtime smoke checks, no-shell package checks, signing, archive verification, and artifact uploads all pass.

**Step 5: Compare artifacts**

Record artifact names and compressed sizes and compare with the previous successful run. Report the measured reduction rather than estimating.
