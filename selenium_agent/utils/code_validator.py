"""
CODE VALIDATOR
==============
Static validation of LLM-generated Python before it touches disk.

Catches, without running a browser:
- syntax errors (ast.parse)
- forbidden patterns (time.sleep, find_element in tests, By in test files)

Used by the Coder (validate before save, retry on failure) and the
Healer (never overwrite a working file with a syntactically broken fix).
"""

from __future__ import annotations

import ast
import re
from dataclasses import dataclass, field


@dataclass
class ValidationResult:
    filename: str
    valid: bool
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


def _is_test_file(filename: str) -> bool:
    name = filename.replace("\\", "/").rsplit("/", 1)[-1]
    return name.startswith("test_") and name.endswith(".py")


def validate_python(filename: str, content: str) -> ValidationResult:
    """Validate one generated/fixed Python file. Feature files pass through."""
    result = ValidationResult(filename=filename, valid=True)

    if not filename.endswith(".py"):
        return result

    try:
        ast.parse(content)
    except SyntaxError as exc:
        result.valid = False
        result.errors.append(
            f"SyntaxError at line {exc.lineno}: {exc.msg}\n"
            f"    {(exc.text or '').rstrip()}"
        )
        return result  # no point pattern-checking broken code

    if re.search(r"\btime\.sleep\s*\(", content):
        result.warnings.append("time.sleep() found — use fluent_wait/explicit waits instead")

    if _is_test_file(filename):
        if re.search(r"from\s+selenium\.webdriver\.common\.by\s+import\s+By", content):
            result.warnings.append("By import in a test file — locators belong in page objects")
        if re.search(r"\bBy\.[A-Z_]+\s*,", content):
            result.warnings.append("Raw locator tuple in a test file — move it to the page object")
        # The driver fixture is deterministic framework scaffolding (conftest.py).
        # LLM-invented fixtures/drivers are the #1 source of collection errors.
        if re.search(r"def\s+driver\w*\s*\(", content):
            result.valid = False
            result.errors.append(
                "Test file defines its own driver fixture — conftest.py already "
                "provides `driver`; test functions must just accept it as a parameter"
            )
        if "DriverFactory" in content:
            result.valid = False
            result.errors.append(
                "Test file imports/uses DriverFactory — drivers come only from "
                "the conftest.py `driver` fixture"
            )

    return result


def validate_files(files: list[dict]) -> list[ValidationResult]:
    """Validate a list of {"filename": ..., "content": ...} dicts."""
    return [validate_python(f.get("filename", ""), f.get("content", "")) for f in files]


def format_errors(results: list[ValidationResult]) -> str:
    """Human/LLM-readable summary of validation failures."""
    lines = []
    for r in results:
        if not r.valid:
            lines.append(f"❌ {r.filename}:")
            lines.extend(f"   {e}" for e in r.errors)
    return "\n".join(lines)
