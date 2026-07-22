"""
HEALER AGENT
============
Works like Playwright's healer agent, for Selenium Python:

  run tests → on failure: classify error (SeleniumErrorMap) →
  re-scan the LIVE DOM of every URL the tests touch →
  ask the LLM for a fix → validate the fix (syntax + architecture) →
  write → re-run → repeat until green or retries exhausted.

Guarantees:
- The LAST fix is always verified with a final test run (never
  "fixed and hoped").
- A syntactically broken LLM fix is NEVER written over a working file.
- Locators are only ever added to page objects; By imports are stripped
  from test files automatically.
- With --test, all other test functions are preserved verbatim.
"""

import html as html_lib
import re
import subprocess
import sys
from datetime import datetime
from pathlib import Path

from selenium_agent.utils.logger import setup_logger
from selenium_agent.utils.llm import create_llm_client, DEFAULT_PROVIDER, get_default_model
from selenium_agent.utils.json_utils import extract_json_object, LLMJSONError
from selenium_agent.utils.code_validator import validate_python
from selenium_agent.selenium.error_map import SeleniumErrorMap
from selenium_agent.selenium.locator_scanner import scan_page_locators, format_for_llm

logger = setup_logger("HealerAgent")

PYTEST_TIMEOUT_SECONDS = 900
MAX_PYTEST_OUTPUT_CHARS = 12000
MAX_SCAN_URLS = 3

