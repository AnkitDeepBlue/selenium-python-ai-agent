# Contributing

Thanks for your interest in improving Selenium Python AI Agent!

## Getting started

```bash
git clone https://github.com/AnkitDeepBlue/selenium-python-ai-agent.git
cd selenium-python-ai-agent
python -m venv .venv && source .venv/bin/activate
pip install -e . && pip install pytest python-dotenv
```

## Before opening a PR

1. Run the unit tests (no browser or API key needed):
   ```bash
   python -m pytest tests/ -q
   ```
2. If you touched an agent or the scanner, verify end-to-end against a live
   demo site (e.g. https://www.saucedemo.com) with your own API key.
3. Keep changes **generic** — nothing in the agents may be tailored to a
   specific website. Framework rules live in prompts and deterministic
   scaffolding, never as site-specific hacks.

## Pull requests

- Open PRs against `main`; they are merged only after review by the maintainer.
- Write commit messages in plain English describing the failure class you
  fixed or the capability you added.
