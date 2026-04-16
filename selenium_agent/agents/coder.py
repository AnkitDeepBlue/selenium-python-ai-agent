"""
CODER AGENT
===========
Takes the Planner's structured plan and generates Selenium Python test code.

Responsibilities:
- Generate Page Object Model classes
- Generate pytest test files
- Follow best practices (explicit waits, proper assertions)
- Save files to output directory
"""

import os
from pathlib import Path
from selenium_agent.utils.logger import setup_logger
from selenium_agent.utils.llm import create_llm_client, get_default_model
from selenium_agent.utils.paths import safe_output_path

logger = setup_logger("CoderAgent")

CODER_SYSTEM_PROMPT = """
You are an expert Selenium Python test automation engineer.

You will receive a structured test plan (JSON) and must generate production-quality Selenium Python code.

Rules:
1. Always use Page Object Model (POM) pattern
2. Use explicit waits (WebDriverWait) — NEVER use time.sleep()
3. Use pytest as the test framework
4. Add proper docstrings to every class and method
5. Use By.ID > By.CSS_SELECTOR > By.XPATH (in preference order)
6. Add @pytest.mark decorators from the plan
7. Handle exceptions gracefully
8. Generate TWO files:
   a) pages/<page_name>_page.py  — Page Object class
   b) tests/test_<page_name>.py  — pytest test file

Respond with valid JSON only:
{
  "files": [
    {
      "filename": "pages/login_page.py",
      "content": "# full python code here"
    },
    {
      "filename": "tests/test_login.py",
      "content": "# full python code here"
    }
  ]
}
"""


class CoderAgent:
    def __init__(
        self,
        api_key: str,
        output_dir: str = "generated_tests",
        provider: str = "anthropic",
        model: str | None = None,
    ):
        self.model = model or get_default_model(provider)
        self.client = create_llm_client(api_key=api_key, provider=provider, model=self.model)
        self.output_dir = output_dir

    def code(self, plan: dict) -> list[dict]:
        logger.info("💻 Generating Selenium Python code from plan...")

        import json
        raw = self.client.generate_text(
            system_prompt=CODER_SYSTEM_PROMPT,
            user_prompt=f"Generate Selenium Python code for this test plan:\n{json.dumps(plan, indent=2)}",
            max_tokens=4000,
        )
        if raw.startswith("```"):
            raw = raw.split("```")[1]
            if raw.startswith("json"):
                raw = raw[4:]
        raw = raw.strip()

        result = json.loads(raw)
        files = result.get("files", [])

        # Save files
        saved = []
        for file_info in files:
            filepath = safe_output_path(self.output_dir, file_info["filename"])
            os.makedirs(filepath.parent, exist_ok=True)
            with open(filepath, "w") as f:
                f.write(file_info["content"])
            saved.append(str(Path(self.output_dir) / file_info["filename"]))
            logger.info(f"✅ Created: {filepath}")

        return saved
