"""PLANNER AGENT — pytest + bdd modes"""

import json
from selenium_agent.utils.logger import setup_logger
from selenium_agent.utils.llm import create_llm_client, DEFAULT_PROVIDER, get_default_model
from selenium_agent.selenium.locator_advisor import LocatorAdvisor
from selenium_agent.bdd.gherkin_advisor import GherkinAdvisor

logger = setup_logger("PlannerAgent")

PLANNER_SYSTEM_PROMPT_PYTEST = f"""
You are an expert QA Test Planner specializing in Selenium Python automation.
Produce a structured pytest test plan.

{LocatorAdvisor.get_priority_guide()}

RULES: No absolute XPath. No time.sleep(). POM mandatory. pytest fixtures required.
Respond with valid JSON only — no markdown, no extra text.

{{
  "mode": "pytest",
  "url": "target URL",
  "page_title": "LoginPage",
  "browser": "chrome",
  "headless": true,
  "test_scenarios": [
    {{
      "id": "TC001",
      "name": "scenario name",
      "description": "what this checks",
      "steps": ["step 1"],
      "expected_result": "success condition",
      "test_data": {{"key": "value"}},
      "selenium_waits": ["wait for element"]
    }}
  ],
  "locators": [
    {{"element": "username input", "strategy": "id", "value": "user-name"}}
  ],
  "page_objects_needed": ["LoginPage"],
  "pytest_markers": ["smoke"],
  "fixtures_needed": ["driver"],
  "notes": ""
}}
"""

PLANNER_SYSTEM_PROMPT_BDD = f"""
You are an expert QA Test Planner for Selenium Python BDD using pytest-bdd.
Produce a structured BDD test plan with Gherkin scenarios.

{LocatorAdvisor.get_priority_guide()}
{GherkinAdvisor.get_guide()}

Respond with valid JSON only — no markdown, no extra text.

{{
  "mode": "bdd",
  "url": "target URL",
  "page_title": "LoginPage",
  "feature_name": "login",
  "feature_title": "User Login",
  "role": "registered user",
  "goal": "log into the application",
  "benefit": "I can access my account",
  "browser": "chrome",
  "headless": true,
  "scenarios": [
    {{
      "id": "TC001",
      "name": "Successful login",
      "tags": ["smoke"],
      "steps": [
        {{"type": "Given", "text": "I am on the login page"}},
        {{"type": "When", "text": "I enter username \\"standard_user\\""}},
        {{"type": "Then", "text": "I should see the dashboard"}}
      ],
      "test_data": {{}}
    }}
  ],
  "locators": [{{"element": "username", "strategy": "id", "value": "user-name"}}],
  "page_objects_needed": ["LoginPage"],
  "notes": ""
}}
"""


class PlannerAgent:
    def __init__(self, api_key: str, provider: str = DEFAULT_PROVIDER, model: str | None = None):
        resolved_model = model or get_default_model(provider)
        self.client = create_llm_client(provider=provider, api_key=api_key, model=resolved_model)
        self.provider = provider
        self.model = resolved_model

    def plan(self, user_instruction: str, mode: str = "pytest") -> dict:
        logger.info(f"📋 Planning [{mode.upper()}] for: {user_instruction}")

        system_prompt = (
            PLANNER_SYSTEM_PROMPT_BDD if mode == "bdd"
            else PLANNER_SYSTEM_PROMPT_PYTEST
        )

        raw = self.client.generate_text(
            system_prompt=system_prompt,
            user_prompt=f"Create a Selenium Python {mode} test plan for: {user_instruction}",
            max_tokens=2000,
        )

        if raw.startswith("```"):
            raw = raw.split("```")[1]
            if raw.startswith("json"):
                raw = raw[4:]
        raw = raw.strip()

        plan = json.loads(raw)
        plan["mode"] = mode
        count = len(plan.get("test_scenarios") or plan.get("scenarios", []))
        logger.info(f"✅ Plan ready: {count} scenarios")
        return plan
