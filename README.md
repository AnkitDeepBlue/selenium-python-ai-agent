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

Works with **any OpenAI or Anthropic model** — pick the one that fits your budget and complexity:

```bash
# any of these (or any other model your API key can access):
selenium-agent config --provider openai --model gpt-4o-mini    # fast & cheap
selenium-agent config --provider openai --model gpt-4o         # strong all-rounder
selenium-agent config --provider openai --model gpt-5          # most intelligent (reasoning)
selenium-agent config --provider anthropic --model claude-sonnet-5   # strong all-rounder
selenium-agent config --provider anthropic --model claude-fable-5    # most intelligent

selenium-agent config --base-url https://www.saucedemo.com     # default URL for all runs
selenium-agent config --headless          # (--no-headless to turn off)
selenium-agent config --show              # verify saved config
```

> 💡 For simple flows `gpt-4o-mini` / `claude-haiku-4-5` are fine; for **multi-page/complex flows** use `gpt-4o`, `gpt-5`, `claude-sonnet-5` or `claude-fable-5` — noticeably better plans and one-shot code.

### 4. Generate & Run Tests

Describe **any workflow on any web app** in plain English — the examples below are just examples.

**Two ways to give the target URL** — a one-off flag, or save it once in config:

```bash
# Option A: pass the URL for this run (it is also saved to config for next time)
selenium-agent "add an item to cart and checkout as guest" --url https://your-app.com

# Option B: save it once, then never pass it again
selenium-agent config --base-url https://your-app.com
selenium-agent "test the login page"                    # uses saved base_url
```

```bash
# Full flow: plan → generate → heal (default)
selenium-agent "test the login page"

# Plan first, review, then generate (Playwright-agents workflow)
selenium-agent --plan-only "test the checkout flow"
#   → specs/test-the-checkout-flow.md   (read/edit this)
#   → specs/test-the-checkout-flow.json
selenium-agent --from-plan specs/test-the-checkout-flow.json

# Something broke later (UI changed, locator died)? Heal it:
selenium-agent --heal-only generated_tests/tests/test_checkout.py
```

---

## 🏗️ Works Inside YOUR Existing Framework

Most teams don't start from scratch — they already have a Selenium project. Point the agent at it with `--project` and it **adapts to your structure instead of imposing its own**:

```bash
# First, see what the scanner detects about your project (read-only).
# The path is SAVED to config — you never need to repeat it.
selenium-agent --scan /path/to/your/project

# From now on every run fits into it automatically:
selenium-agent "test the invoice creation flow"
selenium-agent "test the user permissions page"

# Manage the saved project:
selenium-agent config --project /other/project   # switch
selenium-agent config --project none             # clear
```

The built-in **ProjectScanner** detects and follows:

| What it detects | Effect on generated code |
|---|---|
| Your folder layout (`pages/`, `page_objects/`, `tests/`, `e2e/`, …) | Files are written into **your** folders |
| Your base page class (`BasePage`, `PageBase`, `AbstractPage`, …) | Page objects **extend your class**, with your import path |
| Your test framework (pytest / pytest-bdd / unittest) | Matching test style |
| Your naming conventions (`test_login.py` vs `LoginTest.py`, `login_page.py` vs `LoginPage.py`) | Same naming |
| Your `conftest.py` and driver fixture | Reused — not overwritten |
| Your import style (absolute/relative) and sample code | Generated code follows your style |

`--heal-only` also works directly on your existing test files — the healer auto-discovers the page objects your tests import.

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

The instruction is **free-form natural language** — it works for **any application and any workflow**, not just login pages. The planner opens *your* URL in a real browser and builds the plan from your app's actual DOM.

```bash
selenium-agent "<describe any workflow to test>" --url <your-app-url>
```

Example instructions (any app, any flow):

```bash
selenium-agent "test the login page"                                  # uses saved config + URL
selenium-agent "search for 'laptop' and verify results show prices" --url https://demo.opencart.com
selenium-agent "register a new account and verify the welcome banner" --url https://myapp.internal
selenium-agent "fill the contact form and verify the thank-you message" --url https://mycompany.com/contact
selenium-agent "login as admin, create an invoice and verify it appears in the list" --url https://erp.mycompany.com
selenium-agent "add two items to cart, remove one, then checkout as guest" --url https://shop.example.org
```

Flags (combine with any instruction):

