"""
PLANNER AGENT
=============
Works like Playwright's planner agent, for Selenium Python:

1. Opens a real (headless) browser and scans the live DOM of the target
   URL — optionally exploring same-origin pages — so plans use REAL
   locators, never guessed ones.
2. Asks the LLM for a structured JSON plan (scenarios, page objects,
   locators, wait strategy).
3. The Orchestrator persists the plan to specs/<slug>.md (human-readable)
   and specs/<slug>.json (Generator input).
"""

from selenium_agent.utils.logger import setup_logger
from selenium_agent.utils.llm import create_llm_client, DEFAULT_PROVIDER, get_default_model
from selenium_agent.utils.json_utils import extract_json_object, LLMJSONError
from selenium_agent.selenium.locator_scanner import (
    scan_site_locators, format_site_for_llm,
)
from selenium_agent.bdd.gherkin_advisor import GherkinAdvisor

logger = setup_logger("PlannerAgent")

_SYSTEM_BASE = """
You are an expert QA Test Planner specializing in Selenium Python automation.

══ PAGE OBJECT ARCHITECTURE — MOST IMPORTANT RULE ══

Every distinct page MUST have its OWN class. NEVER mix pages.
Class names and locators come from the actual app under test.

EXAMPLE PATTERN (illustrative only — use actual app's pages and locators):

  class LoginPage(BasePage):       ← only login elements
  class DashboardPage(BasePage):   ← only dashboard elements
  class ProductPage(BasePage):     ← only product page elements
  class CartPage(BasePage):        ← only cart elements
  class CheckoutPage(BasePage):    ← only checkout elements

Each class contains ONLY the locators for that page.
FORBIDDEN: putting page B locators inside page A's class.

══ MULTI-STEP FLOW RULE ══

For flows that span multiple pages (login → inventory → cart → checkout → logout):
  - Plan SEPARATE page objects for EACH page
  - page_objects_needed must list ALL pages: ["LoginPage", "InventoryPage", "CartPage", "CheckoutPage", "MenuPage"]
  - Each locator entry must specify which page_object it belongs to
  - wait_for_url() must be called after every navigation click

══ LOCATOR RULES ══
  1. CSS preferred over XPath
  2. XPath only when CSS cannot express it
  3. NEVER absolute XPath, NEVER index-based XPath
  4. Priority: data-test > data-testid > id > name > css
  5. Use ONLY locators from DOM scan — never invent

══ WAIT STRATEGY ══
  - Input fields     → fluent_wait(locator, 'visible')
  - Buttons/links    → fluent_wait(locator, 'clickable')
  - After navigation → wait_for_url('partial-url-string')
  - Loaders          → fluent_wait(locator, 'invisible')
  No time.sleep(). No hardcoded waits.

══ FORM FILLING ══
  For React/SPA forms always use safe_type() — not type():
  safe_type(page, page.FIRST_NAME_INPUT, "John")

══ SCENARIO QUALITY (enterprise test design) ══
  - Cover the happy path FIRST, then negative/edge cases relevant to the instruction
  - Every scenario independent — no shared state between scenarios
  - Each scenario has explicit expected_result that a machine can assert
  - Use realistic test_data (from the instruction when given)
  - DOM-scan text shows the page BEFORE any action. expected_result must
    describe the state AFTER the action (what changes/appears), never the
    pre-action text you saw in the scan
  - If the flow CREATES an entity (account, record), mark its test_data
    values as "GENERATE_UNIQUE_AT_RUNTIME" — hardcoded values collide with
    previous runs (e.g. "email already taken")
  - When a scanned page contains a form, plan locators and fill-steps for
    ALL its inputs/selects — apps silently reject submissions with missing
    required fields, even if the instruction names only a few

OTHER RULES:
  - Use EXACT target URL — never example.com
  - headless comes from config
  - Respond with valid JSON only — no markdown fences
"""

_PYTEST_SCHEMA = """
{
  "mode": "pytest",
  "url": "<EXACT URL from instruction>",
  "browser": "chrome",
  "headless": false,
  "test_scenarios": [
    {
      "id": "TC001",
      "name": "descriptive scenario name",
      "description": "what this test verifies",
      "steps": [
        "open <PageName>.URL",
        "type <field> on <PageName>",
        "click <button> on <PageName>",
        "wait_for_url('<url-fragment>')",
        "interact with <NextPageName>"
      ],
      "expected_result": "what success looks like",
      "test_data": {"key": "value"}
    }
  ],
  "page_objects_needed": ["<Page1Name>", "<Page2Name>"],
  "locators": [
    {
      "page_object": "<PageName>",
      "element": "descriptive element name",
      "css": "<css selector>",
      "xpath": "<xpath>",
      "preferred": "css",
      "wait_condition": "visible"
    }
  ],
  "pytest_markers": ["smoke"],
  "notes": ""
}
"""

