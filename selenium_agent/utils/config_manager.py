"""
CONFIG MANAGER
==============
Reads/writes .selenium-agent.json in the project root.
Stores user preferences so they don't have to repeat CLI flags.

Priority order (highest to lowest):
  CLI flag > .env > .selenium-agent.json > built-in defaults
"""

import json
import os
from pathlib import Path
from selenium_agent.utils.logger import setup_logger

logger = setup_logger("Config")

CONFIG_FILENAME = ".selenium-agent.json"

DEFAULTS = {
    "provider":  "anthropic",
    "model":     None,
    "headless":  False,
    "mode":      "pytest",
    "base_url":  None,   # persisted across runs — no need to pass --url repeatedly
    "project":   None,   # persisted by --scan/--project — fit into this project automatically
}


def _find_config_path() -> Path:
    """Look for config in CWD first, then home directory."""
    cwd_config = Path.cwd() / CONFIG_FILENAME
    if cwd_config.exists():
        return cwd_config
    return Path.home() / CONFIG_FILENAME


def load() -> dict:
    """Load config from file. Returns defaults if file doesn't exist."""
    path = _find_config_path()
    if not path.exists():
        return dict(DEFAULTS)
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        merged = {**DEFAULTS, **data}
        return merged
    except Exception as e:
        logger.warning(f"⚠️  Could not read {path}: {e} — using defaults")
        return dict(DEFAULTS)


def save(updates: dict, config_path: Path | None = None) -> Path:
    """
    Merge updates into existing config and save.
    Creates config in CWD if it doesn't exist yet.
    """
    path = config_path or _find_config_path()
    if not path.exists():
        path = Path.cwd() / CONFIG_FILENAME

    current = load()
    current.update({k: v for k, v in updates.items() if v is not None})

    path.write_text(json.dumps(current, indent=2), encoding="utf-8")
    return path


def get_effective(cli_args: dict) -> dict:
    """
    Merge config + CLI args. CLI always wins over config.
    cli_args: dict of {key: value} from argparse (None means not provided).
    """
    config = load()
    effective = dict(config)

    for key, value in cli_args.items():
        if value is not None and value is not False:
            effective[key] = value
        elif key == "headless" and value is True:
            effective[key] = True

    return effective
