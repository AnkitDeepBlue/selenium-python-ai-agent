# Selenium Python AI Agent 🤖

> AI-powered multi-agent framework that **plans**, **writes**, and **heals** Selenium Python tests automatically.
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
┌─────────────┐     ┌─────────────┐     ┌─────────────┐
│   PLANNER   │────▶│    CODER    │────▶│   HEALER    │
│   Agent 1   │     │   Agent 2   │     │   Agent 3   │
│             │     │             │     │             │
│ Understands │     │  Generates  │     │ Runs tests, │
│ what to test│     │  Selenium   │     │ fixes errors│
│ & creates   │     │  Python     │     │ & retries   │
│ test plan   │     │  POM code   │     │ auto        │
└─────────────┘     └─────────────┘     └─────────────┘
```

---

## ⚡ Quick Start

### Install

```bash
pip install selenium-python-ai-agent
```

### Get an API Key

| Provider | Where to get |
|----------|-------------|
| Anthropic Claude | [console.anthropic.com](https://console.anthropic.com) |
| OpenAI ChatGPT | [platform.openai.com](https://platform.openai.com) |

---

## 🖥️ CLI Usage

```bash
# --- Anthropic Claude (default) ---
export ANTHROPIC_API_KEY="your-claude-key"
selenium-agent "test login page of amazon.com"

# --- OpenAI ChatGPT ---
export OPENAI_API_KEY="your-openai-key"
selenium-agent "test login page of amazon.com" --provider openai

# Pass key directly
selenium-agent "test search on flipkart.com" --api-key YOUR_KEY

# See plan only (no code generated)
selenium-agent --plan-only "test login page of github.com"

# Skip auto-healing
selenium-agent "test checkout" --no-heal

# Heal existing broken tests
selenium-agent --heal-only generated_tests/tests/test_login.py

# Custom output directory
selenium-agent "test signup page" --output-dir my_project/tests
```

---

## 🐍 Python Library Usage

```python
from selenium_agent import SeleniumAgent

# Using Anthropic Claude (default)
agent = SeleniumAgent(api_key="your-claude-key")
result = agent.run("test login page of flipkart.com")

# Using OpenAI ChatGPT
agent = SeleniumAgent(provider="openai", api_key="your-openai-key")
result = agent.run("test login page of flipkart.com")

# Individual agents
plan  = agent.plan_only("test login page")
files = agent.code_only(plan)
heal  = agent.heal_only(files)
```

---

## 📁 Generated Output

```
generated_tests/
├── pages/
│   └── login_page.py       ← Page Object class
└── tests/
    └── test_login.py       ← pytest test file
```

---

## 🔧 CLI Options

| Flag | Description | Default |
|------|-------------|---------|
| `--provider` | LLM provider: `anthropic` or `openai` | `anthropic` |
| `--api-key` | Provider API key | env var |
| `--model` | Override default model | provider default |
| `--output-dir` | Where to save files | `generated_tests` |
| `--max-retries` | Healer retry attempts | `3` |
| `--no-heal` | Skip auto-healing | False |
| `--plan-only` | Only generate plan | False |
| `--heal-only FILE` | Only heal given files | - |

---

## 📦 Requirements

- Python 3.9+
- Chrome/Firefox browser installed
- API key from Anthropic **or** OpenAI

---

## 🤝 Contributing

PRs welcome! See [CONTRIBUTING.md](CONTRIBUTING.md)

---

## 📄 License

MIT — free to use, modify, distribute.

---

*Built with ❤️ by [Ankit Tripathi](https://github.com/AnkitDeepBlue)*