HEALER_SYSTEM_PROMPT = """
You are an expert Selenium Python debugger. Your job is 360° healing.

You receive:
  1. The failing pytest output. It may contain two high-signal lines:
     FAILURE_URL: <url>         ← the page the browser was ON when it failed
     FAILURE_ERRORS: [...]      ← alert/validation messages visible at failure
                                  (THE most direct clue — read this first)
     FAILURE_PAGE_TEXT: <text>  ← that page's visible text
  2. Real DOM locators scanned from the live page(s)
  3. Current code files (page objects + test files)

══ FORM SUBMITS THAT GO NOWHERE ══
If FAILURE_URL shows the app stayed on the same form page after submit,
the submission was REJECTED — read FAILURE_PAGE_TEXT for validation errors.
The usual cause: required fields were not filled. Fill EVERY input/select
listed in that page's scan block, not just the ones the test already types.

══ ARCHITECTURE RULE — READ THIS FIRST ══

Locators live ONLY in the Page Object class. NEVER in test files.

CORRECT pattern:

  # pages/login_page.py  ← locators go HERE
  class LoginPage(BasePage):
      URL = 'https://www.saucedemo.com'
      USERNAME_INPUT  = (By.CSS_SELECTOR, '#user-name')
      PASSWORD_INPUT  = (By.CSS_SELECTOR, '#password')
      LOGIN_BUTTON    = (By.CSS_SELECTOR, '[data-test="login-button"]')
      ERROR_MESSAGE   = (By.CSS_SELECTOR, '[data-test="error-button"]')

  # tests/test_login.py  ← use class attribute names, no By here
  def test_login(driver):
      page = LoginPage(driver)
      page.open(LoginPage.URL)
      page.fluent_wait(page.USERNAME_INPUT, 'visible')
      page.type(page.USERNAME_INPUT, 'standard_user')
      page.click(page.LOGIN_BUTTON)
      assert page.is_visible(page.ERROR_MESSAGE)

WRONG — NEVER DO THIS:
  # test file using By directly → FORBIDDEN
  page.fluent_wait((By.CSS_SELECTOR, '[data-test="login-button"]'), 'clickable')  ✗
  page.click((By.CSS_SELECTOR, '#user-name'))  ✗

  # test file importing By → FORBIDDEN
  from selenium.webdriver.common.by import By  ✗  (only in page objects)

══ HOW TO FIX EACH ERROR TYPE ══

AttributeError: 'LoginPage' has no attribute 'X'
  → Add missing locator to the PAGE OBJECT class:
     X = (By.CSS_SELECTOR, '<selector from DOM scan>')
  → Test file already calls page.X correctly — do NOT change test file for this

NoSuchElementException / TimeoutException
  → Wrong selector in page object. Fix the tuple value using DOM scan.
  → Change only the page object, not the test.

TimeoutException on wait_for_url(...)
  → The app probably does NOT navigate — SPAs show results on the SAME page.
  → Do NOT increase the timeout. Remove wait_for_url and assert an in-page
    success indicator instead: a status element from the DOM scan whose text
    changes (e.g. a status badge), or a success message element.
  → wait_for_text(locator, 'expected') is available on BasePage for this.

AttributeError: method not found
  → Fix method call in test to use correct BasePage methods:
     self.fluent_wait(locator, 'visible'|'clickable'|'present'|'invisible')
     self.find()  self.click()  self.type()  self.get_text()
     self.wait_for_url()  self.is_visible()  self.open()  self.safe_type()
  NEVER: find_element(), wait_for_element_visible(), time.sleep()

METHOD SIGNATURES — locator is ALWAYS a (By.X, 'selector') tuple:
  wait_for_text(LOCATOR_TUPLE, 'expected text')   ✓
  wait_for_text('h3', 'expected text')            ✗ raw string is not a locator
  wait_for_url('url-fragment')                    ← the ONLY string-taking wait

DRIVER / FIXTURES:
  conftest.py provides the `driver` fixture — test functions accept `driver`
  as a parameter. NEVER define a driver fixture in a test file, NEVER
  import/call DriverFactory in test files, NEVER create drivers manually.
  "fixture 'driver' not found" → the test file broke this rule; restore the
  plain `def test_x(driver):` signature.

AssertionError
  → Read the assertion and the actual value in the output. Decide whether the
    expectation is wrong (fix assertion) or the app state was not reached
    (fix waits / navigation before the assertion).
  → DOM-scan text is the page's PRE-ACTION state. Never assert pre-action
    text (e.g. "STANDBY") as the post-action outcome — assert the CHANGED
    state the scenario expects (e.g. "AUTHENTICATED", a success message).
  → When reading a "LABEL: value" element to use its value, strip the label:
    value = page.get_text(LOCATOR).split(':', 1)[-1].strip()

ImportError
  → Fix import path. Never add sys.path.

StaleElementReferenceException
  → Re-fetch using fluent_wait in page object method.

══ LOCATOR RULES ══
  - CSS preferred over XPath
  - Use ONLY selectors from the DOM scan — never guess
  - The scan is grouped per page (═══ PAGE: <url> ═══). When fixing a page
    object, use ONLY locators from THAT page's block — NEVER borrow a
    locator from a different page's block (it will not exist on this page)
  - NEVER use a selector marked "NOT UNIQUE" for a single element
  - Format in page object: NAME = (By.CSS_SELECTOR, 'selector')
  - test files reference by name: page.NAME — no By, no raw strings

══ TEST DATA ══
  - Errors like "already taken" / "already exists" / "already associated"
    mean the test data is HARDCODED and collides with a previous run.
    Fix: generate unique values at runtime in the test:
      import uuid
      unique = uuid.uuid4().hex[:8]
      email = "qa." + unique + "@example.com"
  - "password has appeared in a data leak" / "password too weak" means the
    password is a common pattern (Password@123 etc.) — breach-list checks
    reject it. Fix: password = "Xk9#" + unique + "!Qz" (strong AND unique).

══ CAPTCHA / BOT PROTECTION ══
  If the DOM scan reports CAPTCHA/bot protection on a page, the flow is
  blocked BY DESIGN — no locator or wait fix will make it pass, and captcha
  must never be bypassed. Return {"fixed_files": [], "fix_summary":
  "BLOCKED: captcha/bot protection on <url> — run against an environment
  with captcha disabled"} instead of changing code.

══ FILE RULES ══
  - Return COMPLETE files — never truncate, never drop functions
  - Fix all issues in one pass
  - If AttributeError on missing locator: fix page object file, preserve test file

REQUIRED IMPORTS in page objects only:
  from selenium.webdriver.common.by import By
  from selenium_agent.selenium.base_page import BasePage

REQUIRED IMPORTS in test files:
  import pytest
  from selenium_agent.selenium.driver_factory import DriverFactory
  from pages.login_page import LoginPage
  # NO 'from selenium.webdriver.common.by import By' in test files

Respond with valid JSON only:
{"fixed_files": [{"filename": "pages/login_page.py", "content": "..."}], "fix_summary": "..."}

filename must be relative: "pages/login_page.py" or "tests/test_login.py"
NEVER include the output_dir prefix.
"""

