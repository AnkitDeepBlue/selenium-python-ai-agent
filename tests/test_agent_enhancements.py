"""Unit tests for the v0.2.0 agent enhancements (no browser / no LLM calls)."""

import json
from pathlib import Path

import pytest

from selenium_agent.agents.definitions import write_agent_definitions
from selenium_agent.agents.healer import HealerAgent
from selenium_agent.utils.code_validator import validate_python, validate_files, format_errors
from selenium_agent.utils.json_utils import LLMJSONError, extract_json_object
from selenium_agent.utils.spec_writer import load_plan, render_markdown, save_spec, slugify


def make_healer(output_dir: Path) -> HealerAgent:
    healer = HealerAgent.__new__(HealerAgent)
    healer.output_dir = str(output_dir)
    healer.max_retries = 1
    healer.client = None
    return healer


# ── json_utils ─────────────────────────────────────────────────────────


def test_extract_json_plain_object():
    assert extract_json_object('{"a": 1}') == {"a": 1}


def test_extract_json_with_markdown_fences_and_prose():
    raw = 'Here is the plan:\n```json\n{"mode": "pytest", "url": "https://x.com"}\n```\nDone!'
    assert extract_json_object(raw)["url"] == "https://x.com"


def test_extract_json_repairs_truncated_output():
    raw = '{"files": [{"filename": "a.py", "content": "print(1)'
    parsed = extract_json_object(raw)
    assert parsed["files"][0]["filename"] == "a.py"


def test_extract_json_removes_trailing_commas():
    assert extract_json_object('{"a": [1, 2,], "b": 3,}') == {"a": [1, 2], "b": 3}


def test_extract_json_raises_on_garbage():
    with pytest.raises(LLMJSONError):
        extract_json_object("I could not produce a plan, sorry.")


# ── code_validator ─────────────────────────────────────────────────────


def test_validator_accepts_valid_python():
    result = validate_python("pages/login_page.py", "class LoginPage:\n    pass\n")
    assert result.valid and not result.errors


def test_validator_rejects_syntax_errors():
    result = validate_python("tests/test_x.py", "def broken(:\n    pass\n")
    assert not result.valid
    assert "SyntaxError" in result.errors[0]


def test_validator_warns_on_by_import_in_test_file():
    content = "from selenium.webdriver.common.by import By\n\ndef test_a():\n    pass\n"
    result = validate_python("tests/test_a.py", content)
    assert result.valid  # warning, not error
    assert any("By import" in w for w in result.warnings)


def test_validator_skips_non_python_files():
    result = validate_python("features/login.feature", "Feature: Login\n")
    assert result.valid


def test_format_errors_lists_broken_files():
    results = validate_files([
        {"filename": "ok.py", "content": "x = 1\n"},
        {"filename": "bad.py", "content": "def (:\n"},
    ])
    text = format_errors(results)
    assert "bad.py" in text and "ok.py" not in text


# ── spec_writer ────────────────────────────────────────────────────────


SAMPLE_PLAN = {
    "mode": "pytest",
    "url": "https://www.saucedemo.com",
    "browser": "chrome",
    "headless": True,
    "test_scenarios": [
        {
            "id": "TC001",
            "name": "valid login",
            "description": "standard user logs in",
            "steps": ["open LoginPage.URL", "type username", "click login"],
            "expected_result": "inventory page shown",
            "test_data": {"username": "standard_user"},
        }
    ],
    "page_objects_needed": ["LoginPage", "InventoryPage"],
    "locators": [
        {
            "page_object": "LoginPage",
            "element": "username input",
            "css": "#user-name",
            "wait_condition": "visible",
        }
    ],
}


def test_slugify():
    assert slugify("Test the Login page!") == "test-the-login-page"


def test_render_markdown_contains_scenarios_and_locators():
    md = render_markdown(SAMPLE_PLAN, "test the login page")
    assert "TC001" in md
    assert "`#user-name`" in md
    assert "LoginPage" in md


def test_save_and_load_plan_roundtrip(tmp_path: Path):
    paths = save_spec(SAMPLE_PLAN, "test the login page", specs_dir=tmp_path / "specs")
    assert Path(paths["markdown"]).exists()
    assert Path(paths["json"]).exists()

    loaded = load_plan(paths["json"])
    assert loaded == SAMPLE_PLAN

    # Pointing at the .md loads the .json twin
    loaded_via_md = load_plan(paths["markdown"])
    assert loaded_via_md == SAMPLE_PLAN


def test_load_plan_missing_file_raises(tmp_path: Path):
    with pytest.raises(FileNotFoundError):
        load_plan(tmp_path / "nope.json")


# ── init-agents ────────────────────────────────────────────────────────


def test_write_agent_definitions(tmp_path: Path):
    written = write_agent_definitions(tmp_path)
    assert len(written) == 3
    names = {Path(p).name for p in written}
    assert names == {
        "selenium-test-planner.md",
        "selenium-test-generator.md",
        "selenium-test-healer.md",
    }
    for p in written:
        content = Path(p).read_text()
        assert content.startswith("---")
        assert "selenium-agent" in content


# ── healer helpers ─────────────────────────────────────────────────────


