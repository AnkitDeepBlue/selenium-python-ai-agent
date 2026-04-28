"""CODER AGENT — pytest + bdd modes"""

import json
from selenium_agent.utils.logger import setup_logger
from selenium_agent.utils.llm import create_llm_client, DEFAULT_PROVIDER, get_default_model
from selenium_agent.utils.paths import safe_output_path
from selenium_agent.selenium.locator_advisor import LocatorAdvisor
from selenium_agent.bdd.gherkin_advisor import GherkinAdvisor

logger = setup_logger("CoderAgent")

CODER_SYSTEM_PROMPT_PYTEST = f"""
You are an expert Selenium Python engineer. Generate pytest test code.

MANDATORY:
- Page Objects inherit: selenium_agent.selenium.base_page.BasePage
- Driver via: selenium_agent.selenium.driver_factory.DriverFactory
- NEVER time.sleep() — use WebDriverWait via BasePage methods
- pytest fixtures for driver setup/teardown
{LocatorAdvisor.get_priority_guide()}

Generate TWO files — respond with valid JSON only:
{{"files": [{{"filename": "pages/login_page.py", "content": "..."}}, {{"filename": "tests/test_login.py", "content": "..."}}]}}
"""

CODER_SYSTEM_PROMPT_BDD = f"""
You are an expert Selenium Python BDD engineer. Generate pytest-bdd + Gherkin code.

MANDATORY:
- Page Objects inherit: selenium_agent.selenium.base_page.BasePage
- Driver via: selenium_agent.selenium.driver_factory.DriverFactory
- NEVER time.sleep() — use WebDriverWait via BasePage methods
{LocatorAdvisor.get_priority_guide()}
{GherkinAdvisor.get_guide()}
{GherkinAdvisor.get_folder_structure()}

Generate FOUR files — respond with valid JSON only:
{{"files": [
  {{"filename": "features/login.feature", "content": "..."}},
  {{"filename": "pages/login_page.py", "content": "..."}},
  {{"filename": "step_definitions/test_login_steps.py", "content": "..."}},
  {{"filename": "conftest.py", "content": "..."}}
]}}
"""


class CoderAgent:
    def __init__(self, api_key: str, output_dir: str = "generated_tests",
                 provider: str = DEFAULT_PROVIDER, model: str | None = None):
        resolved_model = model or get_default_model(provider)
        self.client = create_llm_client(provider=provider, api_key=api_key, model=resolved_model)
        self.output_dir = output_dir

    def code(self, plan: dict) -> list[str]:
        mode = plan.get("mode", "pytest")
        logger.info(f"💻 Generating [{mode.upper()}] code...")

        system_prompt = (
            CODER_SYSTEM_PROMPT_BDD if mode == "bdd"
            else CODER_SYSTEM_PROMPT_PYTEST
        )

        raw = self.client.generate_text(
            system_prompt=system_prompt,
            user_prompt=f"Generate Selenium Python {mode} code:\n{json.dumps(plan, indent=2)}",
            max_tokens=4000,
        )

        if raw.startswith("```"):
            raw = raw.split("```")[1]
            if raw.startswith("json"):
                raw = raw[4:]
        raw = raw.strip()

        result = json.loads(raw)
        saved = []
        for file_info in result.get("files", []):
            filepath = safe_output_path(self.output_dir, file_info["filename"])
            filepath.parent.mkdir(parents=True, exist_ok=True)
            filepath.write_text(file_info["content"], encoding="utf-8")
            saved.append(str(filepath))
            logger.info(f"✅ Created: {filepath}")
        return saved
