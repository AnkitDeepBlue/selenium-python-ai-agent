# Selenium Python AI Agent

AI-powered multi-agent framework that plans, writes, runs, and heals Selenium Python tests using Anthropic or OpenAI models.

[![PyPI version](https://badge.fury.io/py/selenium-python-ai-agent.svg)](https://pypi.org/project/selenium-python-ai-agent/)
[![Python](https://img.shields.io/badge/python-3.9+-blue.svg)](https://python.org)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

## Overview

The package is built around three agents:

```text
Your instruction
      |
      v
 Planner -> Coder -> Healer
```

- `Planner` turns a plain-English request into a structured test plan.
- `Coder` generates Selenium Python files using a Page Object Model style.
- `Healer` runs tests, captures failures, asks the selected LLM for fixes, and retries.

It supports both:

- CLI usage for quick generation
- Python package usage for embedding in scripts, services, or internal tooling

## Requirements

- Python 3.9+
- Google Chrome installed
- An API key for one supported provider
- Billing/quota enabled for that provider's API account

Supported providers:

- `anthropic`
- `openai`

## Install

Install from PyPI:

```bash
pip install selenium-python-ai-agent
```

For local development in this repository:

```bash
pip install -e .
```

That `-e` means editable install. After that, Python can import `selenium_agent` directly from your working copy.

## API Keys

Create a provider API key here:

- Anthropic: `https://console.anthropic.com`
- OpenAI: `https://platform.openai.com/api-keys`

Set one provider key in your shell:

```bash
export ANTHROPIC_API_KEY="your-anthropic-key"
```

or

```bash
export OPENAI_API_KEY="your-openai-key"
```

## CLI Usage

### Quick Start

Generate a plan only:

```bash
selenium-agent --provider openai --plan-only "test login page of github.com"
```

Run the full flow:

```bash
selenium-agent --provider anthropic "test login page of github.com"
```

Skip the healer:

```bash
selenium-agent --provider openai --no-heal "test checkout flow"
```

Heal existing generated files:

```bash
selenium-agent --provider openai --heal-only generated_tests/tests/test_login.py generated_tests/pages/login_page.py
```

Write output to a custom directory:

```bash
selenium-agent --provider anthropic --output-dir my_tests "test signup page of example.com"
```

### CLI Options

| Flag | Description | Default |
|------|-------------|---------|
| `--api-key` | Provider API key | uses env var |
| `--provider` | `anthropic` or `openai` | `anthropic` |
| `--model` | Override the provider default model | provider default |
| `--output-dir` | Where generated files are saved | `generated_tests` |
| `--max-retries` | Healer retry attempts | `3` |
| `--no-heal` | Skip auto-healing | `False` |
| `--plan-only` | Generate a plan only | `False` |
| `--heal-only FILE ...` | Heal existing files | not set |

### CLI Examples

```bash
selenium-agent --provider openai --plan-only "test search on github.com"
selenium-agent --provider openai "test login page of github.com"
selenium-agent --provider anthropic --no-heal "test profile page of example.com"
selenium-agent --provider openai --model gpt-5-mini "test search workflow"
```

## Python Package Usage

### Import the Package

```python
from selenium_agent import SeleniumAgent
```

### Full Run

```python
from selenium_agent import SeleniumAgent

agent = SeleniumAgent(
    provider="openai",
    api_key="your-openai-key",
    output_dir="generated_tests",
    auto_heal=True,
)

result = agent.run("test login page of github.com")

print(result["plan"])
print(result["files"])
print(result["heal_result"])
```

### Run Individual Stages

```python
from selenium_agent import SeleniumAgent

agent = SeleniumAgent(provider="anthropic", api_key="your-anthropic-key")

plan = agent.plan_only("test login page of github.com")
files = agent.code_only(plan)
heal_result = agent.heal_only(files)
```

### Use Environment Variables Instead of Passing Keys

```python
import os
from selenium_agent import SeleniumAgent

os.environ["OPENAI_API_KEY"] = "your-openai-key"

agent = SeleniumAgent(provider="openai")
plan = agent.plan_only("test login page of github.com")
```

## Generated Output

Typical output structure:

```text
generated_tests/
├── pages/
│   └── login_page.py
└── tests/
    └── test_login.py
```

## Public User Setup Notes

If you want other people to use this package successfully, document these upfront:

1. They need a valid provider API key.
2. ChatGPT Plus is not the same as OpenAI API billing.
3. Browser automation depends on Chrome plus a compatible ChromeDriver.
4. API quota and browser-driver mismatch are the two most common failures.

## Troubleshooting

### `429 insufficient_quota`

The provider account has no available API quota or billing is not enabled.

- OpenAI billing: `https://platform.openai.com/settings/organization/billing/overview`
- OpenAI usage: `https://platform.openai.com/usage`

### `401 invalid_api_key`

The API key is invalid, revoked, or belongs to the wrong provider.

### `ModuleNotFoundError: anthropic` or `ModuleNotFoundError: openai`

Install the missing provider SDK:

```bash
pip install anthropic
pip install openai
```

### `SessionNotCreatedException`

Your local browser version and ChromeDriver version do not match. Update the driver or use an automatic driver manager strategy.

## How to Make This Importable as a Python Package

You asked how to "register that as python package to import". There are two separate cases.

### 1. Import it locally on your machine

Inside the project folder, run:

```bash
pip install -e .
```

Then Python can import it:

```python
from selenium_agent import SeleniumAgent
```

This works because your project already has:

- a package directory: `selenium_agent/`
- an `__init__.py`
- a `pyproject.toml`

Those are the pieces that make it a Python package.

### 2. Publish it so the public can install it

You publish it to PyPI so users can run:

```bash
pip install selenium-python-ai-agent
```

Basic publishing flow:

1. Create an account on `https://pypi.org`
2. Make sure `pyproject.toml` has the correct package name and metadata
3. Build the package
4. Upload it to PyPI

Build commands:

```bash
python -m pip install build twine
python -m build
python -m twine check dist/*
python -m twine upload dist/*
```

That will upload your package distributions from `dist/` to PyPI.

After that, public users can install it with:

```bash
pip install selenium-python-ai-agent
```

## Recommended Release Checklist

Before promoting it for public use, I recommend:

1. Add a real end-to-end smoke test path that does not depend on paid API quota.
2. Add a `mock` provider for demos and CI.
3. Improve ChromeDriver auto-management inside generated tests.
4. Add a `.env` setup example for local users.
5. Add screenshots or sample generated output in the README.
6. Make sure the package name is available on PyPI before publishing.

## Development

Run tests:

```bash
python -m pytest
```

Run CLI help:

```bash
python -m selenium_agent.cli --help
```

## License

MIT
