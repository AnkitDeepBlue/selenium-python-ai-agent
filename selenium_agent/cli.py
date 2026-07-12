"""CLI Entry Point for Selenium AI Agent"""

import argparse
import json
import sys

# Auto-load .env file if present — so you never need to pass --api-key manually
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

from selenium_agent.core.orchestrator import Orchestrator
from selenium_agent.utils.logger import setup_logger
from selenium_agent.utils import config_manager

logger = setup_logger("CLI")


def _handle_config(argv):
    """Handle `selenium-agent config [flags]` before main argparse."""
    p = argparse.ArgumentParser(prog="selenium-agent config")
    p.add_argument("--provider", choices=["anthropic", "openai"])
    p.add_argument("--model",    help="e.g. gpt-4o-mini, claude-sonnet-4-20250514")
    p.add_argument("--base-url", dest="base_url", help="Default base URL for all tests")
    p.add_argument("--headless",    dest="headless", action="store_true",  default=None)
    p.add_argument("--no-headless", dest="headless", action="store_false", default=None)
    p.add_argument("--mode",     choices=["pytest", "bdd"])
    p.add_argument("--project",  help="Existing project to fit tests into "
                                      "(use 'none' to clear)")
    p.add_argument("--show",     action="store_true", help="Print current config")
    args = p.parse_args(argv)

    if args.show:
        print("\n📋 Current config:")
        print(json.dumps(config_manager.load(), indent=2))
        return

    if args.project and args.project.lower() in ("none", "clear", "off"):
        args.project = ""  # empty string clears it (consumers treat "" as unset)

    updates = {k: v for k, v in vars(args).items() if v is not None and k != "show"}
    if not updates:
        p.print_help()
        return

    path = config_manager.save(updates)
    print(f"\n✅ Config saved to {path}")
    print(json.dumps(config_manager.load(), indent=2))


def _handle_init_agents(argv):
    """Handle `selenium-agent init-agents [--project PATH]`."""
    p = argparse.ArgumentParser(prog="selenium-agent init-agents")
    p.add_argument("--project", default=".", metavar="PATH",
                   help="Project to install the agent definitions into (default: .)")
    args = p.parse_args(argv)

    from selenium_agent.agents.definitions import write_agent_definitions
    written = write_agent_definitions(args.project)
    print("\n✅ Claude Code agent definitions installed:")
    for path in written:
        print(f"   📄 {path}")
    print("\nOpen Claude Code in this project and ask e.g.:")
    print('   "use selenium-test-planner to plan tests for https://www.saucedemo.com"')


def _handle_help():
    """Print a friendly cheatsheet of all commands."""
    print("""
┌────────────────────────────────────────────────────────────────────────────────┐
│            🤖  Selenium Python AI Agent — Command Reference              │
└────────────────────────────────────────────────────────────────────────────────┘

🔧  ONE-TIME SETUP
  selenium-agent config --provider openai --model gpt-4o-mini
  selenium-agent config --base-url https://www.yoursite.com
  selenium-agent config --headless          (--no-headless to turn off)
  selenium-agent config --show                      ← verify saved config

🚀  GENERATE TESTS  (plan + code + heal)
  selenium-agent "test the login page"               ← uses saved config & URL
  selenium-agent "test login of saucedemo.com"       ← URL auto-detected
  selenium-agent "test login" --url https://myapp.com  ← override URL once
  selenium-agent "test login page" --no-heal         ← generate only, skip heal
  selenium-agent "test login page" --mode bdd        ← BDD/Gherkin output
  selenium-agent "test login page" --headless        ← headless browser
  selenium-agent "test login page" --explore 3       ← scan 3 extra pages for locators
  selenium-agent "test login page" --output-dir my_tests/
  selenium-agent "test login page" --max-retries 5
  selenium-agent "test login page" --project /path/to/existing/project

💻  PLAN ONLY  (saved to specs/<slug>.md + .json for review)
  selenium-agent --plan-only "test the login page"

📋  GENERATE FROM A SAVED PLAN  (review/edit the plan first)
  selenium-agent --from-plan specs/test-the-login-page.json

🩺  HEAL EXISTING TESTS
  selenium-agent --heal-only generated_tests/tests/test_login.py
  selenium-agent --heal-only generated_tests/tests/test_login.py \\
    --test test_login_locked_out_user                ← specific test only
  selenium-agent --heal-only generated_tests/tests/test_login.py \\
    --test "locked_out or invalid_password"          ← multiple (-k syntax)

🔍  SCAN PROJECT
  selenium-agent --scan /path/to/project

🤝  CLAUDE CODE INTEGRATION  (like `playwright init-agents`)
  selenium-agent init-agents                 ← installs .claude/agents/*.md
  selenium-agent init-agents --project /path/to/project

⚙️   CONFIG OPTIONS
  --provider    anthropic | openai          (default: from config)
  --model       e.g. gpt-4o-mini            (default: from config)
  --api-key     your key                    (prefer .env instead)
  --url         override base URL once      (auto-saved to config)
  --mode        pytest | bdd                (default: pytest)
  --headless    headless browser
  --explore N   scan N extra same-origin pages while planning
  --output-dir  where to save files         (default: generated_tests)
  --project     existing project path      (auto-saved to config)
  --max-retries healer retries              (default: 5)
  --no-heal     skip healing
  --plan-only   preview plan only (saved to specs/)
  --from-plan   generate from saved plan JSON
  --test        target specific test (use with --heal-only)
  --version     show version

📂  GENERATED STRUCTURE
  specs/<slug>.md            ← reviewable test plan (planner output)
  specs/<slug>.json          ← machine-readable plan (generator input)
  generated_tests/
  ├── pages/login_page.py    ← Page Object (locators live here)
  ├── tests/test_login.py    ← pytest tests (no raw locators)
  └── conftest.py            ← driver fixture
""")


