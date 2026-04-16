"""
HEALER AGENT
============
Runs the generated tests, captures failures, fixes them, and retries.

Responsibilities:
- Run pytest on generated files
- Parse error output
- Send errors to Claude for fixing
- Retry up to max_retries times
- Report final result
"""

import subprocess
import os
from pathlib import Path
from selenium_agent.utils.logger import setup_logger
from selenium_agent.utils.llm import create_llm_client, get_default_model
from selenium_agent.utils.paths import get_output_root, resolve_input_path, safe_output_path

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

Respond with valid JSON only:
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
        provider: str = "anthropic",
        model: str | None = None,
    ):
        self.model = model or get_default_model(provider)
        self.client = create_llm_client(api_key=api_key, provider=provider, model=self.model)
        self.output_dir = output_dir
        self.max_retries = max_retries

    def _file_label(self, file_path: Path) -> str:
        """Return a stable label for the LLM prompt and fix mapping."""
        output_root = get_output_root(self.output_dir)
        try:
            return str(file_path.relative_to(output_root))
        except ValueError:
            return str(file_path)

    def _resolve_paths(self, file_paths: list[str]) -> list[Path]:
        """Resolve incoming file paths consistently."""
        return [resolve_input_path(file_path, self.output_dir) for file_path in file_paths]

    def _run_tests(self, test_files: list[Path]) -> tuple[bool, str]:
        """Run pytest and return (passed, output)"""
        if not test_files:
            return False, "No pytest test files were provided to the healer."

        output_root = get_output_root(self.output_dir)
        run_in_output_dir = all(
            test_file.is_absolute() and output_root in test_file.parents
            for test_file in test_files
        )

        if run_in_output_dir:
            pytest_targets = [str(test_file.relative_to(output_root)) for test_file in test_files]
            cwd = str(output_root)
        else:
            pytest_targets = [str(test_file) for test_file in test_files]
            cwd = None

        cmd = ["python", "-m", "pytest"] + pytest_targets + ["-v", "--tb=short"]
        logger.info(f"🧪 Running: {' '.join(cmd)}")

        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            cwd=cwd
        )
        passed = result.returncode == 0
        output = result.stdout + result.stderr
        return passed, output

    def _read_files(self, file_paths: list[Path]) -> dict[str, str]:
        """Read file contents"""
        contents = {}
        for file_path in file_paths:
            if file_path.exists():
                with open(file_path) as f:
                    contents[self._file_label(file_path)] = f.read()
        return contents

    def _write_fixed_file(self, filename: str, content: str, known_files: dict[str, Path]) -> Path:
        """Write a fixed file either back to a known input file or inside output_dir."""
        if filename in known_files:
            filepath = known_files[filename]
        else:
            filepath = safe_output_path(self.output_dir, filename)

        os.makedirs(filepath.parent, exist_ok=True)
        with open(filepath, "w") as f:
            f.write(content)

        return filepath

    def heal(self, saved_files: list[str]) -> dict:
        import json

        resolved_files = self._resolve_paths(saved_files)
        test_files = [file_path for file_path in resolved_files if "test_" in file_path.name]
        known_files = {self._file_label(file_path): file_path for file_path in resolved_files}

        for attempt in range(1, self.max_retries + 1):
            logger.info(f"🩺 Heal attempt {attempt}/{self.max_retries}")
            passed, output = self._run_tests(test_files)

            if passed:
                logger.info("✅ All tests passing!")
                return {"status": "passed", "attempts": attempt, "output": output}

            logger.warning(f"❌ Tests failed on attempt {attempt}")
            logger.info("🔧 Asking Claude to fix...")

            # Read current file contents
            file_contents = self._read_files(resolved_files)
            files_text = "\n\n".join(
                [f"# File: {k}\n{v}" for k, v in file_contents.items()]
            )

            raw = self.client.generate_text(
                system_prompt=HEALER_SYSTEM_PROMPT,
                user_prompt=f"""
These Selenium tests are failing. Please fix them.

ERROR OUTPUT:
{output}

CURRENT CODE:
{files_text}
""",
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

            # Write fixed files
            for file_info in result.get("fixed_files", []):
                filepath = self._write_fixed_file(
                    filename=file_info["filename"],
                    content=file_info["content"],
                    known_files=known_files,
                )
                logger.info(f"📝 Updated: {filepath}")

        logger.error(f"💀 Could not fix after {self.max_retries} attempts")
        return {"status": "failed", "attempts": self.max_retries, "output": output}