HEALER_SYSTEM_PROMPT_TARGETED = """
You are an expert Selenium Python debugger doing a SURGICAL fix.

══ ARCHITECTURE RULE — READ THIS FIRST ══

Locators live ONLY in the Page Object class. NEVER in test files.

  # pages/login_page.py  ← locators go HERE as class constants
  class LoginPage(BasePage):
      ERROR_MESSAGE = (By.CSS_SELECTOR, '[data-test="error-button"]')

  # tests/test_login.py  ← reference by name only, NO By import
  assert page.is_visible(page.ERROR_MESSAGE)

NEVER add By or raw locator tuples in test files.

══ YOUR TASK ══
Fix ONE specific test function (indicated below).
  1. If the fix requires a new/corrected locator → add/fix it in the PAGE OBJECT
  2. Return COMPLETE content for every file you change
  3. ALL other test functions must be preserved exactly as-is
  4. Do NOT drop imports, fixtures, or class definitions

Common fixes:
  AttributeError has no attribute X  → add X to page object class, NOT test file
  NoSuchElementException             → fix locator in page object using DOM scan
  TimeoutException                   → fix locator or increase timeout in page object
  Wrong BasePage method              → use fluent_wait / find / click / type / get_text

LOCATOR PREFERENCE: CSS over XPath. Use DOM scan results — never guess.

Respond with valid JSON only:
{"fixed_files": [{"filename": "pages/login_page.py", "content": "..."}], "fix_summary": "..."}
"""