_BDD_SCHEMA = """
{
  "mode": "bdd",
  "url": "<EXACT URL from instruction>",
  "feature_name": "<feature name>",
  "feature_title": "<Feature Title>",
  "role": "<user role>",
  "goal": "<goal>",
  "benefit": "<benefit>",
  "browser": "chrome",
  "headless": false,
  "scenarios": [
    {
      "id": "TC001",
      "name": "descriptive scenario name",
      "tags": ["smoke"],
      "steps": [
        {"type": "Given", "text": "I am on the <page> page"},
        {"type": "When",  "text": "I perform <action>"},
        {"type": "Then",  "text": "I should see <result>"}
      ],
      "test_data": {}
    }
  ],
  "page_objects_needed": ["<Page1Name>", "<Page2Name>"],
  "locators": [
    {
      "page_object": "<PageName>",
      "element": "descriptive element name",
      "css": "<css selector>",
      "preferred": "css",
      "wait_condition": "visible"
    }
  ],
  "notes": ""
}
"""

_MULTI_PAGE_KEYWORDS = [
    "checkout", "cart", "logout", "login and", "then", "after",
    "navigate", "flow", "end to end", "e2e", "journey",
]


class PlannerAgent:
    def __init__(self, api_key: str, provider: str = DEFAULT_PROVIDER,
                 model: str | None = None):
        resolved_model = model or get_default_model(provider)
        self.client = create_llm_client(
            provider=provider, api_key=api_key, model=resolved_model
        )

    def plan(self, user_instruction: str, mode: str = "pytest",
             project_profile=None, headless: bool = False,
             target_url: str | None = None,
             explore_pages: int = 0) -> dict:
        """
        Build a test plan.

        explore_pages: how many same-origin pages beyond the target URL to
        scan for locators (0 = target page only). Multi-page instructions
        automatically get exploration even when not requested.
        """
        logger.info(f"📋 Planning [{mode.upper()}] for: {user_instruction}")

        schema = _BDD_SCHEMA if mode == "bdd" else _PYTEST_SCHEMA
        system = _SYSTEM_BASE + f"\nRespond using this JSON schema:\n{schema}"

        is_multi_page = (
            sum(1 for kw in _MULTI_PAGE_KEYWORDS if kw in user_instruction.lower()) >= 2
        )

        # ── DOM scan BEFORE planning — real locators, never guessed ──
        dom_context = ""
        if target_url:
            extra = explore_pages or (2 if is_multi_page else 0)
            logger.info(f"🔍 Pre-plan DOM scan: {target_url} (explore={extra} extra pages)")
            site = scan_site_locators(target_url, headless=True, max_extra_pages=extra,
                                      instruction=user_instruction)
            dom_context = format_site_for_llm(site, context="planning")
            total = sum(len(v) for v in site.values())
            if total:
                logger.info(f"✅ {total} real locators from {len(site)} page(s) injected into plan prompt")
            else:
                logger.warning("⚠️  DOM scan returned nothing — LLM will infer locators")

        multi_page_hint = ""
        if is_multi_page:
            multi_page_hint = (
                "\n\n🚨 MULTI-PAGE FLOW DETECTED — MANDATORY RULES:\n"
                "  1. Create a SEPARATE page object class for EACH page visited\n"
                "  2. page_objects_needed must list ALL pages with meaningful names based on the app\n"
                "  3. Each locator entry must have 'page_object' field specifying which class it belongs to\n"
                "  4. NEVER put locators from one page inside another page's class\n"
                "  5. Add wait_for_url() after every navigation step\n"
            )

        url_block = ""
        if target_url:
            url_block = (
                f"\n\n🚨 TARGET URL — use EXACTLY:\n"
                f"  URL = '{target_url}'\n"
                f"  NEVER use example.com or any other URL.\n"
            )

        project_context = ""
        if project_profile:
            project_context = (
                f"\n\nFit into this existing project:\n"
                f"{project_profile.to_llm_context()}\n"
            )

        user_prompt = (
            f"Create a Selenium Python {mode} test plan for: {user_instruction}\n"
            f"headless: {str(headless).lower()}"
            f"{url_block}"
            f"{multi_page_hint}"
            f"\n\n{dom_context}"
            f"{project_context}"
        )

        max_tokens = 8000 if is_multi_page else 4000
        raw = self.client.generate_text(
            system_prompt=system,
            user_prompt=user_prompt,
            max_tokens=max_tokens,
            json_mode=True,
        )

        try:
            plan = extract_json_object(raw)
        except LLMJSONError:
            logger.warning("⚠️  Plan JSON unparseable — retrying once with strict reminder")
            raw = self.client.generate_text(
                system_prompt=system,
                user_prompt=user_prompt + "\n\nIMPORTANT: respond with ONLY the JSON object. "
                                          "No prose, no markdown fences.",
                max_tokens=max_tokens,
                json_mode=True,
            )
            plan = extract_json_object(raw)

        plan["mode"] = mode
        plan["headless"] = headless
        if target_url:
            plan["url"] = target_url

        count = len(plan.get("test_scenarios") or plan.get("scenarios", []))
        pages = plan.get("page_objects_needed", [])
        logger.info(f"✅ Plan ready: {count} scenario(s) | pages={pages} | url={plan.get('url')}")
        return plan