def main():
    # ── subcommands handled before argparse to avoid positional conflicts ──
    if len(sys.argv) > 1 and sys.argv[1] == "config":
        _handle_config(sys.argv[2:])
        return

    if len(sys.argv) > 1 and sys.argv[1] == "init-agents":
        _handle_init_agents(sys.argv[2:])
        return

    if len(sys.argv) > 1 and sys.argv[1] == "help":
        _handle_help()
        return

    parser = argparse.ArgumentParser(
        prog="selenium-agent",
        description="🤖 Selenium Python AI Agent — Plan, Code & Heal tests automatically",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
One-time setup:
  selenium-agent config --provider openai --model gpt-4o-mini
  selenium-agent config --base-url https://saucedemo.com
  selenium-agent config --show

After setup, just run:
  selenium-agent "test the login page"
  selenium-agent "test the checkout flow"   ← base_url reused automatically

Other examples:
  selenium-agent "test login" --url https://myapp.com  ← override URL once
  selenium-agent "test login page" --mode bdd
  selenium-agent --plan-only "test login page"
  selenium-agent --from-plan specs/test-login-page.json
  selenium-agent --heal-only generated_tests/tests/test_login.py
  selenium-agent init-agents               ← Claude Code agents (planner/generator/healer)
        """
    )

    parser.add_argument("instruction",    nargs="?",
                        help="What to test. E.g: 'test the login page'")
    parser.add_argument("--api-key",      default=None,
                        help="LLM API key (or set in .env)")
    parser.add_argument("--provider",     default=None, choices=["anthropic", "openai"],
                        help="LLM provider (default from config)")
    parser.add_argument("--model",        default=None, help="Override model")
    parser.add_argument("--mode",         default=None, choices=["pytest", "bdd"])
    parser.add_argument("--headless",     action="store_true", default=False)
    parser.add_argument("--url",          default=None,
                        help="Override base URL for this run (also saves to config)")
    parser.add_argument("--project",      default=None, metavar="PATH")
    parser.add_argument("--output-dir",   default="generated_tests")
    parser.add_argument("--max-retries",  type=int, default=None)
    parser.add_argument("--explore",      type=int, default=0, metavar="N",
                        help="Scan up to N extra same-origin pages while planning")
    parser.add_argument("--no-heal",      action="store_true")
    parser.add_argument("--plan-only",    action="store_true")
    parser.add_argument("--from-plan",    default=None, metavar="FILE",
                        help="Generate code from a saved specs/<slug>.json plan")
    parser.add_argument("--scan",         default=None, metavar="PATH")
    parser.add_argument("--heal-only",    nargs="+", metavar="FILE")
    parser.add_argument("--test",          default=None, metavar="TEST_NAME",
                        help="Specific test function to run/heal. "
                             "e.g. --test test_login_locked_out_user")
    parser.add_argument("--version",      action="version", version="selenium-agent 0.2.4")

    args = parser.parse_args()

    # ── Scan only ────────────────────────────────────────────────────
    if args.scan:
        from selenium_agent.scanner.project_scanner import ProjectScanner
        print(f"\n🔍 Scanning: {args.scan}\n")
        try:
            profile = ProjectScanner(args.scan).scan()
            print(profile.to_llm_context())
        except Exception as e:
            print(f"❌ Scan failed: {e}")
            sys.exit(1)
        # Remember the project — future runs fit into it automatically,
        # no need to repeat --project every time.
        config_manager.save({"project": args.scan})
        print(f"\n💾 Project saved to config — future runs will fit into it.")
        print(f"   (change: selenium-agent config --project <path> | clear: --project none)")
        sys.exit(0)

    # ── Merge config + CLI args ───────────────────────────────────────
    cfg = config_manager.get_effective({
        "provider": args.provider,
        "model":    args.model,
        "headless": args.headless,
        "mode":     args.mode,
    })

    # `--model gpt-5` without `--provider` must not hit the default
    # (Anthropic) API — the model name itself tells us the provider.
    # An explicit --provider flag always wins.
    if args.provider is None and cfg.get("model"):
        from selenium_agent.utils.llm import infer_provider_for_model
        inferred = infer_provider_for_model(cfg["model"])
        if inferred and inferred != cfg.get("provider"):
            logger.info(f"🧭 Model '{cfg['model']}' implies provider '{inferred}'")
            cfg["provider"] = inferred

    # URL priority: --url flag > extracted from instruction > saved base_url
    from selenium_agent.utils.url_extractor import extract_url
    override_url = args.url
    if not override_url and args.instruction:
        override_url = extract_url(args.instruction)
    if not override_url:
        override_url = cfg.get("base_url")
        if override_url:
            logger.info(f"🌐 Using saved base_url: {override_url}")

    # If new URL given via --url, persist it for future runs
    if args.url and args.url != cfg.get("base_url"):
        config_manager.save({"base_url": args.url})
        logger.info(f"💾 base_url saved: {args.url}")

    # Project priority: --project flag > saved config. Persist like --url.
    project_root = args.project or (cfg.get("project") or None)
    if args.project and args.project != cfg.get("project"):
        config_manager.save({"project": args.project})
        logger.info(f"💾 project saved: {args.project}")
    elif not args.project and project_root:
        logger.info(f"🏗️  Using saved project: {project_root}")

    # ── Build orchestrator ────────────────────────────────────────────
    try:
        agent = Orchestrator(
            api_key=args.api_key,
            provider=cfg["provider"],
            model=cfg.get("model"),
            output_dir=args.output_dir,
            max_heal_retries=args.max_retries or 5,
            auto_heal=not args.no_heal,
            mode=cfg["mode"],
            project_root=project_root,
            headless=cfg["headless"],
            explore_pages=args.explore,
        )
    except ValueError as exc:
        print(f"\n❌ {exc}\n")
        sys.exit(1)

    try:
        if args.heal_only:
            result = agent.heal_only(args.heal_only, test_filter=args.test)
            emoji = "✅" if result["status"] == "passed" else "❌"
            print(f"\n{emoji} {result['status']} (attempts: {result['attempts']})")
            sys.exit(0 if result["status"] == "passed" else 1)

        if args.from_plan:
            result = agent.run_from_plan(args.from_plan)
            _print_run_result(result)
            sys.exit(0)

        if not args.instruction:
            parser.print_help()
            sys.exit(1)

        if args.plan_only:
            plan = agent.plan_only(args.instruction, override_url=override_url)
            spec_files = plan.pop("_spec_files", {})
            print("\n📋 TEST PLAN:")
            print(json.dumps(plan, indent=2))
            if spec_files:
                print(f"\n📄 Saved: {spec_files.get('markdown')}")
                print(f"📄 Saved: {spec_files.get('json')}")
                print(f"\nReview/edit the plan, then generate with:")
                print(f"  selenium-agent --from-plan {spec_files.get('json')}")
            sys.exit(0)

        result = agent.run(args.instruction, override_url=override_url)
        _print_run_result(result)
        sys.exit(0)

    except KeyboardInterrupt:
        print("\n\n⚠️  Interrupted")
        sys.exit(1)
    except Exception as e:
        logger.error(f"Fatal: {e}")
        print(f"\n❌ Error: {e}")
        sys.exit(1)


def _print_run_result(result: dict):
    print(f"\n✅ Generated {len(result['files'])} files:")
    for f in result["files"]:
        print(f"   📄 {f}")

    spec = result.get("spec") or {}
    if spec.get("markdown"):
        print(f"\n📋 Test plan: {spec['markdown']}")

    if result.get("heal_result"):
        status   = result["heal_result"]["status"]
        attempts = result["heal_result"]["attempts"]
        emoji    = "✅" if status == "passed" else "❌"
        print(f"\n{emoji} Tests {status} after {attempts} attempt(s)")


if __name__ == "__main__":
    main()
