"""
LOCATOR ADVISOR
===============
Selenium-specific intelligence for choosing the best locator strategy.

The Planner and Coder agents use this to:
- Rank locator strategies by reliability
- Detect anti-patterns in XPath/CSS
- Suggest better alternatives
- Embed locator guidance in generated code

Locator Priority (most → least reliable):
  1. By.ID           — unique, fast, stable
  2. By.NAME         — good for form fields
  3. By.CSS_SELECTOR — flexible, fast, readable
  4. By.XPATH        — powerful but fragile if absolute
  5. By.LINK_TEXT    — brittle, language-dependent
  6. By.CLASS_NAME   — often not unique
  7. By.TAG_NAME     — almost never unique
"""

from __future__ import annotations
from dataclasses import dataclass
from enum import IntEnum


class LocatorScore(IntEnum):
    """Reliability score for locator strategies (higher = better)."""
    ID = 100
    NAME = 90
    CSS_SELECTOR = 80
    XPATH_RELATIVE = 70
    DATA_TESTID = 95       # data-testid is best practice
    ARIA_LABEL = 75
    LINK_TEXT = 50
    PARTIAL_LINK_TEXT = 45
    CLASS_NAME = 40
    TAG_NAME = 10
    XPATH_ABSOLUTE = 5     # Absolute XPath — worst


@dataclass
class LocatorSuggestion:
    """A single locator suggestion with explanation."""
    strategy: str          # By.ID, By.CSS_SELECTOR, etc.
    value: str             # The locator value
    score: int             # Reliability score
    reason: str            # Why this was suggested
    warning: str = ""      # Any anti-pattern warning


