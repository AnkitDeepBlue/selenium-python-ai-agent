from pathlib import Path

import pytest

import selenium_agent
from selenium_agent.agents.healer import HealerAgent
from selenium_agent.core.orchestrator import Orchestrator
from selenium_agent.utils.llm import (
    format_missing_api_key_error,
    get_api_key_env_var,
    get_default_model,
    normalize_provider,
    resolve_api_key,
)
from selenium_agent.utils.paths import resolve_input_path, safe_output_path


def make_healer(output_dir: Path) -> HealerAgent:
    healer = HealerAgent.__new__(HealerAgent)
    healer.output_dir = str(output_dir)
    healer.max_retries = 1
    healer.client = None
    healer.model = "test-model"
    return healer


def test_package_import_exposes_public_api():
    assert selenium_agent.__version__ == "0.1.0"
    assert selenium_agent.SeleniumAgent.__name__ == "Orchestrator"


def test_provider_helpers_support_anthropic_and_openai(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("OPENAI_API_KEY", "openai-key")

    assert normalize_provider("OpenAI") == "openai"
    assert get_api_key_env_var("openai") == "OPENAI_API_KEY"
    assert get_default_model("openai") == "gpt-5-mini"
    assert resolve_api_key("openai") == "openai-key"


def test_missing_api_key_error_mentions_selected_provider():
    message = format_missing_api_key_error("openai")

    assert "OpenAI API key required!" in message
    assert "OPENAI_API_KEY" in message


def test_orchestrator_uses_provider_specific_env_var(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("OPENAI_API_KEY", "openai-key")

    planner_class = Orchestrator.__init__.__globals__["PlannerAgent"]
    coder_class = Orchestrator.__init__.__globals__["CoderAgent"]
    healer_class = Orchestrator.__init__.__globals__["HealerAgent"]

    original_planner_init = planner_class.__init__
    original_coder_init = coder_class.__init__
    original_healer_init = healer_class.__init__

    def fake_agent_init(
        self,
        api_key: str,
        provider: str = "anthropic",
        model: str | None = None,
        **_: object,
    ):
        self.client = None
        self.model = model
        self.provider = provider
        self.api_key = api_key

    planner_class.__init__ = fake_agent_init
    coder_class.__init__ = fake_agent_init
    healer_class.__init__ = fake_agent_init
    try:
        orchestrator = Orchestrator(provider="openai")
    finally:
        planner_class.__init__ = original_planner_init
        coder_class.__init__ = original_coder_init
        healer_class.__init__ = original_healer_init

    assert orchestrator.provider == "openai"
    assert orchestrator.api_key == "openai-key"
    assert orchestrator.model == "gpt-5-mini"


def test_safe_output_path_rejects_parent_traversal(tmp_path: Path):
    with pytest.raises(ValueError):
        safe_output_path(str(tmp_path), "../escape.py")


def test_resolve_input_path_supports_output_prefixed_relative_paths(tmp_path: Path):
    output_dir = tmp_path / "generated_tests"
    test_file = output_dir / "tests" / "test_login.py"
    test_file.parent.mkdir(parents=True)
    test_file.write_text("def test_login():\n    assert True\n")

    resolved = resolve_input_path(str(Path("generated_tests") / "tests" / "test_login.py"), str(output_dir))

    assert resolved == test_file.resolve()


def test_healer_reads_output_prefixed_paths_without_double_join(tmp_path: Path):
    output_dir = tmp_path / "generated_tests"
    page_file = output_dir / "pages" / "login_page.py"
    page_file.parent.mkdir(parents=True)
    page_file.write_text("class LoginPage:\n    pass\n")

    healer = make_healer(output_dir)
    resolved_files = healer._resolve_paths([str(Path("generated_tests") / "pages" / "login_page.py")])

    contents = healer._read_files(resolved_files)

    assert contents["pages/login_page.py"] == "class LoginPage:\n    pass\n"


def test_healer_writes_known_fixed_files_back_to_original_location(tmp_path: Path):
    output_dir = tmp_path / "generated_tests"
    page_file = output_dir / "pages" / "login_page.py"
    page_file.parent.mkdir(parents=True)
    page_file.write_text("old\n")

    healer = make_healer(output_dir)
    known_files = {"pages/login_page.py": page_file.resolve()}

    written = healer._write_fixed_file("pages/login_page.py", "new\n", known_files)

    assert written == page_file.resolve()
    assert page_file.read_text() == "new\n"