def test_healer_extracts_urls_from_output_and_files(tmp_path: Path):
    output_dir = tmp_path / "generated_tests"
    page = output_dir / "pages" / "login_page.py"
    page.parent.mkdir(parents=True)
    page.write_text("class LoginPage:\n    URL = 'https://www.saucedemo.com'\n")

    healer = make_healer(output_dir)
    resolved = {"pages/login_page.py": page}

    pytest_output = "AssertionError: expected https://www.saucedemo.com/inventory.html"
    urls = healer._extract_urls(resolved, pytest_output=pytest_output)

    assert urls[0] == "https://www.saucedemo.com/inventory.html"
    assert "https://www.saucedemo.com" in urls


def test_healer_sanitize_strips_by_import():
    healer = make_healer(Path("."))
    content = (
        "import pytest\n"
        "from selenium.webdriver.common.by import By\n"
        "def test_x():\n    pass\n"
    )
    cleaned = healer._sanitize_test_file(content)
    assert "import By" not in cleaned
    assert "def test_x" in cleaned


def test_healer_merge_restores_dropped_functions():
    healer = make_healer(Path("."))
    original = "def test_a():\n    assert 1\n\n\ndef test_b():\n    assert 2\n"
    fixed = "def test_a():\n    assert True\n"  # LLM dropped test_b
    merged = healer._merge_preserve_others(original, fixed, "test_a")
    assert "def test_b" in merged
    assert "assert True" in merged


def test_healer_trim_output_keeps_tail():
    healer = make_healer(Path("."))
    output = "x" * 20000 + "FAILURE_MARKER"
    trimmed = healer._trim_output(output)
    assert trimmed.endswith("FAILURE_MARKER")
    assert len(trimmed) < 20000


# ── link relevance ranking (generic — scores ANY instruction's words) ──


def test_rank_links_prefers_instruction_relevant_pages():
    from selenium_agent.selenium.locator_scanner import rank_links_by_relevance

    links = [
        {"href": "https://shop.com/search", "text": "Search"},
        {"href": "https://shop.com/pages/about-us", "text": "About us"},
        {"href": "https://shop.com/account/register", "text": "Sign up"},
        {"href": "https://shop.com/account/login", "text": "Log in"},
    ]
    instruction = ("click the Sign up link to reach the Create Account form, "
                   "fill it and click the Create button, then log out")
    ranked = rank_links_by_relevance(links, instruction)

    assert ranked[0] == "https://shop.com/account/register"
    assert ranked.index("https://shop.com/account/login") < ranked.index("https://shop.com/search")


def test_rank_links_works_for_a_completely_different_flow():
    from selenium_agent.selenium.locator_scanner import rank_links_by_relevance

    links = [
        {"href": "https://shop.com/account/register", "text": "Sign up"},
        {"href": "https://shop.com/collections/all", "text": "Catalog"},
        {"href": "https://shop.com/cart", "text": "Cart"},
    ]
    ranked = rank_links_by_relevance(links, "add two items to the cart and checkout as guest")
    assert ranked[0] == "https://shop.com/cart"


def test_rank_links_keeps_document_order_when_nothing_matches():
    from selenium_agent.selenium.locator_scanner import rank_links_by_relevance

    links = [{"href": "https://a.com/x", "text": "X"}, {"href": "https://a.com/y", "text": "Y"}]
    assert rank_links_by_relevance(links, "unrelated words entirely") == \
        ["https://a.com/x", "https://a.com/y"]


def test_validator_rejects_driver_fixture_in_test_file():
    content = (
        "import pytest\n"
        "@pytest.fixture\n"
        "def driver():\n    yield None\n"
        "def test_a(driver):\n    pass\n"
    )
    result = validate_python("tests/test_a.py", content)
    assert not result.valid
    assert any("driver fixture" in e for e in result.errors)


def test_validator_rejects_driverfactory_in_test_file():
    content = (
        "from selenium_agent.selenium.driver_factory import DriverFactory\n"
        "def test_a():\n    d = DriverFactory.create()\n"
    )
    result = validate_python("tests/test_a.py", content)
    assert not result.valid
    assert any("DriverFactory" in e for e in result.errors)


# ── conftest scaffolding ───────────────────────────────────────────────


def test_conftest_registers_plan_markers(tmp_path: Path):
    from selenium_agent.agents.coder import CoderAgent

    coder = CoderAgent.__new__(CoderAgent)
    coder.output_dir = str(tmp_path)

    plan = {
        "pytest_markers": ["smoke"],
        "scenarios": [{"tags": ["@e2e", "checkout"]}],
    }
    coder._write_conftest(headless=True, markers=coder._collect_markers(plan))

    content = (tmp_path / "conftest.py").read_text()
    assert "HEADLESS = True" in content
    assert "def pytest_configure(config):" in content
    assert "'checkout'" in content and "'e2e'" in content and "'smoke'" in content
    assert "def driver():" in content


def test_validator_rejects_skip_placeholders_in_test_files():
    content = (
        "import pytest\n"
        "def test_a(driver):\n"
        "    pytest.skip('Pending: locators not provided')\n"
    )
    result = validate_python("tests/test_a.py", content)
    assert not result.valid
    assert any("skip" in e.lower() for e in result.errors)


def test_healer_green_requires_actual_passes():
    from selenium_agent.agents.healer import HealerAgent

    green = HealerAgent._is_green
    assert green(True, "===== 3 passed in 12.3s =====")
    assert not green(True, "===== 1 skipped in 3.5s =====")            # all skipped
    assert not green(True, "SKIPPED [1] x.py: Pending: locators\n1 passed, 1 skipped")  # pending placeholder
    assert not green(False, "===== 2 passed, 1 failed =====")          # non-zero exit
    assert green(True, "===== 2 passed, 1 deselected in 5s =====")
