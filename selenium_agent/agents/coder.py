"""
CODER (GENERATOR) AGENT
=======================
Works like Playwright's generator agent, for Selenium Python:

1. Consumes a structured plan (fresh from the Planner or loaded from
   specs/<slug>.json) built from REAL scanned locators.
2. Generates Page Object Model code (pytest or pytest-bdd).
3. Self-verifies before saving: every file is syntax-checked (ast) and
   architecture-checked (no By imports / raw locators in test files);
   on failure the LLM gets ONE repair round with the exact errors.
4. Adapts to an existing project's structure, base class, and import
   style when a ProjectProfile is provided.
"""

import json
import re
from pathlib import Path

from selenium_agent.utils.logger import setup_logger
from selenium_agent.utils.llm import create_llm_client, DEFAULT_PROVIDER, get_default_model
from selenium_agent.utils.json_utils import extract_json_object, LLMJSONError
from selenium_agent.utils.paths import safe_output_path
from selenium_agent.utils.code_validator import validate_files, format_errors
from selenium_agent.selenium.locator_advisor import LocatorAdvisor
from selenium_agent.bdd.gherkin_advisor import GherkinAdvisor

logger = setup_logger("CoderAgent")

EXACT_API_REFERENCE = """
IMPORTS:
  from selenium.webdriver.common.by import By
  from selenium_agent.selenium.base_page import BasePage
  from selenium_agent.selenium.driver_factory import DriverFactory

══ PAGE OBJECT ARCHITECTURE — MANDATORY ══

One class per page. NEVER mix locators from different pages into one class.
Class names and locators come from the plan — never hardcoded.

  class SomePage(BasePage):
      URL = '<url from plan>'
      ELEMENT_NAME = (By.CSS_SELECTOR, '<selector from plan>')
      ANOTHER_ELEMENT = (By.ID, '<id from plan>')

      # Methods optional — for complex reusable actions only

FORBIDDEN: putting page B's locators inside page A's class.

══ FLUENT WAIT — use for every interaction ══

  page.fluent_wait(locator, 'visible')    ← inputs, text (DEFAULT)
  page.fluent_wait(locator, 'clickable')  ← all buttons and links
  page.fluent_wait(locator, 'invisible')  ← loaders/spinners
  page.fluent_wait(locator, 'present')    ← hidden inputs

══ NAVIGATION — wait_for_url() after every click that changes page ══

  page.click(page.SUBMIT_BTN)
  page.wait_for_url('expected-url-fragment')  ← ALWAYS after navigation
  next_page = NextPage(driver)
  next_page.fluent_wait(next_page.SOME_ELEMENT, 'visible')

══ FORM FILLING — always use page.safe_type() ══

  page.safe_type(page.FIRST_NAME_INPUT, "John")
  ← built into BasePage: types, verifies, falls back to JS + React events

══ AVAILABLE BasePage METHODS ══

  page.open(url)                 page.click(locator)
  page.type(locator, text)       page.get_text(locator)
  page.find(locator)             page.find_all(locator)
  page.get_url()                 page.get_title()
  page.is_visible(locator)       page.is_present(locator)
  page.wait_for_url(partial)     page.wait_for_invisible(locator)
  page.scroll_to(locator)        page.execute_js(script, *args)
  page.safe_type(locator, text)  ← JS-fallback form input
  page.select_by_text(locator, text)   page.hover(locator)

══ READING VALUES FROM THE PAGE ══

  get_text() returns the FULL text of the element, including any label prefix.
  When a "LABEL: value" element is read to USE its value, strip the label:

    raw = page.get_text(page.SHOWN_USERNAME)          # "USERNAME: testuser"
    username = raw.split(':', 1)[-1].strip()          # "testuser"

══ FILLING FORMS COMPLETELY ══

  When the DOM scan of a form page lists MORE inputs/selects/date fields
  than the instruction names, fill ALL of them with sensible values —
  apps reject submissions with missing required fields, often silently
  (the form just re-renders). "Fill the form" means the WHOLE form.

══ UNIQUE TEST DATA ══

  When a flow CREATES something (an account, a record, any entity),
  hardcoded data collides with previous runs ("email already taken").
  Generate unique values at runtime in the test:

    import uuid
    unique = uuid.uuid4().hex[:8]
    email = "qa." + unique + "@example.com"
    password = "Xk9#" + unique + "!Qz"   # strong AND unique
    first_name = "Test" + unique

  PASSWORDS: never use common patterns (Password@123, Test@1234, ...) —
  browsers and apps reject passwords found in breach lists ("this password
  has appeared in a data leak"). Always embed the runtime-unique suffix.

══ ASSERTING OUTCOMES ══

  Text captured in the DOM scan is the page's state BEFORE any action
  (e.g. a status element showing "STANDBY" before login).
  NEVER assert pre-action text as the expected outcome.
  Assert what the scenario expects AFTER the action: a status element's text
  CHANGES, a success/error message APPEARS, a new element becomes visible.
  Many SPAs never navigate — verify in-page indicators, not URLs, unless the
  plan explicitly says the URL changes.

FORBIDDEN: find_element(), time.sleep(), get_driver(), DriverFactory.get_driver()

══ PAGES BEHIND LOGIN — NO SKIP PLACEHOLDERS, EVER ══

  Auth-gated pages often can't be DOM-scanned up front, so the plan may
  lack locators for them. In that case write the MOST LIKELY locator based
  on the app's visible conventions (e.g. if scanned pages use data-test
  attributes, inner pages almost certainly do too) — the Healer verifies
  and corrects every locator against the live DOM at run time.

  FORBIDDEN: pytest.skip(...) placeholders, TODO steps, empty step bodies.
  A skipped test proves nothing; a best-effort test gets healed to green.

══ DRIVER FIXTURE — PROVIDED BY THE FRAMEWORK ══

  conftest.py (auto-generated) already defines the `driver` fixture.
  Test functions simply accept it as a parameter:

    def test_something(driver):
        page = SomePage(driver)
        ...

  FORBIDDEN in test files:
    - defining any driver fixture
    - importing or calling DriverFactory
    - creating/quitting drivers manually
"""

