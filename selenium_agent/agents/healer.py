"""HEALER AGENT"""

import json
import subprocess
from pathlib import Path
from selenium_agent.utils.logger import setup_logger
from selenium_agent.utils.llm import create_llm_client, DEFAULT_PROVIDER, get_default_model
from selenium_agent.utils.paths import resolve_input_path, safe_output_path
from selenium_agent.selenium.error_map import SeleniumErrorMap

logger = setup_logger("HealerAgent")

HEALER_SYSTEM_PROMPT = """
You are an expert Selenium Python debugger.
Fix failing Selenium tests using the error analysis provided.

FIXES TO APPLY:
- NoSuchElementException → Add WebDriverWait
- TimeoutException → Increase timeout or fix locator
- StaleElementReferenceException → Re-fetch element
- ElementNotInteractableException → Scroll + wait for clickable
- ElementClickInterceptedException → Dismiss overlay or JS click
- time.sleep() → Replace with WebDriverWait

All Page Objects must inherit BasePage. All drivers must use DriverFactory.

Respond with valid JSON only:
{"fixed_files": [{"filename": "...", "content": "..."}], "fix_summary": "..."}
"""


class HealerAgent:
    def __init__(self, api_key: str, output_dir: str = "generated_tests",
                 max_retries: int = 3, provider: str = DEFAULT_PROVIDER,
                 model: str | None = None):
        resolved_model = model or get_default_model(provider)
        self.client = create_llm_client(provider=provider, api_key=api_key, model=resolved_model)
        self.output_dir = output_dir
        self.max_retries = max_retries

    def _resolve_paths(self, file_paths: list[str]) -> dict[str, Path]:
        resolved: dict[str, Path] = {}
        for fp in file_paths:
            absolute = resolve_input_path(fp, self.output_dir)
            output_root = Path(self.output_dir).resolve()
            try:
                label = str(absolute.relative_to(output_root))
            except ValueError:
                label = absolute.name
            resolved[label] = absolute
        return resolved

    def _run_tests(self, test_files: list[str]) -> tuple[bool, str]:
        cmd = ["python", "-m", "pytest"] + test_files + ["-v", "--tb=short"]
        logger.info(f"🧪 Running: {' '.join(cmd)}")
        result = subprocess.run(cmd, capture_output=True, text=True)
        return result.returncode == 0, result.stdout + result.stderr

    def _read_files(self, resolved: dict[str, Path]) -> dict[str, str]:
        contents: dict[str, str] = {}
        for label, absolute in resolved.items():
            if absolute.exists():
                contents[label] = absolute.read_text(encoding="utf-8")
            else:
                logger.warning(f"⚠️  Not found: {absolute}")
        return contents

    def _write_fixed_file(self, filename: str, content: str, known_files: dict[str, Path]) -> Path:
        destination = known_files.get(filename) or safe_output_path(self.output_dir, filename)
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_text(content, encoding="utf-8")
        return destination

    def heal(self, saved_files: list[str]) -> dict:
        resolved = self._resolve_paths(saved_files)
        test_absolutes = [
            str(p) for label, p in resolved.items()
            if label.startswith("tests/") or "test_" in p.name
        ]

        for attempt in range(1, self.max_retries + 1):
            logger.info(f"🩺 Heal attempt {attempt}/{self.max_retries}")
            passed, output = self._run_tests(test_absolutes)

            if passed:
                logger.info("✅ All tests passing!")
                return {"status": "passed", "attempts": attempt, "output": output}

            logger.warning(f"❌ Failed on attempt {attempt}")
            known_fix = SeleniumErrorMap.get_fix_summary(output)
            file_contents = self._read_files(resolved)
            files_text = "\n\n".join([f"# File: {k}\n{v}" for k, v in file_contents.items()])

            raw = self.client.generate_text(
                system_prompt=HEALER_SYSTEM_PROMPT,
                user_prompt=(
                    f"Fix these failing Selenium tests.\n\n"
                    f"SELENIUM ERROR ANALYSIS:\n{known_fix}\n\n"
                    f"PYTEST OUTPUT:\n{output}\n\n"
                    f"CODE:\n{files_text}"
                ),
                max_tokens=4000,
            )

            if raw.startswith("```"):
                raw = raw.split("```")[1]
                if raw.startswith("json"):
                    raw = raw[4:]
            raw = raw.strip()

            result = json.loads(raw)
            logger.info(f"🔧 Fix: {result.get('fix_summary', 'No summary')}")

            for file_info in result.get("fixed_files", []):
                written = self._write_fixed_file(file_info["filename"], file_info["content"], resolved)
                logger.info(f"📝 Updated: {written}")

        logger.error(f"💀 Could not fix after {self.max_retries} attempts")
        return {"status": "failed", "attempts": self.max_retries, "output": output}
