"""
CLI Entry Point for Selenium AI Agent
======================================
Usage:
    selenium-agent "test login page of amazon.com"
    selenium-agent "test search on flipkart.com" --api-key YOUR_KEY
    selenium-agent "test checkout flow" --provider openai --api-key YOUR_OPENAI_KEY
    selenium-agent "test checkout flow" --output-dir my_tests --no-heal
    selenium-agent --plan-only "test login page"
    selenium-agent --heal-only tests/test_login.py pages/login_page.py
"""

import argparse
import json
import os
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
  # Using Anthropic Claude (default)
  selenium-agent "test login page of amazon.com"
  selenium-agent "test search on flipkart.com" --api-key sk-ant-xxx

  # Using OpenAI
  selenium-agent "test login page" --provider openai --api-key sk-xxx
  selenium-agent "test checkout" --provider openai  # uses OPENAI_API_KEY env var

  # Other options
  selenium-agent "test checkout flow" --output-dir my_project/tests
  selenium-agent "test signup page" --no-heal
  selenium-agent --plan-only "test login page of github.com"
  selenium-agent --heal-only generated_tests/tests/test_login.py

Get your Anthropic API key at : https://console.anthropic.com
Get your OpenAI API key at    : https://platform.openai.com
        """
    )

    parser.add_argument(
        "instruction",
        nargs="?",
        help="What to test. E.g: 'test login page of amazon.com'"
    )
    parser.add_argument(
        "--api-key",
        default=None,
        help="LLM provider API key (or set ANTHROPIC_API_KEY / OPENAI_API_KEY env var)"
    )
    parser.add_argument(
        "--provider",
        default=DEFAULT_PROVIDER,
        choices=["anthropic", "openai"],
        help="LLM provider to use (default: anthropic)"
    )
    parser.add_argument(
        "--model",
        default=None,
        help="Override default model for selected provider"
    )
    parser.add_argument(
        "--output-dir",
        default="generated_tests",
        help="Directory to save generated tests (default: generated_tests)"
    )
    parser.add_argument(
        "--max-retries",
        type=int,
        default=3,
        help="Max heal retry attempts (default: 3)"
    )
    parser.add_argument(
        "--no-heal",
        action="store_true",
        help="Skip auto-healing step"
    )
    parser.add_argument(
        "--plan-only",
        action="store_true",
        help="Only generate test plan (no code)"
    )
    parser.add_argument(
        "--heal-only",
        nargs="+",
        metavar="FILE",
        help="Only heal existing test files"
    )
    parser.add_argument(
        "--version",
        action="version",
        version="selenium-agent 0.1.0"
    )

    args = parser.parse_args()

    try:
        agent = Orchestrator(
            api_key=args.api_key,
            provider=args.provider,
            model=args.model,
            output_dir=args.output_dir,
            max_heal_retries=args.max_retries,
            auto_heal=not args.no_heal,
        )
    except ValueError as exc:
        print(f"\n❌ {exc}\n")
        sys.exit(1)

    try:
        # Mode: heal only
        if args.heal_only:
            logger.info(f"🩺 Healing files: {args.heal_only}")
            result = agent.heal_only(args.heal_only)
            print(f"\n🩺 Heal result: {result['status']} (attempts: {result['attempts']})")
            sys.exit(0 if result["status"] == "passed" else 1)

        # Need instruction for other modes
        if not args.instruction:
            parser.print_help()
            sys.exit(1)

        # Mode: plan only
        if args.plan_only:
            plan = agent.plan_only(args.instruction)
            print("\n📋 TEST PLAN:")
            print(json.dumps(plan, indent=2))
            sys.exit(0)

        # Mode: full run
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
        print("\n\n⚠️  Interrupted by user")
        sys.exit(1)
    except Exception as e:
        logger.error(f"Fatal error: {e}")
        print(f"\n❌ Error: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
