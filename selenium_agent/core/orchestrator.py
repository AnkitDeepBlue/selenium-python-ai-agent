"""
ORCHESTRATOR
============
The main brain that coordinates Planner → Coder → Healer agents.
This is what users interact with via the Python Library.

Usage:
    from selenium_agent import SeleniumAgent

    agent = SeleniumAgent(api_key="your-key")
    result = agent.run("test login page of amazon.com")
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
        api_key (str): Provider API key. Supports Anthropic and OpenAI.
        output_dir (str): Directory where generated tests will be saved.
                          Default: "generated_tests"
        max_heal_retries (int): How many times Healer will retry fixing failed tests.
                                Default: 3
        auto_heal (bool): Whether to automatically run and heal tests after generation.
                          Default: True
        provider (str): LLM provider to use. Supported: "anthropic", "openai".
                        Default: "anthropic"
        model (str | None): Override the default model for the selected provider.
    """

    def __init__(
        self,
        api_key: str = None,
        output_dir: str = "generated_tests",
        max_heal_retries: int = 3,
        auto_heal: bool = True,
        provider: str = DEFAULT_PROVIDER,
        model: str | None = None,
    ):
        self.provider = normalize_provider(provider)
        self.model = model or get_default_model(self.provider)
        self.api_key = resolve_api_key(provider=self.provider, api_key=api_key)
        if not self.api_key:
            raise ValueError(format_missing_api_key_error(self.provider))

        self.output_dir = output_dir
        self.auto_heal = auto_heal

        self.planner = PlannerAgent(api_key=self.api_key, provider=self.provider, model=self.model)
        self.coder = CoderAgent(
            api_key=self.api_key,
            output_dir=output_dir,
            provider=self.provider,
            model=self.model,
        )
        self.healer = HealerAgent(
            api_key=self.api_key,
            output_dir=output_dir,
            max_retries=max_heal_retries,
            provider=self.provider,
            model=self.model,
        )

    def run(self, instruction: str) -> dict:
        """
        Full pipeline: Plan → Code → Heal

        Args:
            instruction: Natural language description of what to test.
                        Example: "test login page of flipkart.com"

        Returns:
            dict with keys: plan, files, heal_result
        """
        logger.info("=" * 60)
        logger.info(f"🚀 Starting Selenium AI Agent")
        logger.info(f"📌 Task: {instruction}")
        logger.info("=" * 60)

        # Step 1: Plan
        logger.info("\n🧠 STEP 1: PLANNER AGENT")
        plan = self.planner.plan(instruction)

        # Step 2: Code
        logger.info("\n💻 STEP 2: CODER AGENT")
        saved_files = self.coder.code(plan)

        # Step 3: Heal (optional)
        heal_result = None
        if self.auto_heal:
            logger.info("\n🩺 STEP 3: HEALER AGENT")
            heal_result = self.healer.heal(saved_files)
        else:
            logger.info("\n⏭️  Auto-heal skipped (auto_heal=False)")

        logger.info("\n" + "=" * 60)
        logger.info("🎉 DONE!")
        logger.info(f"📁 Files saved in: {self.output_dir}/")
        logger.info("=" * 60)

        return {
            "plan": plan,
            "files": saved_files,
            "heal_result": heal_result
        }

    def plan_only(self, instruction: str) -> dict:
        """Only run the Planner agent — get test plan without generating code."""
        logger.info("🧠 Running Planner only...")
        return self.planner.plan(instruction)

    def code_only(self, plan: dict) -> list:
        """Only run the Coder agent — generate code from an existing plan."""
        logger.info("💻 Running Coder only...")
        return self.coder.code(plan)

    def heal_only(self, file_paths: list) -> dict:
        """Only run the Healer agent — fix existing failing tests."""
        logger.info("🩺 Running Healer only...")
        return self.healer.heal(file_paths)