```bash
selenium-agent "..." --url https://staging.myapp.com   # override saved URL once (also saved)
selenium-agent "..." --no-heal                         # generate only, skip healing
selenium-agent "..." --mode bdd                        # Gherkin .feature files
selenium-agent "..." --headless                        # no visible browser
selenium-agent "..." --explore 3                       # explore up to 3 more pages while planning
selenium-agent "..." --output-dir my_tests/            # custom output folder
selenium-agent "..." --project /path/to/project        # fit into YOUR existing framework
selenium-agent "..." --model gpt-5                     # override model for this run
selenium-agent "..." --max-retries 8                   # more healer attempts (default: 5)
```

### `--plan-only` — Preview & Persist the Test Plan

```bash
selenium-agent --plan-only "test the login page"
selenium-agent --plan-only "end-to-end purchase flow with checkout and logout" --explore 2
```

Saves `specs/<slug>.md` (human-readable) + `specs/<slug>.json` (generator input),
built from a **real DOM scan** — scenarios, locators, wait strategies.

**Smart planning includes:**
- **Live DOM scan first** — selectors come from your actual page, never guessed
- **SPA-aware scanning** — polls until React/Vue/Angular apps finish rendering (boot animations included)
- **Relevance-ranked site exploration** (`--explore N`) — follows the links that match *your instruction* (a sign-up flow explores the register page, a checkout flow explores the cart), multi-hop: pages linked from explored pages are reachable too
- **Selector uniqueness verification** — every CSS/XPath is counted against the live DOM; ambiguous selectors are scoped to a unique ancestor or flagged, so the wrong twin element is never picked
- **Text & value elements captured** — labels, displayed values, status badges get locators too (for "read the X shown on the page" workflows)
- **Dropdown options captured** — `<select>` option texts are scanned so planned test data matches real options
- **CAPTCHA / bot-protection detection** — reported honestly as a blocker instead of doomed retries (never bypassed)

### `--from-plan` — Generate From a Saved/Edited Plan

```bash
selenium-agent --from-plan specs/test-the-login-page.json
selenium-agent --from-plan specs/test-the-login-page.json --no-heal
selenium-agent --from-plan specs/test-the-login-page.json --headless
```

**Smart generation includes:**
- **Deterministic scaffolding** — the `driver` fixture lives in a framework-generated `conftest.py`, never LLM-written (an entire class of collection errors is impossible by construction)
- **Self-verification before saving** — every file is syntax-checked (`ast`), architecture-checked (no `By`/locators/DriverFactory in test files) and completeness-checked (page objects AND tests present), with one automatic LLM repair round
- **Unique runtime test data** — entity-creating flows (sign-ups, records) get uuid-based emails/names, and **strong unique passwords** (never `Password@123`-style patterns that breach-list validators reject)
- **Complete form filling** — "fill the form" means every scanned input/select, not just the fields named in the instruction

### `--heal-only` — Fix Existing Tests

```bash
selenium-agent --heal-only generated_tests/tests/test_login.py

# Heal tests living in YOUR project (page objects auto-discovered from imports)
selenium-agent --heal-only src/tests/test_checkout.py --project /path/to/your/project

# Heal one test only (other tests preserved verbatim)
selenium-agent --heal-only generated_tests/tests/test_login.py \
  --test test_login_locked_out_user

# pytest -k syntax works too
selenium-agent --heal-only generated_tests/tests/test_login.py \
  --test "locked_out or invalid_password"

# Stubborn failure? Give it more rounds and a stronger model
selenium-agent --heal-only generated_tests/tests/test_login.py --max-retries 8 --model gpt-5
```

**Smart healing includes:**
- **Failure-time diagnostics** — on every failure the run reports `FAILURE_URL` (the exact page the browser was on), `FAILURE_ERRORS` (visible alert/validation messages) and `FAILURE_PAGE_TEXT`, so the healer debugs from evidence, not guesses
- **Live DOM re-scan of the failing page(s)** — locator fixes come from ground truth, grouped per page so locators are never borrowed from the wrong page
- Selenium-specific error classification (SeleniumErrorMap) before the LLM is asked — including SPA patterns like "the URL never changes, assert an in-page indicator instead"
- Every fix is **validated** (syntax + architecture) — a broken fix never overwrites a working file
- The final fix is **always verified** with a test run (never "fixed and hoped")
- Pure-Python failures (imports, collection) skip browser scans — attempts are spent where they matter
- Missing locators added to page objects (never to test files); `By` imports stripped from tests
- Targeted mode restores any test functions the LLM accidentally drops
- CAPTCHA-blocked flows are reported as blocked instead of endlessly "fixed"

### `--scan` — Inspect an Existing Project