class HealerAgent:
    def __init__(self, api_key: str, output_dir: str = "generated_tests",
                 max_retries: int = 5, provider: str = DEFAULT_PROVIDER,
                 model: str | None = None, save_report: bool = False):
        resolved_model = model or get_default_model(provider)
        self.client = create_llm_client(provider=provider, api_key=api_key, model=resolved_model)
        self.output_dir = str(Path(output_dir).resolve())
        self.max_retries = max_retries
        self.save_report = save_report

    # ── Path handling ──────────────────────────────────────────────────

    def _resolve_paths(self, file_paths: list[str]) -> dict[str, Path]:
        """Map relative label → absolute Path. CWD-first to avoid double-path bug."""
        resolved: dict[str, Path] = {}
        output_root = Path(self.output_dir)

        for fp in file_paths:
            p = Path(fp)

            if p.is_absolute():
                absolute = p
            else:
                candidates = []
                # Priority 1: path already carries the output_dir prefix
                # ("generated_tests/pages/x.py") — strip it, don't double-join
                if p.parts and p.parts[0] == output_root.name:
                    candidates.append((output_root.parent / p).resolve())
                # Priority 2: resolve against CWD (user typed the path)
                candidates.append((Path.cwd() / p).resolve())
                # Priority 3: resolve against output_dir (internal call)
                candidates.append((output_root / p).resolve())

                absolute = next((c for c in candidates if c.exists()), candidates[-1])

            try:
                label = str(absolute.relative_to(output_root))
            except ValueError:
                label = p.name

            resolved[label] = absolute

        return resolved

    def _read_files(self, resolved: dict[str, Path]) -> dict[str, str]:
        contents: dict[str, str] = {}
        for label, absolute in resolved.items():
            if absolute.exists():
                contents[label] = absolute.read_text(encoding="utf-8")
            else:
                logger.warning(f"⚠️  Not found: {absolute}")
        return contents

    def _write_fixed_file(self, filename: str, content: str,
                          known_files: dict[str, Path]) -> Path:
        output_root = Path(self.output_dir)
        norm = Path(filename)
        if norm.is_absolute():
            destination = norm
        else:
            if filename in known_files:
                destination = known_files[filename]
            else:
                parts = norm.parts
                if parts and parts[0] == output_root.name:
                    norm = Path(*parts[1:])
                destination = (output_root / norm).resolve()

        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_text(content, encoding="utf-8")
        return destination

    # ── Test execution ─────────────────────────────────────────────────

    def _run_tests(self, test_files: list[str], test_filter: str | None = None) -> tuple[bool, str]:
        cmd = [sys.executable, "-m", "pytest"] + test_files + ["-v", "--tb=short"]

        if test_filter:
            cmd += ["-k", test_filter]
            logger.info(f"🎯 Filter: -k '{test_filter}'")

        logger.info(f"🧪 Running: {' '.join(cmd)}")
        try:
            result = subprocess.run(
                cmd, capture_output=True, text=True, timeout=PYTEST_TIMEOUT_SECONDS,
            )
        except subprocess.TimeoutExpired:
            return False, (
                f"pytest timed out after {PYTEST_TIMEOUT_SECONDS}s — "
                f"likely a hung wait or a browser that never loaded."
            )
        output = result.stdout + result.stderr
        return self._is_green(result.returncode == 0, output), output

    @staticmethod
    def _is_green(returncode_ok: bool, output: str) -> bool:
        """
        Green means tests genuinely PASSED — not merely exit code 0.
        pytest exits 0 when every test is SKIPPED, but a generated suite
        full of skip placeholders proves nothing.
        """
        if not returncode_ok:
            return False
        if "Pending:" in output:  # generated skip placeholders = unfinished work
            return False
        m = re.search(r"(\d+) passed", output)
        return bool(m) and int(m.group(1)) >= 1

    @staticmethod
    def _trim_output(output: str) -> str:
        """Keep the tail of pytest output — that's where failures live."""
        if len(output) <= MAX_PYTEST_OUTPUT_CHARS:
            return output
        return "...[output trimmed]...\n" + output[-MAX_PYTEST_OUTPUT_CHARS:]

    # ── Source surgery helpers ─────────────────────────────────────────

    def _extract_function(self, source: str, func_name: str) -> str | None:
        """Extract a single top-level function block from source, or None."""
        lines = source.splitlines(keepends=True)
        start = None
        for i, line in enumerate(lines):
            if re.match(rf'^def {re.escape(func_name)}\b', line):
                start = i
                break
        if start is None:
            return None

        func_lines = [lines[start]]
        for line in lines[start + 1:]:
            if line and line[0] not in (' ', '\t', '\n', '\r', '#'):
                break
            func_lines.append(line)
        return "".join(func_lines)

    def _replace_function(self, source: str, func_name: str, new_func: str) -> str:
        """Replace one function in source; all other content preserved exactly."""
        lines = source.splitlines(keepends=True)
        start = None
        for i, line in enumerate(lines):
            if re.match(rf'^def {re.escape(func_name)}\b', line):
                start = i
                break
        if start is None:
            return source + "\n\n" + new_func

        end = start + 1
        while end < len(lines):
            line = lines[end]
            if line and line[0] not in (' ', '\t', '\n', '\r', '#'):
                break
            end += 1

        new_lines = lines[:start] + [new_func.rstrip('\n') + '\n'] + lines[end:]
        return "".join(new_lines)

    def _sanitize_test_file(self, content: str) -> str:
        """Remove By imports the LLM incorrectly added to test files."""
        lines = content.splitlines(keepends=True)
        cleaned = []
        for line in lines:
            if re.search(r'from selenium\.webdriver\.common\.by import By', line) or \
               re.search(r'from selenium.*import.*\bBy\b', line):
                logger.warning("⚠️  Removed 'By' import from test file (belongs in page object)")
                continue
            cleaned.append(line)
        return "".join(cleaned)

    def _merge_preserve_others(self, original: str, fixed: str, target_func: str) -> str:
        """Restore any functions the LLM dropped during a targeted fix."""
        original_funcs = re.findall(r'^def (\w+)\b', original, re.MULTILINE)
        result = fixed
        for func_name in original_funcs:
            if func_name == target_func:
                continue
            if not re.search(rf'^def {re.escape(func_name)}\b', result, re.MULTILINE):
                logger.warning(f"⚠️  LLM dropped '{func_name}' — restoring from original")
                original_func_body = self._extract_function(original, func_name)
                if original_func_body:
                    result = result.rstrip('\n') + '\n\n\n' + original_func_body
        return result

    # ── Context discovery ──────────────────────────────────────────────

    def _auto_discover_related_files(self, resolved: dict[str, Path]) -> dict[str, Path]:
        """Given test files, auto-discover the page objects they import."""
        output_root = Path(self.output_dir)
        extra: dict[str, Path] = {}

        for label, path in list(resolved.items()):
            if not ("test_" in path.name and path.suffix == ".py" and path.exists()):
                continue

            source = path.read_text(encoding="utf-8")
            imports = re.findall(r'from\s+pages\.?(\w+)?\s+import\s+(\w+)', source)
            for module, _ in imports:
                if not module:
                    continue
                pages_dir = path.parent.parent / "pages"
                candidate = pages_dir / f"{module}.py"
                if candidate.exists() and str(candidate) not in [str(v) for v in resolved.values()]:
                    try:
                        lbl = str(candidate.relative_to(output_root))
                    except ValueError:
                        lbl = candidate.name
                    extra[lbl] = candidate
                    logger.info(f"🔗 Auto-discovered page file: {candidate.name}")

        return extra

    def _extract_urls(self, resolved: dict[str, Path], pytest_output: str = "") -> list[str]:
        """
        Collect the URLs the tests actually touch, best-signal first:
        1. failure-time URLs from pytest output, but ONLY on domains the
           code itself navigates to (filters out pytest/selenium doc links
           that appear in warnings and tracebacks)
        2. URL constants / open()/get() calls in the code files
        """
        from urllib.parse import urlparse

        # URLs the code navigates to — these define the app's domains
        code_urls: list[str] = []
        code_url_re = re.compile(
            r'(?:URL\s*=\s*|self\.open\(|page\.open\(|driver\.get\()[\'"](https?://[^\'"]+)[\'"]',
            re.IGNORECASE,
        )
        for label, path in resolved.items():
            if path.exists() and path.suffix == ".py":
                try:
                    for m in code_url_re.finditer(path.read_text(encoding="utf-8")):
                        url = m.group(1).rstrip("/")
                        if url not in code_urls:
                            code_urls.append(url)
                except Exception:
                    pass
        code_domains = {urlparse(u).netloc for u in code_urls}

        # Failure-time URLs (assertion messages, current_url dumps) — the page
        # the browser was ON when it failed is the best thing to re-scan.
        noise = ("w3.org", "selenium.dev", "docs.pytest.org", "readthedocs",
                 "github.com", "python.org")
        output_urls: list[str] = []
        for m in re.finditer(r'https?://[^\s\'")\]]+', pytest_output):
            url = m.group(0).rstrip('.,;')
            if url not in output_urls and not any(d in url for d in noise):
                output_urls.append(url)

        urls: list[str] = []
        for url in output_urls:
            if urlparse(url).netloc in code_domains and url not in urls:
                urls.append(url)
        for url in code_urls:
            if url not in urls:
                urls.append(url)
        if not urls:  # no code URLs found — trust filtered output URLs
            urls = output_urls

        return urls[:MAX_SCAN_URLS]

    # ── Main heal loop ─────────────────────────────────────────────────

    def _steps_for_feature(self, feature: Path) -> list[Path]:
        """
        Map a .feature file to the step-definition test file(s) that run it.
        A .feature is data, not runnable — when a user passes one to
        --heal-only, the intent is obviously "heal the tests behind it".
        """
        project_root = feature.parent.parent
        candidates: list[Path] = []
        for steps_dir in (project_root / "step_definitions", project_root / "steps",
                          feature.parent):
            if not steps_dir.is_dir():
                continue
            exact = steps_dir / f"test_{feature.stem}_steps.py"
            if exact.exists():
                return [exact]
            for f in steps_dir.glob("test_*.py"):
                try:
                    if feature.name in f.read_text(encoding="utf-8"):
                        candidates.append(f)
                except Exception:
                    continue
        return candidates

    def heal(self, saved_files: list[str], test_filter: str | None = None,
             project_profile=None) -> dict:
        resolved = self._resolve_paths(saved_files)

        # BDD convenience: .feature inputs resolve to their step-definition tests
        output_root = Path(self.output_dir)
        for label, path in list(resolved.items()):
            if path.suffix == ".feature" and path.exists():
                for steps in self._steps_for_feature(path):
                    if all(str(steps) != str(v) for v in resolved.values()):
                        try:
                            lbl = str(steps.relative_to(output_root))
                        except ValueError:
                            lbl = steps.name
                        resolved[lbl] = steps
                        logger.info(f"🔗 {path.name} → step definitions: {steps.name}")

        extra = self._auto_discover_related_files(resolved)
        if extra:
            resolved.update(extra)
            logger.info(f"📎 Added {len(extra)} related file(s) to heal context")

        test_absolutes = [
            str(p) for label, p in resolved.items()
            if "test_" in p.name and p.suffix == ".py"
        ]

        if not test_absolutes:
            logger.warning(
                "⚠️  No runnable test files (test_*.py) among the given paths.\n"
                "   Pass the pytest test file — e.g. tests/test_login.py, or for "
                "BDD the step_definitions/test_<name>_steps.py file.\n"
                "   Page objects and .feature files are healed alongside their "
                "tests automatically."
            )
            return {"status": "no_tests", "attempts": 0, "output": ""}

        if test_filter:
            logger.info(f"🎯 Heal scope: '{test_filter}' only — other tests preserved")

        scan_cache: dict[str, str] = {}
        report: list[dict] = []
        output = ""
        attempt = 0

        # max_retries FIX attempts; every fix is verified by the run at the
        # top of the next loop iteration or by the final verification run.
        for attempt in range(1, self.max_retries + 1):
            logger.info(f"🩺 Heal attempt {attempt}/{self.max_retries}")
            passed, output = self._run_tests(test_absolutes, test_filter=test_filter)

            if passed:
                logger.info("✅ All tests passing!")
                report_file = self._emit_report(report, "passed", attempt)
                return {"status": "passed", "attempts": attempt,
                        "output": output, "report": report,
                        "report_file": report_file}

            logger.warning(f"❌ Failed on attempt {attempt}")
            problem = self._problem_summary(output)
            try:
                fix = self._fix_once(resolved, output, test_filter, scan_cache,
                                     project_profile=project_profile)
            except LLMJSONError as exc:
                logger.error(f"💥 Healer LLM returned unusable JSON: {exc}")
                fix = {"applied": False, "fix_summary": "LLM returned unusable JSON",
                       "files": []}
            report.append({"attempt": attempt, "problem": problem,
                           "fix": fix["fix_summary"], "files": fix["files"],
                           "applied": fix["applied"]})
            if not fix["applied"]:
                logger.warning("⚠️  No usable fix produced this round")

        # ── Final verification: the last fix must prove itself ──
        logger.info("🔁 Final verification run")
        passed, output = self._run_tests(test_absolutes, test_filter=test_filter)
        status = "passed" if passed else "failed"
        if passed:
            logger.info("✅ All tests passing after final fix!")
        else:
            logger.error(f"💀 Could not fix after {self.max_retries} attempts")
        report_file = self._emit_report(report, status, self.max_retries)
        return {"status": status, "attempts": self.max_retries,
                "output": output, "report": report,
                "report_file": report_file}

    # ── Healing report (displayed; saved to HTML only with --save-report) ──

    @staticmethod
    def _problem_summary(output: str) -> str:
        """One-line diagnosis of what actually failed, best evidence first."""
        m = re.search(r"FAILURE_ERRORS: (\[.*?\])", output)
        if m:
            return f"On-page errors: {m.group(1)[:140]}"
        for line in output.splitlines():
            stripped = line.strip()
            if stripped.startswith("E ") or stripped.startswith("E\t"):
                return stripped[1:].strip()[:160]
        m = re.search(r"FAILED [^\s]+ - (.+)", output)
        if m:
            return m.group(1).strip()[:160]
        if "ERROR" in output:
            return "collection/import error (see pytest output)"
        return "see pytest output"

    @staticmethod
    def _format_heal_report(report: list[dict], status: str, attempts: int) -> str:
        lines = ["", "🩺 HEALING REPORT " + "─" * 42]
        for entry in report:
            lines.append(f"Attempt {entry['attempt']}:")
            lines.append(f"  Problem : {entry['problem']}")
            lines.append(f"  Fix     : {entry['fix']}")
            files = ", ".join(entry["files"]) if entry["files"] else "—"
            lines.append(f"  Files   : {files}")
        lines.append(f"Result: {status.upper()} after {attempts} attempt(s)")
        lines.append("─" * 60)
        return "\n".join(lines)

    def _emit_report(self, report: list[dict], status: str, attempts: int) -> str | None:
        """Display the healing report. Persisted to an HTML file only when
        save_report is enabled (--save-report); otherwise display-only.

        Returns the saved file path, or None when nothing was saved."""
        if report:
            logger.info(self._format_heal_report(report, status, attempts))
        if not getattr(self, "save_report", False):
            return None
        try:
            path = self._save_report_html(report, status, attempts)
            logger.info(f"📄 Healing report saved: {path}")
            return str(path)
        except Exception as e:
            logger.warning(f"⚠️  Could not save healing report: {e}")
            return None

    def _save_report_html(self, report: list[dict], status: str, attempts: int) -> Path:
        """Write a self-contained HTML healing report into
        <output_dir>/heal_reports/ — one new timestamped file per run."""
        reports_dir = Path(self.output_dir) / "heal_reports"
        reports_dir.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        path = reports_dir / f"heal-report-{stamp}.html"
        n = 2
        while path.exists():
            path = reports_dir / f"heal-report-{stamp}-{n}.html"
            n += 1
        path.write_text(self._render_report_html(report, status, attempts),
                        encoding="utf-8")
        return path

    @staticmethod
    def _render_report_html(report: list[dict], status: str, attempts: int) -> str:
        esc = html_lib.escape
        passed = status == "passed"
        badge_class = "badge-pass" if passed else "badge-fail"

        attempt_blocks = []
        for entry in report:
            applied = entry.get("applied", False)
            applied_text = "✓ fix applied" if applied else "✗ no usable fix"
            applied_class = "pill-ok" if applied else "pill-bad"
            file_chips = "".join(
                f'<span class="chip">{esc(f)}</span>'
                for f in (entry.get("files") or [])
            ) or '<span class="chip chip-empty">no files changed</span>'
            attempt_blocks.append(f"""
    <div class="attempt">
      <div class="attempt-head">
        <span class="attempt-no">Attempt {entry.get('attempt', '?')}</span>
        <span class="pill {applied_class}">{applied_text}</span>
      </div>
      <div class="section sec-problem">
        <div class="sec-label">⚠ Problem</div>
        <div class="sec-body mono">{esc(str(entry.get('problem', '')))}</div>
      </div>
      <div class="section sec-fix">
        <div class="sec-label">🛠 Fix</div>
        <div class="sec-body">{esc(str(entry.get('fix', '')))}</div>
      </div>
      <div class="section sec-files">
        <div class="sec-label">📁 Files</div>
        <div class="sec-body">{file_chips}</div>
      </div>
    </div>""")

        if not attempt_blocks:
            attempt_blocks.append("""
    <div class="section sec-fix clean-box">
      <div class="sec-label">✓ Clean run</div>
      <div class="sec-body">No fixes were needed — tests passed on the first run.</div>
    </div>""")

        generated = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Healing Report — {esc(status.upper())}</title>
