"""
PROJECT SCANNER
===============
Scans an existing Selenium Python project and detects:
- Folder structure (pages/, page_objects/, src/, etc.)
- Base class (BasePage, BaseTest, PageBase, etc.)
- Test framework (pytest, unittest, pytest-bdd)
- Naming conventions (test_login.py vs LoginTest.py)
- Import style (relative vs absolute)
- Existing conftest.py, fixtures
- Driver setup pattern

This context is passed to Planner + Coder so generated code
fits INTO the existing project, not alongside it.
"""

from __future__ import annotations
import os
import re
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class ProjectProfile:
    """
    Complete profile of a detected Selenium Python project.
    Passed to Planner and Coder agents as context.
    """

    # Root directory
    root: str = ""

    # Folder structure
    pages_dir: str = "pages"                    # where Page Objects live
    tests_dir: str = "tests"                    # where test files live
    steps_dir: str = "step_definitions"         # BDD steps dir
    features_dir: str = "features"              # BDD features dir
    utils_dir: str = ""                         # utils/helpers dir
    base_dir: str = ""                          # base classes dir

    # Framework
    test_framework: str = "pytest"              # pytest | unittest | pytest-bdd
    has_bdd: bool = False
    has_pytest: bool = True
    has_conftest: bool = False

    # Base classes
    base_page_class: str = "BasePage"           # existing base page name
    base_page_import: str = ""                  # full import path
    base_test_class: str = ""                   # existing base test name
    base_test_import: str = ""

    # Driver setup
    driver_setup: str = "fixture"               # fixture | setUp | class-level
    driver_scope: str = "function"              # function | class | module
    driver_fixture_name: str = "driver"         # actual fixture name (e.g. 'browser')
    browser: str = "chrome"
    headless: bool = False

    # Naming conventions
    test_file_prefix: str = "test_"             # test_login.py
    test_file_suffix: str = ""                  # LoginTest.py → suffix=Test
    page_file_suffix: str = "_page"             # login_page.py
    test_func_prefix: str = "test_"

    # Import style
    import_style: str = "absolute"              # absolute | relative
    project_package: str = ""                   # top-level package name

    # Existing files (for context)
    existing_page_files: list = field(default_factory=list)
    existing_test_files: list = field(default_factory=list)
    existing_conftest_files: list = field(default_factory=list)

    # Raw snippets for LLM context
    sample_page_code: str = ""                  # snippet from existing page object
    sample_test_code: str = ""                  # snippet from existing test
    sample_conftest_code: str = ""              # snippet from conftest

    def to_llm_context(self) -> str:
        """
        Format the project profile as a clear context string
        for injection into Planner and Coder prompts.
        """
        lines = [
            "=== EXISTING PROJECT PROFILE ===",
            f"Root              : {self.root}",
            f"Pages folder      : {self.pages_dir}/",
            f"Tests folder      : {self.tests_dir}/",
            f"Test framework    : {self.test_framework}",
            f"BDD detected      : {self.has_bdd}",
            f"Base Page class   : {self.base_page_class}",
            f"Base Page import  : {self.base_page_import or 'not detected'}",
            f"Driver setup      : {self.driver_setup} (scope={self.driver_scope}, "
            f"fixture name='{self.driver_fixture_name}')",
            f"Browser           : {self.browser} (headless={self.headless})",
            f"Test file pattern : {self.test_file_prefix}<name>.py",
            f"Page file pattern : <name>{self.page_file_suffix}.py",
            f"Import style      : {self.import_style}",
            f"Package           : {self.project_package or 'none'}",
        ]

        if self.existing_page_files:
            lines.append(f"\nExisting pages    : {', '.join(self.existing_page_files[:5])}")
        if self.existing_test_files:
            lines.append(f"Existing tests    : {', '.join(self.existing_test_files[:5])}")

        if self.sample_page_code:
            lines.append(f"\n--- SAMPLE PAGE OBJECT (follow this style) ---\n{self.sample_page_code}\n---")
        if self.sample_test_code:
            lines.append(f"\n--- SAMPLE TEST FILE (follow this style) ---\n{self.sample_test_code}\n---")
        if self.sample_conftest_code:
            lines.append(f"\n--- CONFTEST (follow this fixture pattern) ---\n{self.sample_conftest_code}\n---")

        lines.append("\nINSTRUCTION: Generated code MUST follow this exact project structure,")
        lines.append("import style, base class, and naming convention shown above.")
        lines.append("=================================")

        return "\n".join(lines)


