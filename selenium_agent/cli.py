"""
CLI Entry Point for Selenium AI Agent
"""

import argparse
import json
import sys

from selenium_agent.core.orchestrator import Orchestrator
from selenium_agent.utils.llm import DEFAULT_PROVIDER
from selenium_agent.utils.logger import setup_logger

logger = setup_logger("CLI")


def main():
    parser = argparse.ArgumentParser(
        prog="selenium-agent",
        description="🤖 Selenium Python AI Agent — Plan, Code & Heal tests automatically",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # pytest mode (default)
  selenium-agent "test login page of saucedemo.com"

  # pytest-bdd / Gherkin mode
  selenium-agent "test login page of saucedemo.com" --mode bdd

  # OpenAI provider
  selenium-agent "test login page" --provider openai --api-key sk-xxx

  # Plan only (no code generated)
  selenium-agent --plan-only "test login page"

  # Skip auto-healing
  selenium-agent "test checkout" --no-heal

  # Heal existing broken tests
  selenium-agent --heal-only generated_tests/tests/test_login.py

Get Anthropic key : https://console.anthropic.com
Get OpenAI key    : https://platform.openai.com
        """
    )

    parser.add_argument("instruction", nargs="?",
                        help="What to test. E.g: 'test login page of saucedemo.com'")
    parser.add_argument("--api-key", default=None,
                        help="LLM provider API key (or set ANTHROPIC_API_KEY / OPENAI_API_KEY)")
    parser.add_argument("--provider", default=DEFAULT_PROVIDER,
                        choices=["anthropic", "openai"],
                        help="LLM provider (default: anthropic)")
    parser.add_argument("--model", default=None,
                        help="Override default model for selected provider")
    parser.add_argument("--mode", default="pytest",
                        choices=["pytest", "bdd"],
                        help="Test framework: pytest (default) or bdd (pytest-bdd/Gherkin)")
    parser.add_argument("--output-dir", default="generated_tests",
                        help="Directory to save generated tests (default: generated_tests)")
    parser.add_argument("--max-retries", type=int, default=3,
                        help="Max heal retry attempts (default: 3)")
    parser.add_argument("--no-heal", action="store_true",
                        help="Skip auto-healing step")
    parser.add_argument("--plan-only", action="store_true",
                        help="Only generate test plan (no code)")
    parser.add_argument("--heal-only", nargs="+", metavar="FILE",
                        help="Only heal existing test files")
    parser.add_argument("--version", action="version", version="selenium-agent 0.1.0")

    args = parser.parse_args()

    try:
        agent = Orchestrator(
            api_key=args.api_key,
            provider=args.provider,
            model=args.model,
            output_dir=args.output_dir,
            max_heal_retries=args.max_retries,
            auto_heal=not args.no_heal,
            mode=args.mode,
        )
    except ValueError as exc:
        print(f"\n❌ {exc}\n")
        sys.exit(1)

    try:
        if args.heal_only:
            result = agent.heal_only(args.heal_only)
            print(f"\n🩺 {result['status']} (attempts: {result['attempts']})")
            sys.exit(0 if result["status"] == "passed" else 1)

        if not args.instruction:
            parser.print_help()
            sys.exit(1)

        if args.plan_only:
            plan = agent.plan_only(args.instruction)
            print("\n📋 TEST PLAN:")
            print(json.dumps(plan, indent=2))
            sys.exit(0)

        result = agent.run(args.instruction)

        print(f"\n✅ Generated {len(result['files'])} files:")
        for f in result["files"]:
            print(f"   📄 {f}")

        if result["heal_result"]:
            status = result["heal_result"]["status"]
            attempts = result["heal_result"]["attempts"]
            emoji = "✅" if status == "passed" else "❌"
            print(f"\n{emoji} Tests {status} after {attempts} attempt(s)")

        sys.exit(0)

    except KeyboardInterrupt:
        print("\n\n⚠️  Interrupted")
        sys.exit(1)
    except Exception as e:
        logger.error(f"Fatal: {e}")
        print(f"\n❌ Error: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
