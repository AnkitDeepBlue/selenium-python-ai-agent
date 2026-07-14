"""
SPEC WRITER
===========
Renders a structured test plan (the Planner's JSON) as a human-readable
Markdown spec and persists both to the `specs/` directory — mirroring how
Playwright's planner agent saves Markdown test plans.

specs/
├── login-page.md      ← human-readable plan (review / edit / re-run)
└── login-page.json    ← machine-readable plan (input to the Generator)
"""

from __future__ import annotations

import json
import re
from datetime import datetime
from pathlib import Path


def slugify(text: str, max_len: int = 60) -> str:
    """'Test the Login page!' → 'test-the-login-page'"""
    slug = re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")
    return slug[:max_len].rstrip("-") or "test-plan"


def render_markdown(plan: dict, instruction: str = "") -> str:
    """Render a plan dict (pytest or bdd mode) as a Markdown test plan."""
    mode = plan.get("mode", "pytest")
    url = plan.get("url", "")
    scenarios = plan.get("test_scenarios") or plan.get("scenarios") or []
    pages = plan.get("page_objects_needed", [])
    locators = plan.get("locators", [])

    lines = [
        f"# Test Plan — {plan.get('feature_title') or instruction or 'Selenium Test Suite'}",
        "",
        f"- **Generated**: {datetime.now().strftime('%Y-%m-%d %H:%M')}",
        f"- **Mode**: {mode}",
        f"- **Target URL**: {url or 'n/a'}",
        f"- **Browser**: {plan.get('browser', 'chrome')} (headless={plan.get('headless', False)})",
        "",
    ]

    # Non-technical narrative — shareable with stakeholders as-is
    if plan.get("summary"):
        lines += ["## Summary (for stakeholders)", "", str(plan["summary"]), ""]

    strategy = plan.get("test_strategy") or {}
    if strategy:
        lines += ["## Test Strategy", ""]
        for key, label in (("scope", "Scope"), ("out_of_scope", "Out of scope"),
                           ("approach", "Approach"), ("environment", "Environment")):
            if strategy.get(key):
                lines.append(f"- **{label}:** {strategy[key]}")
        risks = strategy.get("risks") or []
        if risks:
            lines.append("- **Risks & assumptions:**")
            lines += [f"  - {r}" for r in risks]
        lines.append("")

    lines += [
        "## Page Objects",
        "",
    ]
    for page in pages:
        lines.append(f"- `{page}`")
    if not pages:
        lines.append("- _none planned_")

    lines += ["", "## Scenarios", ""]
    for idx, sc in enumerate(scenarios, 1):
        name = sc.get("name", f"Scenario {idx}")
        lines.append(f"### {sc.get('id', f'TC{idx:03d}')} — {name}")
        lines.append("")
        if sc.get("description"):
            lines.append(f"{sc['description']}")
            lines.append("")
        lines.append("**Steps:**")
        for step in sc.get("steps", []):
            if isinstance(step, dict):  # BDD step: {"type": "Given", "text": "..."}
                lines.append(f"1. **{step.get('type', '')}** {step.get('text', '')}")
            else:
                lines.append(f"1. {step}")
        if sc.get("expected_result"):
            lines.append("")
            lines.append(f"**Expected:** {sc['expected_result']}")
        if sc.get("test_data"):
            lines.append("")
            lines.append(f"**Test data:** `{json.dumps(sc['test_data'])}`")
        lines.append("")

    if locators:
        lines += [
            "## Locators (from live DOM scan)",
            "",
            "| Page Object | Element | Selector | Wait |",
            "|---|---|---|---|",
        ]
        for loc in locators:
            selector = loc.get("css") or loc.get("xpath") or ""
            lines.append(
                f"| {loc.get('page_object', '')} | {loc.get('element', '')} "
                f"| `{selector}` | {loc.get('wait_condition', 'visible')} |"
            )
        lines.append("")

    if plan.get("notes"):
        lines += ["## Notes", "", str(plan["notes"]), ""]

    return "\n".join(lines)


def save_spec(plan: dict, instruction: str, specs_dir: str | Path = "specs") -> dict:
    """
    Save the plan as Markdown + JSON in specs_dir.
    Returns {"markdown": path, "json": path}.
    """
    specs_root = Path(specs_dir)
    specs_root.mkdir(parents=True, exist_ok=True)

    slug = slugify(plan.get("feature_name") or instruction)
    md_path = specs_root / f"{slug}.md"
    json_path = specs_root / f"{slug}.json"

    md_path.write_text(render_markdown(plan, instruction), encoding="utf-8")
    json_path.write_text(json.dumps(plan, indent=2), encoding="utf-8")

    return {"markdown": str(md_path), "json": str(json_path)}


def load_plan(plan_file: str | Path) -> dict:
    """Load a saved plan (.json) for the Generator to consume."""
    path = Path(plan_file)
    if not path.exists():
        raise FileNotFoundError(f"Plan file not found: {path}")
    if path.suffix == ".md":
        # Allow pointing at the markdown twin — load the sibling .json
        sibling = path.with_suffix(".json")
        if not sibling.exists():
            raise FileNotFoundError(
                f"Markdown plans are for humans — the Generator needs the JSON twin, "
                f"which was not found: {sibling}"
            )
        path = sibling
    return json.loads(path.read_text(encoding="utf-8"))
