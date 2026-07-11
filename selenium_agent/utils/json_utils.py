"""
JSON UTILITIES
==============
Robust extraction of JSON objects from LLM responses.

LLMs wrap JSON in markdown fences, add prose before/after, or truncate
mid-object when they hit the token limit. Every agent (Planner, Coder,
Healer) parses LLM JSON through this single module so the behavior is
consistent and battle-tested in one place.
"""

from __future__ import annotations

import json
import re


class LLMJSONError(ValueError):
    """Raised when no usable JSON object could be extracted from an LLM response."""

    def __init__(self, message: str, raw: str = ""):
        snippet = (raw or "")[:400]
        super().__init__(f"{message}\n--- response snippet ---\n{snippet}")
        self.raw = raw


def strip_markdown_fences(raw: str) -> str:
    """Remove ```json ... ``` fences, keeping the largest fenced block if present."""
    if "```" not in raw:
        return raw.strip()
    blocks = re.findall(r"```(?:json)?\s*([\s\S]*?)```", raw)
    if blocks:
        # Take the largest block — small ones are usually inline examples
        return max(blocks, key=len).strip()
    # Unclosed fence: drop everything before the first fence marker
    return raw.split("```", 1)[-1].removeprefix("json").strip()


def find_balanced_object(raw: str) -> str:
    """
    Return the first balanced top-level {...} object in raw.
    If the object is truncated, repair it structurally: close the open
    string, then close arrays/objects in the reverse order they were opened.
    """
    start = raw.find("{")
    if start == -1:
        raise LLMJSONError("No JSON object found in LLM response", raw)

    stack: list[str] = []
    in_str, esc = False, False
    for i, ch in enumerate(raw[start:], start):
        if esc:
            esc = False
            continue
        if ch == "\\" and in_str:
            esc = True
            continue
        if ch == '"':
            in_str = not in_str
            continue
        if in_str:
            continue
        if ch in "{[":
            stack.append(ch)
        elif ch in "}]":
            if stack:
                stack.pop()
            if not stack:
                return raw[start : i + 1]

    # Truncated — repair by unwinding the open-structure stack
    frag = raw[start:]
    if in_str:
        frag += '"'
    for opener in reversed(stack):
        frag += "}" if opener == "{" else "]"
    return frag


def extract_json_object(raw: str) -> dict:
    """
    Extract and parse a JSON object from an arbitrary LLM response.

    Handles: markdown fences, leading/trailing prose, truncated output.
    Raises LLMJSONError when nothing parseable can be recovered.
    """
    if not raw or not raw.strip():
        raise LLMJSONError("Empty LLM response", raw)

    candidate = find_balanced_object(strip_markdown_fences(raw))
    try:
        parsed = json.loads(candidate)
    except json.JSONDecodeError:
        # Last resort: remove trailing commas (a common LLM slip) and retry
        cleaned = re.sub(r",\s*([}\]])", r"\1", candidate)
        try:
            parsed = json.loads(cleaned)
        except json.JSONDecodeError as exc:
            raise LLMJSONError(f"LLM returned invalid JSON: {exc}", raw) from exc

    if not isinstance(parsed, dict):
        raise LLMJSONError(f"Expected JSON object, got {type(parsed).__name__}", raw)
    return parsed
