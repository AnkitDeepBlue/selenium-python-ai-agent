"""ORCHESTRATOR — Coordinates Planner → Coder (Generator) → Healer

Mirrors the Playwright agents workflow:
  plan     → specs/<slug>.md + specs/<slug>.json  (reviewable artifacts)
  generate → Page Object Model code from a plan (fresh or saved)
  heal     → run, live-DOM re-scan, fix, verify — until green
"""

from pathlib import Path

from selenium_agent.agents.planner import PlannerAgent
from selenium_agent.agents.coder import CoderAgent
from selenium_agent.agents.healer import HealerAgent
from selenium_agent.utils.logger import setup_logger
from selenium_agent.utils.url_extractor import extract_url
from selenium_agent.utils.spec_writer import save_spec, load_plan
from selenium_agent.utils.llm import (
    DEFAULT_PROVIDER, format_missing_api_key_error,
    get_default_model, normalize_provider, resolve_api_key,
)

logger = setup_logger("Orchestrator")


class Orchestrator:
    def __init__(
        self,
        api_key: str = None,
        output_dir: str = "generated_tests",
        max_heal_retries: int = 5,
        auto_heal: bool = True,
        provider: str = DEFAULT_PROVIDER,
        model: str | None = None,
        mode: str = "pytest",
        project_root: str | None = None,
        headless: bool = False,
        explore_pages: int = 0,
        save_report: bool = False,
    ):
        self.provider = normalize_provider(provider)
        self.model    = model or get_default_model(self.provider)
        self.api_key  = resolve_api_key(provider=self.provider, api_key=api_key)
        if not self.api_key:
            raise ValueError(format_missing_api_key_error(self.provider))

        self.output_dir    = output_dir
        self.auto_heal     = auto_heal
        self.mode          = mode if mode in ("pytest", "bdd") else "pytest"
        self.headless      = headless
        self.project_root  = project_root
        self.explore_pages = explore_pages

        self.project_profile = None
        if project_root:
            self._scan_project(project_root)

        self.planner = PlannerAgent(api_key=self.api_key, provider=self.provider, model=self.model)
        self.coder   = CoderAgent(api_key=self.api_key, output_dir=self.output_dir,
                                  provider=self.provider, model=self.model)
        self.healer  = HealerAgent(api_key=self.api_key, output_dir=self.output_dir,
                                   max_retries=max_heal_retries,
                                   provider=self.provider, model=self.model,
                                   save_report=save_report)

    def _scan_project(self, project_root: str):
        from selenium_agent.scanner.project_scanner import ProjectScanner
        logger.info(f"🔍 Scanning: {project_root}")
        try:
            self.project_profile = ProjectScanner(project_root).scan()
            logger.info(
                f"✅ Detected: {self.project_profile.test_framework} | "
                f"pages={self.project_profile.pages_dir} | "
                f"base={self.project_profile.base_page_class}"
            )
            if self.output_dir == "generated_tests":
                self.output_dir = project_root
                self.coder.output_dir  = project_root
                self.healer.output_dir = str(Path(project_root).resolve())
        except Exception as e:
            logger.warning(f"⚠️  Scan failed: {e} — using defaults")

    # ── Spec persistence (Playwright-planner style) ──────────────────────

    def _specs_dir(self) -> Path:
        root = Path(self.project_root) if self.project_root else Path.cwd()
        return root / "specs"

    def _save_spec(self, plan: dict, instruction: str) -> dict:
        try:
            paths = save_spec(plan, instruction, specs_dir=self._specs_dir())
            logger.info(f"📄 Plan saved: {paths['markdown']} (+ .json twin)")
            return paths
        except Exception as e:
            logger.warning(f"⚠️  Could not save spec files: {e}")
            return {}

    # ── Pipelines ────────────────────────────────────────────────────────

    def run(self, instruction: str, override_url: str | None = None) -> dict:
        logger.info("=" * 60)
        logger.info(f"🚀 Selenium AI Agent | mode={self.mode.upper()} | headless={self.headless}")
        logger.info(f"📌 Task: {instruction}")
        logger.info("=" * 60)

        # URL priority: --url flag > extracted from instruction > LLM decides
        target_url = override_url or extract_url(instruction)
        if override_url:
            logger.info(f"🌐 URL override (--url flag): {target_url}")
        elif target_url:
            logger.info(f"🌐 Target URL detected: {target_url}")
        else:
            logger.warning("⚠️  No URL detected — LLM will infer from instruction")

        logger.info("\n🧠 STEP 1: PLANNER")
        plan = self._plan(instruction, target_url)
        spec_paths = self._save_spec(plan, instruction)

        saved_files, heal_result = self._generate_and_heal(plan)

        logger.info("\n" + "=" * 60)
        logger.info("🎉 DONE!")
        logger.info(f"📁 Files in: {self.output_dir}/")
        logger.info("=" * 60)

        return {
            "plan": plan,
            "spec": spec_paths,
            "files": saved_files,
            "heal_result": heal_result,
        }

    def run_from_plan(self, plan_file: str) -> dict:
        """Generate (and heal) directly from a saved specs/<slug>.json plan."""
        plan = load_plan(plan_file)
        if self.headless:
            plan["headless"] = True
        logger.info(f"📋 Loaded plan: {plan_file} "
                    f"({len(plan.get('test_scenarios') or plan.get('scenarios', []))} scenario(s))")
        saved_files, heal_result = self._generate_and_heal(plan)
        return {"plan": plan, "files": saved_files, "heal_result": heal_result}

    def plan_only(self, instruction: str, override_url: str | None = None) -> dict:
        target_url = override_url or extract_url(instruction)
        plan = self._plan(instruction, target_url)
        spec_paths = self._save_spec(plan, instruction)
        plan["_spec_files"] = spec_paths
        return plan

    def code_only(self, plan: dict) -> list:
        return self.coder.code(plan, project_profile=self.project_profile)

    def heal_only(self, file_paths: list, test_filter: str | None = None) -> dict:
        return self.healer.heal(file_paths, test_filter=test_filter,
                                project_profile=self.project_profile)

    def scan_only(self, project_root: str) -> str:
        from selenium_agent.scanner.project_scanner import ProjectScanner
        return ProjectScanner(project_root).scan().to_llm_context()

    # ── Internals ────────────────────────────────────────────────────────

    def _plan(self, instruction: str, target_url: str | None) -> dict:
        plan = self.planner.plan(
            instruction, mode=self.mode,
            project_profile=self.project_profile,
            headless=self.headless,
            target_url=target_url,
            explore_pages=self.explore_pages,
        )
        # Force URL and headless into plan — LLM cannot override these
        if target_url:
            plan["url"] = target_url
        plan["headless"] = self.headless
        return plan

    def _generate_and_heal(self, plan: dict) -> tuple[list, dict | None]:
        logger.info("\n💻 STEP 2: GENERATOR")
        try:
            saved_files = self.coder.code(plan, project_profile=self.project_profile)
        except ValueError as e:
            logger.error(f"💥 Generator failed: {e}")
            logger.error("💡 Tip: Complex multi-page flows may exceed token limits.")
            logger.error("   Try: simplifying the instruction or splitting the plan.")
            raise

        heal_result = None
        if self.auto_heal:
            logger.info("\n🩺 STEP 3: HEALER")
            heal_result = self.healer.heal(saved_files,
                                           project_profile=self.project_profile)
        else:
            logger.info("\n⏭️  Auto-heal skipped")
        return saved_files, heal_result