CONFTEST_CONTENT = '''"""conftest.py — Auto-generated by selenium-python-ai-agent"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import pytest
from selenium_agent.selenium.driver_factory import DriverFactory

HEADLESS = __HEADLESS__

# Markers/tags used by the generated tests — registered automatically so
# `pytest -m <marker>` works cleanly, no pytest.ini needed.
MARKERS = __MARKERS__


def pytest_configure(config):
    for marker in MARKERS:
        config.addinivalue_line("markers", f"{marker}: tagged by selenium-agent")


@pytest.fixture(scope="function")
def driver():
    """Canonical driver fixture — provided by the framework, never by
    generated test files (deterministic scaffolding beats regeneration)."""
    d = DriverFactory.create(browser="chrome", headless=HEADLESS)
    yield d
    d.quit()


@pytest.hookimpl(hookwrapper=True)
def pytest_runtest_makereport(item, call):
    """On failure, report the URL the browser was on — the healer re-scans
    that exact page instead of guessing from the base URL."""
    outcome = yield
    report = outcome.get_result()
    if report.when == "call" and report.failed:
        driver = item.funcargs.get("driver")
        if driver is not None:
            try:
                sys.stderr.write(f"\\nFAILURE_URL: {driver.current_url}\\n")
                errors = driver.execute_script(
                    "return [...document.querySelectorAll("
                    "'[class*=alert],[class*=error],[class*=invalid],[role=alert]')]"
                    ".map(e => e.textContent.trim()).filter(t => t).slice(0, 10)"
                ) or []
                if errors:
                    sys.stderr.write(f"FAILURE_ERRORS: {errors}\\n")
                text = driver.execute_script("return document.body.innerText") or ""
                text = " | ".join(text.split())[:800]
                sys.stderr.write(f"FAILURE_PAGE_TEXT: {text}\\n")
            except Exception:
                pass
'''