```bash
selenium-agent --scan /path/to/existing/project
```

Detects folder layout, base page class, test framework, driver setup, naming
conventions and import style — so generated code fits **into** the project.

---

## 🛡️ Battle-Hardened BasePage

Generated code runs on a `BasePage` that survives real-world DOM messiness:

- **Duplicate-element tolerance** — when one selector matches several elements (desktop form + hidden mobile drawer with the same ids, wrapper sharing its id with the input inside), it picks the *displayed, editable, in-viewport* one instead of crashing
- **Fuzzy dropdown matching** — `select_by_text("United States")` still works when the option is literally `"United States of America (the)"`
- **`safe_type()`** — typing verified after entry, with a JS + React-event fallback for stubborn SPA inputs
- **Fluent waits everywhere** — `fluent_wait(locator, 'visible'|'clickable'|'present'|'invisible')`; no `time.sleep()` anywhere
- **Forgiving locator input** — a raw selector string accidentally passed where a locator tuple belongs is auto-normalized instead of crashing

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
└── conftest.py               ← framework-provided driver fixture + failure diagnostics
```

**Architecture enforced by the agents:**
- Locators are **always** class constants in page objects: `LOGIN_BUTTON = (By.CSS_SELECTOR, '[data-test="login-button"]')`
- Test files reference by name: `page.LOGIN_BUTTON` — no `By`, no raw strings, no DriverFactory
- One page object per page — multi-page flows get one class each
- All waits via `fluent_wait(locator, condition)` — no `time.sleep()`
- `wait_for_url()` after every navigation, `page.safe_type()` for React/SPA forms

---

## 🏢 Enterprise-Grade Reliability

| Concern | What the framework does |
|---|---|
| LLM flakiness | Automatic retries with exponential backoff on rate limits / 5xx / timeouts |
| Malformed LLM JSON | Native JSON modes (OpenAI `json_object`, Anthropic prefill) + robust extraction: fences, prose, trailing commas, truncation repair |
| Broken generated code | Every file `ast`-validated + architecture-validated before saving; automatic repair round |
| Broken "fixes" | Healer rejects invalid fixes — never overwrites working files |
| Unverified fixes | Final heal attempt always followed by a verification test run |
| Guessed selectors | Live DOM scans with per-selector **uniqueness verification** |
| Client-side apps | SPA-aware scan polling — waits for React/Vue/Angular to actually render |
| Flaky duplicate DOM | BasePage prefers displayed/editable/in-viewport elements among duplicates |
| Colliding test data | Runtime-unique emails/names + strong unique passwords by rule |
| Bot protection | CAPTCHA detected and reported — never bypassed, never blindly retried |
| Hung test runs | pytest executed with a hard timeout |
| Existing projects | ProjectScanner detects your BasePage, layout & conventions; code fits in |
| Reasoning models | OpenAI gpt-5*/o* token budgets handled (reasoning tokens accounted for) |

---

## 🔧 All CLI Flags Reference

| Flag | Description | Default |
|------|-------------|---------|
| `--provider` | `anthropic` or `openai` | from config |
| `--model` | Any model of that provider, for this run | from config |
| `--api-key` | API key (prefer .env instead) | env var |
| `--url` | Base URL for this run (also saved to config) | from config |
| `--mode` | `pytest` or `bdd` | from config (`pytest`) |
| `--headless` | Headless browser | from config (`false`) |
| `--explore N` | Explore up to N extra same-origin pages while planning (relevance-ranked, multi-hop) | `0` |
| `--output-dir` | Where to save generated files | `generated_tests` |
| `--project` | Existing project path (saved to config — set once) | from config |
| `--max-retries` | Healer fix attempts | `5` |
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

**Any chat model from OpenAI or Anthropic works** — pass it via `--model` or save it with `selenium-agent config --model <name>`. Recommendations:

| Provider | Model | Best for |
|----------|-------|----------|
| OpenAI | `gpt-4o-mini` | Simple flows, lowest cost |
| OpenAI | `gpt-4o` | Strong default for real projects |
| OpenAI | `gpt-5` / `gpt-5-mini` | Complex multi-page flows (reasoning models — token budgets handled automatically) |
| Anthropic | `claude-fable-5` | Most intelligent — hardest multi-page flows |
| Anthropic | `claude-opus-4-8` | Complex flows, high quality |
| Anthropic | `claude-sonnet-5` | Strong default for real projects |
| Anthropic | `claude-haiku-4-5-20251001` | Simple flows, lowest cost |

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