class LocatorAdvisor:
    """
    Advises on the best Selenium locator strategy.

    Used by Planner Agent to embed locator guidance in test plans,
    and by Coder Agent to generate reliable locators.
    """

    # Anti-patterns to warn about
    ANTI_PATTERNS = {
        "absolute_xpath": {
            "pattern": r"^/html/body",
            "warning": "Absolute XPath is extremely fragile — breaks on any DOM change.",
            "suggestion": "Use By.ID or By.CSS_SELECTOR instead."
        },
        "index_xpath": {
            "pattern": r"\[\d+\]",
            "warning": "Index-based XPath (e.g. [2]) breaks when new elements are added.",
            "suggestion": "Use a unique attribute like id, name, or data-testid."
        },
        "dynamic_class": {
            "pattern": r"[a-z0-9]{8,}",  # Random-looking class names
            "warning": "This class name looks auto-generated and may change on rebuild.",
            "suggestion": "Ask developers to add stable data-testid attributes."
        },
    }

    # Locator strategy priority list (for Coder Agent prompt injection)
    PRIORITY_GUIDE = """
SELENIUM LOCATOR STRATEGY — Priority Order:

1. data-testid attribute (BEST)
   css = "[data-testid='login-button']"
   → Stable, developer-intended for testing

2. By.ID (EXCELLENT)
   By.ID, "username"
   → Fast, unique per page spec

3. By.NAME (GOOD for forms)
   By.NAME, "email"
   → Stable for form inputs

4. By.CSS_SELECTOR (GOOD)
   By.CSS_SELECTOR, "button.login-btn"
   By.CSS_SELECTOR, "input[placeholder='Email']"
   By.CSS_SELECTOR, "form > button[type='submit']"
   → Readable, faster than XPath

5. Relative By.XPATH (ACCEPTABLE)
   By.XPATH, "//button[contains(text(),'Login')]"
   By.XPATH, "//input[@placeholder='Email']"
   → Use only when CSS won't work

6. By.LINK_TEXT (LIMITED)
   By.LINK_TEXT, "Forgot Password"
   → Only for anchor tags, breaks on text change

NEVER USE:
  ❌ Absolute XPath: /html/body/div[1]/form/input[2]
  ❌ Index-based: (//button)[3]
  ❌ Auto-generated classes: .sc-bdXHXe.hQDDGZ
"""

    @classmethod
    def get_priority_guide(cls) -> str:
        """Return the full locator priority guide for injection into LLM prompts."""
        return cls.PRIORITY_GUIDE

    @classmethod
    def rank_locators(cls, locators: list[dict]) -> list[LocatorSuggestion]:
        """
        Rank a list of locator options by reliability.

        Args:
            locators: List of dicts with 'strategy' and 'value' keys

        Returns:
            Sorted list of LocatorSuggestion (best first)

        Example:
            ranked = LocatorAdvisor.rank_locators([
                {"strategy": "xpath", "value": "/html/body/div/input"},
                {"strategy": "id", "value": "username"},
                {"strategy": "css", "value": "input.login-field"},
            ])
        """
        strategy_scores = {
            "id": LocatorScore.ID,
            "name": LocatorScore.NAME,
            "css": LocatorScore.CSS_SELECTOR,
            "css_selector": LocatorScore.CSS_SELECTOR,
            "xpath": LocatorScore.XPATH_RELATIVE,
            "link_text": LocatorScore.LINK_TEXT,
            "class_name": LocatorScore.CLASS_NAME,
            "tag_name": LocatorScore.TAG_NAME,
            "data_testid": LocatorScore.DATA_TESTID,
            "aria_label": LocatorScore.ARIA_LABEL,
        }

        suggestions = []
        for loc in locators:
            strategy = loc.get("strategy", "").lower().replace(" ", "_")
            value = loc.get("value", "")
            score = strategy_scores.get(strategy, 30)

            # Penalize absolute XPath
            if strategy == "xpath" and value.startswith("/html"):
                score = LocatorScore.XPATH_ABSOLUTE
                warning = "⚠️ Absolute XPath — extremely fragile!"
            elif strategy == "xpath" and "[" in value and value[value.index("[") + 1].isdigit():
                score = max(score - 30, 10)
                warning = "⚠️ Index-based XPath — fragile!"
            elif "[data-testid" in value:
                score = LocatorScore.DATA_TESTID
                warning = ""
            else:
                warning = ""

            reason = cls._get_reason(strategy, score)
            suggestions.append(LocatorSuggestion(
                strategy=strategy,
                value=value,
                score=score,
                reason=reason,
                warning=warning,
            ))

        return sorted(suggestions, key=lambda s: s.score, reverse=True)

    @classmethod
    def best_locator(cls, locators: list[dict]) -> LocatorSuggestion:
        """Return the single best locator from a list."""
        ranked = cls.rank_locators(locators)
        return ranked[0] if ranked else None

    @classmethod
    def _get_reason(cls, strategy: str, score: int) -> str:
        reasons = {
            "id": "Unique per-page, fastest lookup, most stable",
            "name": "Good for form fields, stable in most frameworks",
            "css": "Readable, fast, flexible — preferred over XPath",
            "css_selector": "Readable, fast, flexible — preferred over XPath",
            "xpath": "Use only when CSS/ID not available",
            "link_text": "Brittle — breaks on text change or i18n",
            "class_name": "Often not unique — combine with other strategies",
            "tag_name": "Almost never unique — avoid",
            "data_testid": "Best practice — developer-defined test hook",
            "aria_label": "Good for accessibility-first apps",
        }
        return reasons.get(strategy, "No specific guidance available")

    @classmethod
    def validate(cls, strategy: str, value: str) -> dict:
        """
        Validate a single locator and return warnings.

        Returns:
            dict with 'valid', 'score', 'warnings', 'suggestions'
        """
        import re
        warnings = []
        suggestions = []

        if strategy.lower() == "xpath":
            if value.startswith("/html"):
                warnings.append("Absolute XPath is extremely fragile")
                suggestions.append("Convert to By.ID or By.CSS_SELECTOR")

            if re.search(r"\[\d+\]", value):
                warnings.append("Index-based XPath breaks when DOM changes")
                suggestions.append("Use unique attribute selectors instead")

        if strategy.lower() in ("class_name", "css_selector"):
            if re.search(r"\b[a-z0-9]{8,}\b", value):
                warnings.append("Possible auto-generated class name detected")
                suggestions.append("Request data-testid from developers")

        score_map = {
            "id": LocatorScore.ID,
            "name": LocatorScore.NAME,
            "css_selector": LocatorScore.CSS_SELECTOR,
            "xpath": LocatorScore.XPATH_RELATIVE if not value.startswith("/html") else LocatorScore.XPATH_ABSOLUTE,
            "link_text": LocatorScore.LINK_TEXT,
            "class_name": LocatorScore.CLASS_NAME,
            "tag_name": LocatorScore.TAG_NAME,
        }

        score = score_map.get(strategy.lower(), 30)

        return {
            "valid": len(warnings) == 0,
            "score": score,
            "warnings": warnings,
            "suggestions": suggestions,
        }