<style>
  * {{ box-sizing: border-box; }}
  body {{ font-family: -apple-system, "Segoe UI", Roboto, Arial, sans-serif;
         margin: 0; background: #eef1f6; color: #1b2a41; }}
  .wrap {{ max-width: 880px; margin: 36px auto; padding: 0 16px; }}
  .card {{ background: #fff; border-radius: 14px; overflow: hidden;
          box-shadow: 0 2px 10px rgba(15,29,51,.10); }}
  .header {{ background: #0f1d33; color: #fff; padding: 24px 30px; }}
  .header h1 {{ font-size: 22px; margin: 0 0 4px; letter-spacing: .2px; }}
  .header .meta {{ color: #cadcfc; font-size: 13px; }}
  .summary {{ display: flex; align-items: center; gap: 14px;
             padding: 16px 30px; border-bottom: 1px solid #e5e7eb;
             background: #f8fafc; flex-wrap: wrap; }}
  .badge {{ display: inline-block; padding: 5px 16px; border-radius: 999px;
           font-weight: 700; font-size: 13px; letter-spacing: .3px; }}
  .badge-pass {{ color: #fff; background: #16a34a; }}
  .badge-fail {{ color: #fff; background: #b91c1c; }}
  .summary .count {{ color: #5a6b82; font-size: 13px; }}
  .body {{ padding: 10px 30px 26px; }}
  .attempt {{ border: 1px solid #e5e7eb; border-radius: 12px;
             padding: 16px 18px; margin-top: 16px; background: #fff; }}
  .attempt-head {{ display: flex; justify-content: space-between;
                  align-items: center; margin-bottom: 12px; }}
  .attempt-no {{ font-weight: 800; font-size: 15px; color: #0f1d33; }}
  .pill {{ font-size: 12px; font-weight: 700; padding: 3px 12px;
          border-radius: 999px; }}
  .pill-ok {{ color: #16a34a; background: #e8f7ee; }}
  .pill-bad {{ color: #b91c1c; background: #fdecec; }}
  .section {{ border-radius: 8px; padding: 10px 14px; margin-top: 10px;
             border-left: 4px solid; }}
  .sec-problem {{ background: #fdf2f2; border-left-color: #b91c1c; }}
  .sec-fix {{ background: #f0faf3; border-left-color: #16a34a; }}
  .sec-files {{ background: #f1f5fb; border-left-color: #29527a; }}
  .sec-label {{ font-size: 11px; font-weight: 800; text-transform: uppercase;
               letter-spacing: .8px; margin-bottom: 5px; }}
  .sec-problem .sec-label {{ color: #b91c1c; }}
  .sec-fix .sec-label {{ color: #15803d; }}
  .sec-files .sec-label {{ color: #29527a; }}
  .sec-body {{ font-size: 14px; line-height: 1.55; word-break: break-word; }}
  .mono {{ font-family: "SF Mono", ui-monospace, Menlo, Consolas, monospace;
          font-size: 13px; }}
  .chip {{ display: inline-block; font-family: "SF Mono", ui-monospace, Menlo,
          Consolas, monospace; font-size: 12px; background: #fff;
          border: 1px solid #c9d6ea; color: #29527a; border-radius: 6px;
          padding: 3px 10px; margin: 2px 6px 2px 0; }}
  .chip-empty {{ color: #5a6b82; border-style: dashed; }}
  .clean-box {{ margin-top: 16px; }}
  .footer {{ padding: 12px 30px 18px; color: #8a97a8; font-size: 12px; }}
</style>
</head>
<body>
<div class="wrap">
  <div class="card">
    <div class="header">
      <h1>🩺 Healing Report</h1>
      <div class="meta">Generated {generated} · selenium-python-ai-agent</div>
    </div>
    <div class="summary">
      <span class="badge {badge_class}">{esc(status.upper())} after {attempts} attempt(s)</span>
      <span class="count">{len(report)} fix round(s) recorded</span>
    </div>
    <div class="body">{''.join(attempt_blocks)}
    </div>
    <div class="footer">Every fix shown here was verified by a real re-run of the tests.</div>
  </div>
</div>
</body>
</html>
"""

    def _fix_once(self, resolved: dict[str, Path], output: str,
                  test_filter: str | None, scan_cache: dict[str, str],
                  project_profile=None) -> dict:
        """One LLM fix round.

        Returns {"applied": bool, "fix_summary": str, "files": [labels]} —
        the raw material of the healing report."""
        known_fix = SeleniumErrorMap.get_fix_summary(output)

        # ── DOM re-scan of every URL the tests touch (live ground truth) ──
        # Pure-Python failures (import/collection/API-usage errors) don't
        # need a browser — skip the scans and fix the code directly.
        locator_context = ""
        needs_dom = ("selenium.common.exceptions" in output
                     or "FAILURE_URL:" in output)
        urls = self._extract_urls(resolved, pytest_output=output) if needs_dom else []
        if not needs_dom:
            logger.info("🐍 Pure Python failure — skipping DOM scans")
        blocks = []
        for url in urls:
            if url not in scan_cache:
                logger.info(f"🔍 DOM scan — real locators for healer: {url}")
                elements = scan_page_locators(url, headless=True)
                if any(el.get("kind") == "captcha" for el in elements):
                    logger.warning(
                        f"🚫 CAPTCHA / bot protection detected on {url} — "
                        f"flows behind it cannot (and must not) be automated. "
                        f"Run this flow on an environment with captcha disabled."
                    )
                scan_cache[url] = format_for_llm(elements, context="healing")
            if scan_cache[url]:
                blocks.append(f"═══ PAGE: {url} ═══\n{scan_cache[url]}")
        if blocks:
            locator_context = "\n\n".join(blocks)
            logger.info(f"✅ Real DOM locators injected from {len(blocks)} page(s)")

        file_contents = self._read_files(resolved)
        files_text = "\n\n".join(f"# File: {k}\n{v}" for k, v in file_contents.items())

        if test_filter:
            system_prompt = HEALER_SYSTEM_PROMPT_TARGETED
            target_instruction = (
                f"\n\n🎯 TARGETED FIX — Fix ONLY this test: '{test_filter}'\n"
                f"ALL other test functions must be returned unchanged.\n"
                f"Return the COMPLETE file — do NOT truncate or drop any tests.\n"
            )
        else:
            system_prompt = HEALER_SYSTEM_PROMPT
            target_instruction = ""

        project_instruction = ""
        if project_profile is not None:
            project_instruction = (
                f"\n\n🏗️ EXISTING-PROJECT MODE — this codebase has its OWN "
                f"architecture. The profile below OVERRIDES the default "
                f"architecture/import rules above: mirror the project's "
                f"patterns exactly, never convert files to the "
                f"selenium_agent BasePage style, and tests use the fixture "
                f"named '{project_profile.driver_fixture_name}'.\n\n"
                f"{project_profile.to_llm_context()}\n"
            )

        raw = self.client.generate_text(
            system_prompt=system_prompt,
            user_prompt=(
                f"Fix these failing Selenium tests.\n\n"
                f"SELENIUM ERROR ANALYSIS:\n{known_fix}\n\n"
                f"{locator_context}\n"
                f"PYTEST OUTPUT:\n{self._trim_output(output)}\n"
                f"{target_instruction}"
                f"{project_instruction}\n"
                f"CURRENT CODE:\n{files_text}"
            ),
            max_tokens=8000,
            json_mode=True,
        )

        result = extract_json_object(raw)
        fix_summary = result.get("fix_summary", "No summary")
        logger.info(f"🔧 Fix: {fix_summary}")

        wrote_any = False
        written_files: list[str] = []
        for file_info in result.get("fixed_files", []):
            filename = file_info.get("filename", "")
            fixed_content = file_info.get("content", "")
            if not filename or not fixed_content:
                continue

            # Test files must never contain By imports / raw locators
            if Path(filename).name.startswith("test_"):
                fixed_content = self._sanitize_test_file(fixed_content)

            # Targeted mode: restore any functions the LLM dropped
            if test_filter:
                original_path = next(
                    (p for l, p in resolved.items()
                     if p.name == Path(filename).name),
                    None,
                )
                if original_path and original_path.exists():
                    original = original_path.read_text(encoding="utf-8")
                    fixed_content = self._merge_preserve_others(
                        original, fixed_content, test_filter
                    )

            # Never overwrite a working file with a syntactically broken fix
            validation = validate_python(filename, fixed_content)
            if not validation.valid:
                logger.warning(
                    f"⚠️  Rejected broken fix for {filename}: {validation.errors[0]}"
                )
                continue

            written = self._write_fixed_file(filename, fixed_content, resolved)
            logger.info(f"📝 Updated: {written}")
            wrote_any = True
            written_files.append(filename)

        return {"applied": wrote_any, "fix_summary": fix_summary,
                "files": written_files}