CODER_SYSTEM_PROMPT_PYTEST = f"""
You are an expert Selenium Python engineer. Generate pytest Page Object Model code.

{EXACT_API_REFERENCE}

{LocatorAdvisor.get_priority_guide()}

RULES:
1. One class per page — names and selectors from plan only, never hardcoded
2. page.safe_type() for ALL form inputs
3. wait_for_url() after every navigation click
4. fluent_wait() before every element interaction
5. headless from plan JSON — never hardcode True/False
6. No sys.path — conftest.py handles it
7. No By imports in test files — only in page objects

Output valid JSON only, no markdown:
{{"files": [
  {{"filename": "pages/<name>_page.py", "content": "..."}},
  {{"filename": "tests/test_<name>.py",  "content": "..."}}
]}}
"""

CODER_SYSTEM_PROMPT_BDD = f"""
You are an expert Selenium Python BDD engineer. Generate pytest-bdd Page Object Model code.

{EXACT_API_REFERENCE}
{LocatorAdvisor.get_priority_guide()}
{GherkinAdvisor.get_guide()}

RULES:
1. One class per page — names and selectors from plan only
2. page.safe_type() for ALL form inputs
3. wait_for_url() after every navigation
4. headless from plan JSON
5. Step files must start with test_

Output valid JSON only, no markdown:
{{"files": [
  {{"filename": "features/<name>.feature",               "content": "..."}},
  {{"filename": "pages/<name>_page.py",                  "content": "..."}},
  {{"filename": "step_definitions/test_<name>_steps.py", "content": "..."}}
]}}
"""

REPAIR_PROMPT = """
The code you generated has validation errors. Fix them and return the
COMPLETE corrected set of files in the same JSON format.

VALIDATION ERRORS:
{errors}

YOUR PREVIOUS OUTPUT:
{previous}
"""


