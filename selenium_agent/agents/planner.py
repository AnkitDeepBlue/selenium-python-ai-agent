"""
PLANNER AGENT
=============
Takes user instruction and creates a structured test plan.

Responsibilities:
- Understand what needs to be tested
- Break it into test scenarios
- Define locator strategy
- Output a structured plan for the Coder Agent
"""

import json
from selenium_agent.utils.logger import setup_logger
from selenium_agent.utils.llm import create_llm_client, get_default_model

logger = setup_logger("PlannerAgent")

PLANNER_SYSTEM_PROMPT = """
You are an expert QA Test Planner specializing in Selenium Python automation.

Your job is to analyze a user's testing requirement and produce a structured test plan.

Always respond with valid JSON only. No extra text. No markdown.

Your JSON output must follow this schema:
{
  "url": "target URL to test",
  "page_title": "short name for the page",
  "test_scenarios": [
    {
      "id": "TC001",
      "name": "scenario name",
      "description": "what this test checks",
      "steps": ["step 1", "step 2"],
      "expected_result": "what success looks like",
      "test_data": {"key": "value"}
    }
  ],
  "locator_strategy": "ID | CSS | XPath — explain preferred approach",
  "page_objects_needed": ["LoginPage", "HomePage"],
  "pytest_markers": ["smoke", "login"],
  "notes": "any important observations"
}
"""


class PlannerAgent:
    def __init__(self, api_key: str, provider: str = "anthropic", model: str | None = None):
        self.model = model or get_default_model(provider)
        self.client = create_llm_client(api_key=api_key, provider=provider, model=self.model)

    def plan(self, user_instruction: str) -> dict:
        logger.info(f"📋 Planning tests for: {user_instruction}")

        raw = self.client.generate_text(
            system_prompt=PLANNER_SYSTEM_PROMPT,
            user_prompt=f"Create a Selenium test plan for: {user_instruction}",
            max_tokens=2000,
        )

        # Strip markdown fences if present
        if raw.startswith("```"):
            raw = raw.split("```")[1]
            if raw.startswith("json"):
                raw = raw[4:]
        raw = raw.strip()

        plan = json.loads(raw)
        logger.info(f"✅ Plan created: {len(plan.get('test_scenarios', []))} scenarios")
        return plan
