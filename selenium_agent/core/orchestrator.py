"""
ORCHESTRATOR — Coordinates Planner → Coder → Healer
"""

from selenium_agent.agents.planner import PlannerAgent
from selenium_agent.agents.coder import CoderAgent
from selenium_agent.agents.healer import HealerAgent
from selenium_agent.utils.logger import setup_logger
from selenium_agent.utils.llm import (
    DEFAULT_PROVIDER,
    format_missing_api_key_error,
    get_default_model,
    normalize_provider,
    resolve_api_key,
)

logger = setup_logger("Orchestrator")


class Orchestrator:
    """
    Main entry point for the Selenium AI Agent.

    Args:
        api_key: Provider API key (ANTHROPIC_API_KEY or OPENAI_API_KEY env var)
        output_dir: Where to save generated tests (default: generated_tests)
        max_heal_retries: How many times Healer retries (default: 3)
        auto_heal: Run and heal tests after generation (default: True)
        provider: 'anthropic' or 'openai' (default: anthropic)
        model: Override default model
        mode: 'pytest' or 'bdd' (default: pytest)
    """

    def __init__(
        self,
        api_key: str = None,
        output_dir: str = "generated_tests",
        max_heal_retries: int = 3,
        auto_heal: bool = True,
        provider: str = DEFAULT_PROVIDER,
        model: str | None = None,
        mode: str = "pytest",
    ):
        self.provider = normalize_provider(provider)
        self.model = model or get_default_model(self.provider)
        self.api_key = resolve_api_key(provider=self.provider, api_key=api_key)
        if not self.api_key:
            raise ValueError(format_missing_api_key_error(self.provider))

        self.output_dir = output_dir
        self.auto_heal = auto_heal
        self.mode = mode if mode in ("pytest", "bdd") else "pytest"

        self.planner = PlannerAgent(
            api_key=self.api_key, provider=self.provider, model=self.model,
        )
        self.coder = CoderAgent(
            api_key=self.api_key, output_dir=output_dir,
            provider=self.provider, model=self.model,
        )
        self.healer = HealerAgent(
            api_key=self.api_key, output_dir=output_dir,
            max_retries=max_heal_retries,
            provider=self.provider, model=self.model,
        )

    def run(self, instruction: str) -> dict:
        """Full pipeline: Plan → Code → Heal"""
        logger.info("=" * 60)
        logger.info(f"🚀 Selenium AI Agent — mode: {self.mode.upper()}")
        logger.info(f"📌 Task: {instruction}")
        logger.info("=" * 60)

        logger.info("\n🧠 STEP 1: PLANNER")
        plan = self.planner.plan(instruction, mode=self.mode)

        logger.info("\n💻 STEP 2: CODER")
        saved_files = self.coder.code(plan)

        heal_result = None
        if self.auto_heal:
            logger.info("\n🩺 STEP 3: HEALER")
            heal_result = self.healer.heal(saved_files)
        else:
            logger.info("\n⏭️  Auto-heal skipped (--no-heal)")

        logger.info("\n" + "=" * 60)
        logger.info("🎉 DONE!")
        logger.info(f"📁 Files in: {self.output_dir}/")
        logger.info("=" * 60)

        return {"plan": plan, "files": saved_files, "heal_result": heal_result}

    def plan_only(self, instruction: str) -> dict:
        return self.planner.plan(instruction, mode=self.mode)

    def code_only(self, plan: dict) -> list:
        return self.coder.code(plan)

    def heal_only(self, file_paths: list) -> dict:
        return self.healer.heal(file_paths)