class CoderAgent:
    def __init__(self, api_key: str, output_dir: str = "generated_tests",
                 provider: str = DEFAULT_PROVIDER, model: str | None = None):
        resolved_model = model or get_default_model(provider)
        self.client = create_llm_client(
            provider=provider, api_key=api_key, model=resolved_model
        )
        self.output_dir = output_dir

    def code(self, plan: dict, project_profile=None) -> list[str]:
        mode = plan.get("mode", "pytest")
        logger.info(f"💻 Generating [{mode.upper()}] code (headless={plan.get('headless', False)})...")

        system_prompt = CODER_SYSTEM_PROMPT_BDD if mode == "bdd" else CODER_SYSTEM_PROMPT_PYTEST
        user_prompt = self._build_user_prompt(plan, project_profile, mode)
        max_tokens = self._token_budget(plan)

        raw = self.client.generate_text(
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            max_tokens=max_tokens,
            json_mode=True,
        )
        try:
            result = extract_json_object(raw)
        except LLMJSONError:
            logger.warning("⚠️  Generator JSON unparseable — retrying once with strict reminder")
            raw = self.client.generate_text(
                system_prompt=system_prompt,
                user_prompt=user_prompt + "\n\nIMPORTANT: respond with ONLY the JSON object. "
                                          "Escape all quotes and newlines inside file contents.",
                max_tokens=max_tokens,
                json_mode=True,
            )
            result = extract_json_object(raw)
        files = result.get("files", [])
        if not files:
            raise ValueError("Coder LLM returned no files")

        # ── Completeness: a plan must yield page objects AND runnable tests ──
        missing = self._missing_file_kinds(files, mode)
        if missing:
            logger.warning(f"⚠️  Generator output incomplete — missing: {', '.join(missing)} — retry")
            raw = self.client.generate_text(
                system_prompt=system_prompt,
                user_prompt=user_prompt + (
                    f"\n\nYOUR PREVIOUS RESPONSE WAS INCOMPLETE — it was missing: "
                    f"{', '.join(missing)}.\n"
                    f"Return the COMPLETE set of files (page objects AND test files) "
                    f"in one JSON object."
                ),
                max_tokens=max_tokens,
                json_mode=True,
            )
            files = extract_json_object(raw).get("files", files)
            still_missing = self._missing_file_kinds(files, mode)
            if still_missing:
                raise ValueError(
                    f"Generator failed to produce a complete test suite — "
                    f"missing: {', '.join(still_missing)}"
                )

        # ── Self-verification: syntax + architecture, one repair round ──
        files = self._sanitize(files)
        validations = validate_files(files)
        broken = [v for v in validations if not v.valid]
        if broken:
            logger.warning(f"⚠️  {len(broken)} generated file(s) failed validation — repair round")
            raw = self.client.generate_text(
                system_prompt=system_prompt,
                user_prompt=user_prompt + REPAIR_PROMPT.format(
                    errors=format_errors(validations),
                    previous=json.dumps(result)[:12000],
                ),
                max_tokens=max_tokens,
                json_mode=True,
            )
            files = self._sanitize(extract_json_object(raw).get("files", files))
            still_broken = [v for v in validate_files(files) if not v.valid]
            if still_broken:
                raise ValueError(
                    "Generated code failed validation after repair:\n"
                    + format_errors(still_broken)
                )

        for v in validate_files(files):
            for w in v.warnings:
                logger.warning(f"⚠️  {v.filename}: {w}")

        # ── Save ──
        saved = []
        target_url = plan.get("url")
        for file_info in files:
            content = file_info["content"]
            if target_url:
                content = self._force_correct_url(content, target_url)
            filepath = safe_output_path(self.output_dir, file_info["filename"])
            filepath.parent.mkdir(parents=True, exist_ok=True)
            filepath.write_text(content, encoding="utf-8")
            saved.append(str(filepath))
            logger.info(f"✅ Created: {filepath}")

        self._write_conftest(project_profile, headless=plan.get("headless", False),
                             markers=self._collect_markers(plan))
        return saved

    @staticmethod
    def _collect_markers(plan: dict) -> list[str]:
        """Union of plan-level pytest markers and BDD scenario tags."""
        markers = set(plan.get("pytest_markers") or [])
        for scenario in (plan.get("scenarios") or plan.get("test_scenarios") or []):
            for tag in scenario.get("tags") or []:
                markers.add(str(tag).lstrip("@"))
        markers.add("smoke")  # agents tag critical-path tests with @smoke by convention
        return sorted(markers)

    # ── Prompt building ────────────────────────────────────────────────

    def _build_user_prompt(self, plan: dict, project_profile, mode: str) -> str:
        project_context = ""
        if project_profile:
            base_import_hint = ""
            if getattr(project_profile, "base_page_import", ""):
                base_import_hint = (
                    f"IMPORTANT — this project has its OWN base page class. "
                    f"Page objects MUST use it instead of selenium_agent's:\n"
                    f"  from {project_profile.base_page_import} "
                    f"import {project_profile.base_page_class}\n"
                    f"  class SomePage({project_profile.base_page_class}): ...\n"
                    f"Only call methods that exist on that base class "
                    f"(see the sample page object below for its style).\n"
                )
            project_context = (
                f"\n\nFit into existing project:\n"
                f"{project_profile.to_llm_context()}\n"
                f"Pages dir  : {project_profile.pages_dir}/\n"
                f"Tests dir  : {project_profile.tests_dir}/\n"
                f"{base_import_hint}"
            )

        url_warning = ""
        if plan.get("url"):
            url_warning = (
                f"\n\n🚨 MANDATORY URL: {plan['url']}\n"
                f"Use this as the page URL constant. NEVER use example.com.\n"
            )

        return (
            f"Generate Selenium Python {mode} code for:\n"
            f"{json.dumps(plan, indent=2)}"
            f"{url_warning}"
            f"{project_context}"
        )

    def _token_budget(self, plan: dict) -> int:
        scenarios = len(plan.get("test_scenarios") or plan.get("scenarios", []))
        page_objects = len(plan.get("page_objects_needed", []))
        complex_kw = ["checkout", "cart", "logout", "navigate", "flow", "then", "after"]
        is_complex = (
            scenarios > 2 or page_objects > 2
            or sum(1 for kw in complex_kw if kw in json.dumps(plan).lower()) >= 2
        )
        max_tokens = 12000 if is_complex else 6000
        logger.info(
            f"📐 Scenarios: {scenarios} | Pages: {page_objects} | "
            f"complex: {is_complex} | max_tokens: {max_tokens}"
        )
        return max_tokens

    # ── Post-processing ────────────────────────────────────────────────

    @staticmethod
    def _missing_file_kinds(files: list[dict], mode: str) -> list[str]:
        """A complete suite needs page objects AND runnable tests/steps."""
        names = [Path(f.get("filename", "")).name for f in files]
        missing = []
        if not any(n.endswith("_page.py") or "page" in n for n in names):
            missing.append("page object file (pages/<name>_page.py)")
        if mode == "bdd":
            if not any(n.endswith(".feature") for n in names):
                missing.append("feature file (features/<name>.feature)")
            if not any(n.startswith("test_") for n in names):
                missing.append("step definitions (step_definitions/test_<name>_steps.py)")
        else:
            if not any(n.startswith("test_") and n.endswith(".py") for n in names):
                missing.append("test file (tests/test_<name>.py)")
        return missing

    @staticmethod
    def _sanitize(files: list[dict]) -> list[dict]:
        """Strip By imports the LLM sneaked into test files (locators live in page objects)."""
        cleaned = []
        for f in files:
            filename = f.get("filename", "")
            content = f.get("content", "")
            name = Path(filename).name
            if name.startswith("test_") and name.endswith(".py"):
                new_content, n = re.subn(
                    r"^from selenium\.webdriver\.common\.by import By\s*\n",
                    "", content, flags=re.MULTILINE,
                )
                if n:
                    logger.warning(f"⚠️  Removed By import from {filename} (belongs in page object)")
                content = new_content
            cleaned.append({"filename": filename, "content": content})
        return cleaned

    @staticmethod
    def _force_correct_url(code: str, correct_url: str) -> str:
        from urllib.parse import urlparse
        placeholders = [
            r'https?://(?:www\.)?example\.com[^\s\'"]*',
            r'https?://(?:www\.)?placeholder\.com[^\s\'"]*',
            r'https?://(?:www\.)?yoursite\.com[^\s\'"]*',
            r'https?://(?:www\.)?testsite\.com[^\s\'"]*',
            r'https?://(?:www\.)?myapp\.com[^\s\'"]*',
        ]
        base = re.match(r'(https?://[^/]+)', correct_url)
        base_url = base.group(1) if base else correct_url
        for p in placeholders:
            code = re.sub(p, base_url, code, flags=re.IGNORECASE)

        def fix_url_const(m):
            q, existing = m.group(1), m.group(2)
            cd = urlparse(correct_url).netloc
            ed = urlparse(existing).netloc if existing.startswith('http') else ''
            return f'URL = {q}{base_url}{q}' if cd and ed and cd not in ed else m.group(0)
        code = re.sub(r'URL\s*=\s*([\'"])([^\'"]+)\1', fix_url_const, code)
        return code

    def _write_conftest(self, project_profile=None, headless: bool = False,
                        markers: list[str] | None = None):
        if project_profile and project_profile.has_conftest:
            logger.info("⏭️  Skipping conftest.py — already exists")
            return
        conftest_path = Path(self.output_dir) / "conftest.py"
        conftest_path.parent.mkdir(parents=True, exist_ok=True)
        content = (CONFTEST_CONTENT
                   .replace("__HEADLESS__", str(bool(headless)))
                   .replace("__MARKERS__", repr(sorted(set(markers or ["smoke"])))))
        conftest_path.write_text(content, encoding="utf-8")
        logger.info(f"✅ Created: {conftest_path}")
