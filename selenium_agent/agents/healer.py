"""
HEALER AGENT
============
Runs the generated tests, captures failures, fixes them, and retries.
Supports both Anthropic Claude and OpenAI as LLM providers.
"""

import json
import subprocess
from pathlib import Path
from selenium_agent.utils.logger import setup_logger
from selenium_agent.utils.llm import create_llm_client, DEFAULT_PROVIDER, get_default_model
from selenium_agent.utils.paths import resolve_input_path, safe_output_path

logger = setup_logger("HealerAgent")

HEALER_SYSTEM_PROMPT = """
You are an expert Selenium Python debugger and test healer.

You will receive:
1. The failing test code
2. The error/traceback from pytest

Your job is to fix the code and return the corrected version.

Common issues you must handle:
- NoSuchElementException → fix locator or add wait
- TimeoutException → increase wait or fix selector
- StaleElementReferenceException → re-fetch element
- ElementNotInteractableException → scroll into view or wait
- WebDriverException → handle driver setup issues

Respond with valid JSON only. No extra text. No markdown:
{
  "fixed_files": [
    {
      "filename": "pages/login_page.py",
      "content": "# corrected python code"
    }
  ],
  "fix_summary": "What was wrong and what was fixed"
}
"""


class HealerAgent:
    def __init__(
        self,
        api_key: str,
        output_dir: str = "generated_tests",
        max_retries: int = 3,
        provider: str = DEFAULT_PROVIDER,
        model: str | None = None,
    ):
        resolved_model = model or get_default_model(provider)
        self.client = create_llm_client(provider=provider, api_key=api_key, model=resolved_model)
        self.provider = provider
        self.model = resolved_model
        self.output_dir = output_dir
        self.max_retries = max_retries

    def _resolve_paths(self, file_paths: list[str]) -> dict[str, Path]:
        """Resolve file paths to absolute Paths, keyed by relative label."""
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
        """Run pytest on absolute paths and return (passed, output)."""
        cmd = ["python", "-m", "pytest"] + test_files + ["-v", "--tb=short"]
        logger.info(f"🧪 Running: {' '.join(cmd)}")

        result = subprocess.run(cmd, capture_output=True, text=True)
        passed = result.returncode == 0
        output = result.stdout + result.stderr
        return passed, output

    def _read_files(self, resolved: dict[str, Path]) -> dict[str, str]:
        """Read content of resolved files that exist."""
        contents: dict[str, str] = {}
        for label, absolute in resolved.items():
            if absolute.exists():
                contents[label] = absolute.read_text(encoding="utf-8")
            else:
                logger.warning(f"⚠️  File not found, skipping: {absolute}")
        return contents

    def _write_fixed_file(
        self,
        filename: str,
        content: str,
        known_files: dict[str, Path],
    ) -> Path:
        """Write a healed file back. Uses known_files mapping when available."""
        if filename in known_files:
            destination = known_files[filename]
        else:
            destination = safe_output_path(self.output_dir, filename)

        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_text(content, encoding="utf-8")
        return destination

    def heal(self, saved_files: list[str]) -> dict:
        resolved = self._resolve_paths(saved_files)
        test_absolutes = [
            str(p) for label, p in resolved.items()
            if label.startswith("tests" + "/") or "test_" in p.name
        ]

        for attempt in range(1, self.max_retries + 1):
            logger.info(f"🩺 Heal attempt {attempt}/{self.max_retries}")
            passed, output = self._run_tests(test_absolutes)

            if passed:
                logger.info("✅ All tests passing!")
                return {"status": "passed", "attempts": attempt, "output": output}

            logger.warning(f"❌ Tests failed on attempt {attempt}")
            logger.info("🔧 Asking LLM to fix...")

            file_contents = self._read_files(resolved)
            files_text = "\n\n".join(
                [f"# File: {k}\n{v}" for k, v in file_contents.items()]
            )

            raw = self.client.generate_text(
                system_prompt=HEALER_SYSTEM_PROMPT,
                user_prompt=(
                    f"These Selenium tests are failing. Please fix them.\n\n"
                    f"ERROR OUTPUT:\n{output}\n\n"
                    f"CURRENT CODE:\n{files_text}"
                ),
                max_tokens=4000,
            )

            if raw.startswith("```"):
                raw = raw.split("```")[1]
                if raw.startswith("json"):
                    raw = raw[4:]
            raw = raw.strip()

            result = json.loads(raw)
            fix_summary = result.get("fix_summary", "No summary")
            logger.info(f"🔧 Fix applied: {fix_summary}")

            for file_info in result.get("fixed_files", []):
                written = self._write_fixed_file(file_info["filename"], file_info["content"], resolved)
                logger.info(f"📝 Updated: {written}")

        logger.error(f"💀 Could not fix after {self.max_retries} attempts")
        return {"status": "failed", "attempts": self.max_retries, "output": output}