class ProjectScanner:
    """
    Scans an existing Selenium Python project and returns a ProjectProfile.

    Usage:
        scanner = ProjectScanner("/path/to/existing/project")
        profile = scanner.scan()
        print(profile.to_llm_context())
    """

    # Known folder name patterns
    PAGES_DIRS     = ["pages", "page_objects", "pageobjects", "page_object",
                      "pom", "page_models", "screens", "views", "ui"]
    TESTS_DIRS     = ["tests", "test", "test_suite", "testing", "functional",
                      "e2e", "integration", "specs", "test_cases"]
    FEATURES_DIRS  = ["features", "feature", "bdd", "scenarios"]
    STEPS_DIRS     = ["step_definitions", "steps", "step_defs", "stepdefs"]
    UTILS_DIRS     = ["utils", "utilities", "helpers", "common", "lib"]
    BASE_DIRS      = ["base", "core", "foundation", "abstract"]

    # Known base class name patterns
    BASE_PAGE_NAMES = ["BasePage", "BasePageObject", "PageBase", "BaseUI",
                       "SeleniumBase", "WebPage", "AbstractPage", "PageObject",
                       "BaseDriver", "DriverBase"]

    def __init__(self, project_root: str):
        self.root = Path(project_root).resolve()
        self.profile = ProjectProfile(root=str(self.root))

    def scan(self) -> ProjectProfile:
        """
        Full project scan. Returns populated ProjectProfile.
        Safe to call on any Python project — read-only, no writes.
        """
        if not self.root.exists():
            raise ValueError(f"Project root does not exist: {self.root}")

        self._detect_folders()
        self._detect_framework()
        self._detect_base_classes()
        self._detect_driver_setup()
        self._detect_naming_conventions()
        self._detect_import_style()
        self._collect_existing_files()
        self._extract_code_samples()

        return self.profile

    # ── Detection methods ─────────────────────────────────────────────

    def _detect_folders(self):
        """Find pages, tests, features, steps directories.

        Shallowest directory wins: a project's real `pages/` at the root
        must beat any deeper `something/pages/` twin."""
        all_dirs = sorted(
            (d for d in self.root.rglob("*")
             if d.is_dir() and not self._is_ignored(d)),
            key=lambda d: len(d.parts),
        )
        dir_names: dict = {}
        for d in all_dirs:
            dir_names.setdefault(d.name.lower(), d)

        for name in self.PAGES_DIRS:
            if name in dir_names:
                self.profile.pages_dir = str(
                    dir_names[name].relative_to(self.root)
                )
                break

        for name in self.TESTS_DIRS:
            if name in dir_names:
                self.profile.tests_dir = str(
                    dir_names[name].relative_to(self.root)
                )
                break

        for name in self.FEATURES_DIRS:
            if name in dir_names:
                self.profile.features_dir = str(
                    dir_names[name].relative_to(self.root)
                )
                break

        for name in self.STEPS_DIRS:
            if name in dir_names:
                self.profile.steps_dir = str(
                    dir_names[name].relative_to(self.root)
                )
                break

        for name in self.UTILS_DIRS:
            if name in dir_names:
                self.profile.utils_dir = str(
                    dir_names[name].relative_to(self.root)
                )
                break

        for name in self.BASE_DIRS:
            if name in dir_names:
                self.profile.base_dir = str(
                    dir_names[name].relative_to(self.root)
                )
                break

    def _detect_framework(self):
        """Detect test framework from imports and file contents."""
        py_files = list(self.root.rglob("*.py"))[:50]  # limit for speed

        has_pytest_bdd  = False
        has_pytest      = False
        has_unittest    = False
        has_conftest    = False

        for f in py_files:
            if self._is_ignored(f):
                continue
            try:
                content = f.read_text(encoding="utf-8", errors="ignore")
                if "pytest_bdd" in content or "from pytest_bdd" in content:
                    has_pytest_bdd = True
                if "import pytest" in content or "from pytest" in content:
                    has_pytest = True
                if "unittest" in content:
                    has_unittest = True
                if f.name == "conftest.py":
                    has_conftest = True
            except Exception:
                continue

        self.profile.has_bdd       = has_pytest_bdd
        self.profile.has_pytest    = has_pytest
        self.profile.has_conftest  = has_conftest

        if has_pytest_bdd:
            self.profile.test_framework = "pytest-bdd"
        elif has_pytest:
            self.profile.test_framework = "pytest"
        elif has_unittest:
            self.profile.test_framework = "unittest"

    def _detect_base_classes(self):
        """Find existing BasePage / BaseTest class definitions."""
        py_files = list(self.root.rglob("*.py"))[:100]

        for f in py_files:
            if self._is_ignored(f):
                continue
            try:
                content = f.read_text(encoding="utf-8", errors="ignore")
            except Exception:
                continue

            # Look for class definitions matching known base names
            class_matches = re.findall(r"class\s+(\w+)\s*[\(:]", content)
            for cls_name in class_matches:
                if any(base.lower() in cls_name.lower() for base in
                       ["basepage", "pagebase", "pageobject", "baseui",
                        "seleniumbase", "webpage", "abstractpage", "basedriver"]):
                    self.profile.base_page_class = cls_name
                    rel = f.relative_to(self.root)
                    # Build import path
                    parts = list(rel.with_suffix("").parts)
                    self.profile.base_page_import = ".".join(parts)
                    break

                if any(base.lower() in cls_name.lower() for base in
                       ["basetest", "testbase", "seleniumtest", "webtest"]):
                    self.profile.base_test_class = cls_name
                    rel = f.relative_to(self.root)
                    parts = list(rel.with_suffix("").parts)
                    self.profile.base_test_import = ".".join(parts)
                    break

    def _detect_driver_setup(self):
        """Detect how the driver is initialized (fixture/setUp/class)."""
        conftest_files = list(self.root.rglob("conftest.py"))
        test_files     = list(self.root.rglob("test_*.py"))[:20]

        for f in conftest_files + test_files:
            if self._is_ignored(f):
                continue
            try:
                content = f.read_text(encoding="utf-8", errors="ignore")
            except Exception:
                continue

            # Fixture pattern
            if "@pytest.fixture" in content and "driver" in content.lower():
                self.profile.driver_setup = "fixture"
                scope_match = re.search(r'@pytest\.fixture\s*\(\s*scope=["\'](\w+)["\']', content)
                if scope_match:
                    self.profile.driver_scope = scope_match.group(1)
                # The fixture NAME matters — generated tests must request the
                # project's actual fixture ('browser', 'web_driver', ...),
                # not assume it is called 'driver'.
                name_match = re.search(
                    r"@pytest\.fixture(?:\([^)]*\))?\s*\ndef\s+(\w+)\s*\(", content
                )
                if name_match and f.name == "conftest.py":
                    self.profile.driver_fixture_name = name_match.group(1)

            # unittest setUp pattern
            elif "def setUp(self)" in content:
                self.profile.driver_setup = "setUp"

            # Browser detection
            for browser in ["chrome", "firefox", "edge", "safari"]:
                if browser in content.lower():
                    self.profile.browser = browser
                    break

            # Headless detection
            if "headless" in content.lower():
                self.profile.headless = True

    def _detect_naming_conventions(self):
        """Detect test file and page file naming patterns."""
        py_files = list(self.root.rglob("*.py"))

        test_prefixed  = 0  # test_login.py
        test_suffixed  = 0  # LoginTest.py
        page_suffixed  = 0  # login_page.py
        page_prefixed  = 0  # page_login.py

        for f in py_files:
            if self._is_ignored(f):
                continue
            name = f.stem  # filename without extension
            if name.startswith("test_"):
                test_prefixed += 1
            elif name.endswith("Test") or name.endswith("Tests"):
                test_suffixed += 1
            if name.endswith("_page") or name.endswith("_Page"):
                page_suffixed += 1
            elif name.endswith("Page") or name.endswith("PageObject"):
                page_prefixed += 1

        # Set based on majority
        if test_suffixed > test_prefixed:
            self.profile.test_file_prefix = ""
            self.profile.test_file_suffix = "Test"
        else:
            self.profile.test_file_prefix = "test_"
            self.profile.test_file_suffix = ""

        if page_prefixed > page_suffixed:
            self.profile.page_file_suffix = "Page"
        else:
            self.profile.page_file_suffix = "_page"

    def _detect_import_style(self):
        """Detect relative vs absolute imports."""
        py_files = list(self.root.rglob("*.py"))[:30]
        relative = 0
        absolute = 0

        for f in py_files:
            if self._is_ignored(f):
                continue
            try:
                content = f.read_text(encoding="utf-8", errors="ignore")
            except Exception:
                continue

            if re.search(r"^from \.", content, re.MULTILINE):
                relative += 1
            if re.search(r"^from [a-zA-Z]", content, re.MULTILINE):
                absolute += 1

        self.profile.import_style = "relative" if relative > absolute else "absolute"

        # Try to detect top-level package
        init_files = [
            f for f in self.root.glob("*/__init__.py") if not self._is_ignored(f)
        ]
        if init_files:
            self.profile.project_package = init_files[0].parent.name

    def _collect_existing_files(self):
        """Collect lists of existing page and test files."""
        pages_path = self.root / self.profile.pages_dir
        tests_path = self.root / self.profile.tests_dir

        if pages_path.exists():
            self.profile.existing_page_files = [
                f.name for f in pages_path.rglob("*.py")
                if not f.name.startswith("__")
            ][:10]

        if tests_path.exists():
            self.profile.existing_test_files = [
                f.name for f in tests_path.rglob("*.py")
                if not f.name.startswith("__")
            ][:10]

        self.profile.existing_conftest_files = [
            str(f.relative_to(self.root))
            for f in self.root.rglob("conftest.py")
        ][:5]

    def _extract_code_samples(self):
        """Extract small code snippets as style examples for LLM."""
        pages_path = self.root / self.profile.pages_dir
        tests_path = self.root / self.profile.tests_dir

        # Sample page object (first 40 lines)
        if pages_path.exists():
            for f in pages_path.rglob("*.py"):
                if f.name.startswith("__"):
                    continue
                try:
                    lines = f.read_text(encoding="utf-8", errors="ignore").splitlines()
                    self.profile.sample_page_code = "\n".join(lines[:40])
                    break
                except Exception:
                    continue

        # Sample test file (first 40 lines)
        if tests_path.exists():
            for f in tests_path.rglob("*.py"):
                if f.name.startswith("__"):
                    continue
                try:
                    lines = f.read_text(encoding="utf-8", errors="ignore").splitlines()
                    self.profile.sample_test_code = "\n".join(lines[:40])
                    break
                except Exception:
                    continue

        # Conftest sample
        for conftest_path in self.root.rglob("conftest.py"):
            try:
                lines = conftest_path.read_text(encoding="utf-8", errors="ignore").splitlines()
                self.profile.sample_conftest_code = "\n".join(lines[:30])
                break
            except Exception:
                continue

    def _is_ignored(self, path: Path) -> bool:
        """Skip venv, cache, git, node_modules etc.

        Also skips the agent's OWN output folders (generated_tests/, specs/):
        scanning them would make the profile describe the agent's previous
        output instead of the user's real framework — circular pollution.
        """
        ignored = {".venv", "venv", "__pycache__", ".git", ".idea",
                   "node_modules", ".pytest_cache", "dist", "build",
                   ".eggs", "*.egg-info", ".tox", ".mypy_cache",
                   "generated_tests", "specs"}
        return any(part in ignored for part in path.parts)
