"""
GHERKIN ADVISOR
===============
pytest-bdd specific intelligence for writing good BDD tests.

Provides:
- Gherkin best practices guide (injected into LLM prompts)
- Step naming conventions
- Anti-pattern detection
- Feature file structure rules
"""

from __future__ import annotations
from dataclasses import dataclass


@dataclass
class StepValidation:
    """Result of validating a Gherkin step."""
    valid: bool
    warnings: list[str]
    suggestions: list[str]


class GherkinAdvisor:
    """
    Advises on writing good Gherkin feature files and step definitions.
    Used by Planner and Coder agents when BDD mode is enabled.
    """

    BEST_PRACTICES_GUIDE = """
PYTEST-BDD / GHERKIN BEST PRACTICES:

FEATURE FILE RULES:
1. One Feature per file — named <feature>.feature
2. Feature title describes the business capability, not the UI
3. Scenarios should be independent — no shared state
4. Use Scenario Outline for data-driven tests
5. Tags (@smoke, @regression) go above Scenario

STEP WRITING RULES:
1. Given  → System state / precondition
   ✅ Given I am on the login page
   ✅ Given the user "admin" exists in the system
   ❌ Given I click the login button  (that's a When)

2. When   → User action
   ✅ When I enter username "standard_user"
   ✅ When I click the submit button
   ❌ When the page shows an error  (that's a Then)

3. Then   → Expected outcome / assertion
   ✅ Then I should see the dashboard
   ✅ Then the error message "Invalid credentials" should be displayed
   ❌ Then I click OK  (that's a When)

4. And/But → Continuation of previous step type
   ✅ When I enter username "user"
      And I enter password "pass"
      And I click Login

STEP DEFINITION RULES:
1. Use parsers.parse() for parameterized steps:
   @when(parsers.parse('I enter username "{username}"'))
   def enter_username(login_page, username):
       login_page.type(LoginPage.USERNAME_INPUT, username)

2. Never put assertions in Given/When steps
3. Always use page object methods — never raw driver calls
4. Fixtures inject page objects, not driver directly

ANTI-PATTERNS TO AVOID:
❌ UI-centric steps: "When I click the blue button at position 3"
❌ Steps with implementation details: "When I send POST to /api/login"
❌ Chained UI actions in one step: "When I login and navigate to profile"
❌ Assertions in Given: "Given the error message is shown"
❌ Vague Then: "Then it works"

GOOD SCENARIO EXAMPLE:
  @smoke @login
  Scenario: Successful login with valid credentials
    Given I am on the login page
    When I enter username "standard_user"
    And I enter password "secret_sauce"
    And I click the login button
    Then I should be redirected to the products page
    And the page title should be "Products"

SCENARIO OUTLINE EXAMPLE (data-driven):
  Scenario Outline: Login with multiple users
    Given I am on the login page
    When I enter username "<username>"
    And I enter password "<password>"
    Then I should see "<expected_result>"

    Examples:
      | username        | password     | expected_result     |
      | standard_user   | secret_sauce | Products            |
      | locked_out_user | secret_sauce | Epic sadface logo   |
"""

    @classmethod
    def get_guide(cls) -> str:
        """Return full Gherkin best practices guide for LLM prompt injection."""
        return cls.BEST_PRACTICES_GUIDE

    @classmethod
    def validate_step(cls, step: str) -> StepValidation:
        """
        Validate a single Gherkin step for common anti-patterns.

        Args:
            step: Full step string e.g. "When I click the blue button at index 3"

        Returns:
            StepValidation with warnings and suggestions
        """
        warnings = []
        suggestions = []
        step_lower = step.lower()

        # UI-centric anti-patterns
        ui_terms = ["click", "button", "input", "field", "textbox", "dropdown"]
        if any(t in step_lower for t in ui_terms) and step_lower.startswith("given"):
            warnings.append("Given steps should describe state, not UI actions")
            suggestions.append("Rewrite as: Given the user is authenticated")

        # Index-based references
        if any(w in step_lower for w in ["index", "position", "number", "nth"]):
            warnings.append("Index-based steps are brittle")
            suggestions.append("Reference elements by label or role instead")

        # Assertion in Given/When
        if step_lower.startswith(("given", "when")) and any(
            w in step_lower for w in ["should", "must", "verify", "assert", "check"]
        ):
            warnings.append("Assertions belong in Then steps, not Given/When")
            suggestions.append("Move verification to a Then step")

        # Vague Then
        if step_lower.startswith("then") and any(
            w in step_lower for w in ["it works", "success", "ok", "done"]
        ):
            warnings.append("Vague Then step — be specific about what is verified")
            suggestions.append("Specify exact element, message, or URL expected")

        # Too many actions in one step
        action_words = ["and", "then", "also", "afterwards"]
        if sum(1 for w in action_words if f" {w} " in step_lower) >= 2:
            warnings.append("Step contains multiple actions — split into separate steps")
            suggestions.append("Use And/But to chain related steps")

        return StepValidation(
            valid=len(warnings) == 0,
            warnings=warnings,
            suggestions=suggestions,
        )

    @classmethod
    def validate_feature(cls, feature_content: str) -> list[StepValidation]:
        """Validate all steps in a feature file."""
        results = []
        for line in feature_content.splitlines():
            line = line.strip()
            if any(line.startswith(kw) for kw in ("Given", "When", "Then", "And", "But")):
                results.append(cls.validate_step(line))
        return results

    @classmethod
    def get_folder_structure(cls) -> str:
        """Return recommended BDD folder structure for generated tests."""
        return """
RECOMMENDED pytest-bdd FOLDER STRUCTURE:

generated_tests/
├── features/                    ← .feature files (Gherkin)
│   └── login.feature
├── step_definitions/            ← pytest-bdd step implementations
│   └── test_login_steps.py     ← must start with test_ for pytest discovery
├── pages/                       ← Page Objects (BasePage subclasses)
│   └── login_page.py
└── conftest.py                  ← shared fixtures (driver, etc.)

IMPORTANT:
- step_definitions files MUST start with test_ for pytest to discover them
- Feature files go in features/ folder
- conftest.py must be at root of generated_tests/
- scenarios() call in step file links to feature file
"""
