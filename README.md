# Selenium Python AI Agent 🤖

> AI-powered multi-agent framework that **plans**, **generates**, and **heals** Selenium Python tests automatically — working the way **Playwright's test agents** do, but for Selenium.
> Supports **Anthropic Claude** and **OpenAI ChatGPT** as LLM backends.

[![PyPI version](https://badge.fury.io/py/selenium-python-ai-agent.svg)](https://pypi.org/project/selenium-python-ai-agent/)
[![Python](https://img.shields.io/badge/python-3.9+-blue.svg)](https://python.org)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

---

## 🧠 How It Works — 3 Agents

```
Your Instruction
      │
      ▼
┌──────────────┐      ┌──────────────┐      ┌──────────────┐
│   PLANNER    │─────▶│  GENERATOR   │─────▶│    HEALER    │
│              │      │              │      │              │
│ live DOM scan│      │ POM code from│      │ run → rescan │
│ (+ optional  │      │ plan, self-  │      │ live DOM →   │
│ site explore)│      │ verified     │      │ fix → verify │
│ → specs/*.md │      │ (syntax +    │      │ (final fix   │
│   specs/*.json      │ architecture)│      │ always re-run)│
└──────────────┘      └──────────────┘      └──────────────┘
```

**Every agent uses real DOM locators** — a real browser is opened headlessly before planning and healing, so the LLM never guesses selectors.

**Plans are reviewable artifacts** — like Playwright's planner agent, the Planner saves a human-readable Markdown plan plus a machine-readable JSON plan to `specs/`. Review or edit the plan, then generate from it.

---

## ⚡ Quick Start

### 1. Install

```bash
pip install selenium-python-ai-agent
pip install python-dotenv   # recommended — load keys from .env
```

### 2. Set API Keys

Create a `.env` file in your project root (git-ignored automatically):

```env
OPENAI_API_KEY=sk-...
ANTHROPIC_API_KEY=sk-ant-...
```

### 3. One-Time Config Setup

```bash
selenium-agent config --provider openai --model gpt-4o-mini
selenium-agent config --base-url https://www.saucedemo.com
selenium-agent config --headless          # (--no-headless to turn off)
selenium-agent config --show
```

### 4. Generate & Run Tests

```bash
# Full flow: plan → generate → heal (default)
selenium-agent "test the login page"

# Plan first, review, then generate (Playwright-agents workflow)
selenium-agent --plan-only "test the checkout flow"
#   → specs/test-the-checkout-flow.md   (read/edit this)
#   → specs/test-the-checkout-flow.json
selenium-agent --from-plan specs/test-the-checkout-flow.json
```

---

## 🤝 Claude Code Integration — `init-agents`

The Selenium equivalent of `npx playwright init-agents --loop=claude`:

```bash
selenium-agent init-agents                       # into current project
selenium-agent init-agents --project /path/to/project
```

This installs three Claude Code subagents:

```
.claude/agents/selenium-test-planner.md     ← plans tests, saves specs/
.claude/agents/selenium-test-generator.md   ← generates code from specs/
.claude/agents/selenium-test-healer.md      ← runs, debugs & fixes tests
```

Then, inside Claude Code:

> "use selenium-test-planner to plan tests for https://www.saucedemo.com"
> "use selenium-test-generator to generate the tests from specs/login.json"
> "use selenium-test-healer to fix tests/test_login.py"

---

## 📋 All Commands

### Generate Tests (Main Command)

```bash
selenium-agent "test the login page"                    # uses saved config + URL
selenium-agent "test login page of saucedemo.com"       # URL auto-detected
selenium-agent "test login" --url https://staging.myapp.com   # override once
selenium-agent "test the login page" --no-heal          # generate only
selenium-agent "test the login page" --mode bdd         # Gherkin .feature files
selenium-agent "test the login page" --headless
selenium-agent "test checkout" --explore 3              # scan 3 extra same-origin pages
selenium-agent "test the login page" --output-dir my_tests/
selenium-agent "test the login page" --project /path/to/project   # fit existing project
selenium-agent "test the login page" --max-retries 5
```

### `--plan-only` — Preview & Persist the Test Plan

```bash
selenium-agent --plan-only "test the login page"
```

Saves `specs/<slug>.md` (human-readable) + `specs/<slug>.json` (generator input),
built from a **real DOM scan** — scenarios, locators, wait strategies.

### `--from-plan` — Generate From a Saved/Edited Plan

```bash
selenium-agent --from-plan specs/test-the-login-page.json
selenium-agent --from-plan specs/test-the-login-page.json --no-heal
```

### `--heal-only` — Fix Existing Tests

```bash
selenium-agent --heal-only generated_tests/tests/test_login.py

# Heal one test only (other tests preserved verbatim)
selenium-agent --heal-only generated_tests/tests/test_login.py \
  --test test_login_locked_out_user

# pytest -k syntax works too
selenium-agent --heal-only generated_tests/tests/test_login.py \
  --test "locked_out or invalid_password"
```

**Smart healing includes:**
- Live DOM re-scan of **every URL the tests touch** on each failure
- Selenium-specific error classification (SeleniumErrorMap) before the LLM is asked
- Every fix is **syntax-validated** — a broken fix never overwrites a working file
- The final fix is **always verified** with a test run (never "fixed and hoped")
- Missing locators added to page objects (never to test files); `By` imports stripped from tests
- Targeted mode restores any test functions the LLM accidentally drops

### `--scan` — Inspect an Existing Project

```bash
selenium-agent --scan /path/to/existing/project
```

Detects folder layout, base page class, test framework, driver setup, naming
conventions and import style — so generated code fits **into** the project.

---

## 🏗️ Generated Output Structure

```
specs/
├── test-the-login-page.md    ← reviewable test plan (Planner output)
└── test-the-login-page.json  ← machine-readable plan (Generator input)
generated_tests/
├── pages/
│   └── login_page.py         ← Page Object (locators live here)
├── tests/
│   └── test_login.py         ← pytest test file (no raw locators)
└── conftest.py               ← shared fixtures (driver setup)
```

**Architecture enforced by the agents:**
- Locators are **always** class constants in page objects: `LOGIN_BUTTON = (By.CSS_SELECTOR, '[data-test="login-button"]')`
- Test files reference by name: `page.LOGIN_BUTTON` — no `By`, no raw strings
- All waits via `fluent_wait(locator, condition)` — no `time.sleep()`
- `wait_for_url()` after every navigation, `page.safe_type()` for React/SPA forms

---

## 🏢 Enterprise-Grade Reliability

| Concern | What the framework does |
|---|---|
| LLM flakiness | Automatic retries with exponential backoff on rate limits / 5xx / timeouts |
| Malformed LLM JSON | Robust extraction: fences, prose, trailing commas, truncation repair |
| Broken generated code | Every file `ast`-validated before saving; one LLM repair round on failure |
| Broken "fixes" | Healer rejects syntactically invalid fixes — never overwrites working files |
| Unverified fixes | Final heal attempt always followed by a verification test run |
| Guessed selectors | Planner & Healer scan the **live DOM** (optionally multiple pages) first |
| Hung test runs | pytest executed with a hard timeout |
| Existing projects | ProjectScanner detects your BasePage, layout & conventions; code fits in |
| Reasoning models | OpenAI gpt-5*/o* token budgets handled (reasoning tokens accounted for) |

---

## 🔧 All CLI Flags Reference

| Flag | Description | Default |
|------|-------------|---------|
| `--provider` | `anthropic` or `openai` | from config |
| `--model` | Override model for this run | from config |
| `--api-key` | API key (prefer .env instead) | env var |
| `--url` | Override base URL for this run | from config |
| `--mode` | `pytest` or `bdd` | from config (`pytest`) |
| `--headless` | Headless browser | from config (`false`) |
| `--explore N` | Scan N extra same-origin pages while planning | `0` |
| `--output-dir` | Where to save generated files | `generated_tests` |
| `--project` | Fit into existing project path | — |
| `--max-retries` | Healer retry attempts | `3` |
| `--no-heal` | Skip healing after codegen | `false` |
| `--plan-only` | Save + show plan, no code | `false` |
| `--from-plan FILE` | Generate from saved plan JSON | — |
| `--heal-only FILE` | Heal specific file(s) | — |
| `--test TEST_NAME` | Target specific test (with `--heal-only`) | — |
| `--scan PATH` | Scan existing project structure | — |
| `--version` | Show version | — |

Subcommands: `selenium-agent config …`, `selenium-agent init-agents …`, `selenium-agent help`

---

## 🤖 Supported Models

| Provider | Recommended Model | Notes |
|----------|-----------------|-------|
| OpenAI | `gpt-4o-mini` | Fast, cheap, good quality |
| OpenAI | `gpt-4o` | Best quality |
| OpenAI | `gpt-5-mini` | Reasoning model — handled automatically |
| Anthropic | `claude-sonnet-4-20250514` | Best quality |
| Anthropic | `claude-haiku-4-5-20251001` | Fast, cheap |

---

## 📦 Requirements

- Python 3.9+
- Chrome browser installed
- API key from Anthropic **or** OpenAI

---

## 🤝 Contributing

PRs welcome! See [CONTRIBUTING.md](CONTRIBUTING.md)

---

## 📄 License

MIT — free to use, modify, distribute.

---

*Built with ❤️ by [Ankit Tripathi](https://github.com/AnkitDeepBlue)*
