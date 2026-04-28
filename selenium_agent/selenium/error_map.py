"""
SELENIUM ERROR MAP
==================
Maps known Selenium exceptions to root causes and exact fixes.

The Healer Agent uses this to:
- Identify error type from pytest output
- Apply targeted fix before asking the LLM
- Reduce LLM calls for common/known errors

This is what makes the Healer truly Selenium-specific,
not just a generic "ask LLM to fix" agent.
"""

from __future__ import annotations
from dataclasses import dataclass


@dataclass
class ErrorFix:
    """A known Selenium error with its cause and fix."""
    exception: str          # Exception class name
    pattern: str            # String to search for in error output
    cause: str              # What causes this error
    fix: str                # How to fix it in code
    code_before: str        # Example of broken code
    code_after: str         # Example of fixed code
    severity: str           # low | medium | high


class SeleniumErrorMap:
    """
    Lookup table of known Selenium errors → targeted fixes.

    Used by the Healer Agent to apply precise fixes
    before falling back to LLM healing.
    """

    KNOWN_ERRORS: list[ErrorFix] = [

        ErrorFix(
            exception="NoSuchElementException",
            pattern="no such element",
            cause="Element not found in DOM — wrong locator or page not loaded",
            fix="Add WebDriverWait for element presence, or fix the locator",
            code_before='driver.find_element(By.ID, "username")',
            code_after='WebDriverWait(driver, 10).until(EC.presence_of_element_located((By.ID, "username")))',
            severity="high",
        ),

        ErrorFix(
            exception="TimeoutException",
            pattern="timeout",
            cause="Element did not appear within the wait timeout",
            fix="Increase timeout, verify locator is correct, or check if page loaded",
            code_before='WebDriverWait(driver, 5).until(EC.visibility_of_element_located((By.ID, "result")))',
            code_after='WebDriverWait(driver, 15).until(EC.visibility_of_element_located((By.ID, "result")))',
            severity="medium",
        ),

        ErrorFix(
            exception="StaleElementReferenceException",
            pattern="stale element reference",
            cause="Element was found, then DOM was refreshed/updated — reference is now stale",
            fix="Re-fetch the element inside the action, or use a retry wrapper",
            code_before="""element = driver.find_element(By.ID, "btn")
page.load_more()
element.click()  # stale!""",
            code_after="""page.load_more()
# Re-fetch after DOM change
WebDriverWait(driver, 10).until(EC.element_to_be_clickable((By.ID, "btn"))).click()""",
            severity="high",
        ),

        ErrorFix(
            exception="ElementNotInteractableException",
            pattern="element not interactable",
            cause="Element exists but is hidden, disabled, or off-screen",
            fix="Scroll element into view, wait for it to be visible, or use JS click",
            code_before='driver.find_element(By.ID, "submit").click()',
            code_after="""element = WebDriverWait(driver, 10).until(
    EC.element_to_be_clickable((By.ID, "submit"))
)
driver.execute_script("arguments[0].scrollIntoView(true);", element)
element.click()""",
            severity="medium",
        ),

        ErrorFix(
            exception="ElementClickInterceptedException",
            pattern="element click intercepted",
            cause="Another element (overlay, modal, cookie banner) is blocking the click",
            fix="Dismiss the overlay first, or use JS click as fallback",
            code_before='driver.find_element(By.ID, "checkout").click()',
            code_after="""# Option 1: Dismiss overlay if present
try:
    WebDriverWait(driver, 3).until(
        EC.element_to_be_clickable((By.CSS_SELECTOR, ".cookie-accept"))
    ).click()
except TimeoutException:
    pass

# Option 2: JS click fallback
element = WebDriverWait(driver, 10).until(
    EC.presence_of_element_located((By.ID, "checkout"))
)
driver.execute_script("arguments[0].click();", element)""",
            severity="medium",
        ),

        ErrorFix(
            exception="MoveTargetOutOfBoundsException",
            pattern="move target out of bounds",
            cause="Element is outside the current viewport",
            fix="Scroll element into view before hover/click",
            code_before='ActionChains(driver).move_to_element(element).perform()',
            code_after="""driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", element)
ActionChains(driver).move_to_element(element).perform()""",
            severity="low",
        ),

        ErrorFix(
            exception="WebDriverException (session)",
            pattern="invalid session id",
            cause="WebDriver session was closed or crashed",
            fix="Ensure driver.quit() is in teardown, add session check in fixture",
            code_before="""# Missing teardown
def test_login(driver):
    driver.get("https://example.com")""",
            code_after="""@pytest.fixture
def driver():
    d = DriverFactory.create(browser="chrome", headless=True)
    yield d
    d.quit()  # Always called, even on failure""",
            severity="high",
        ),

        ErrorFix(
            exception="ImplicitWaitConflict",
            pattern="implicit wait",
            cause="Mixing implicit and explicit waits causes unpredictable timeouts",
            fix="Remove implicit waits — use only WebDriverWait (explicit) everywhere",
            code_before='driver.implicitly_wait(10)  # conflicts with WebDriverWait',
            code_after="""# Remove implicit wait
# Use explicit wait everywhere:
WebDriverWait(driver, 10).until(EC.visibility_of_element_located(locator))""",
            severity="medium",
        ),

        ErrorFix(
            exception="NoAlertPresentException",
            pattern="no alert",
            cause="Trying to switch to alert before it appears",
            fix="Wait for alert to be present using EC.alert_is_present()",
            code_before='alert = driver.switch_to.alert',
            code_after="""WebDriverWait(driver, 5).until(EC.alert_is_present())
alert = driver.switch_to.alert""",
            severity="low",
        ),

        ErrorFix(
            exception="UnexpectedAlertPresentException",
            pattern="unexpected alert",
            cause="An unexpected JS alert appeared and blocked the driver",
            fix="Handle alert in teardown or dismiss it before continuing",
            code_before="# No alert handling",
            code_after="""try:
    WebDriverWait(driver, 2).until(EC.alert_is_present())
    driver.switch_to.alert.dismiss()
except TimeoutException:
    pass""",
            severity="medium",
        ),
    ]

    @classmethod
    def find_fix(cls, error_output: str) -> ErrorFix | None:
        """
        Search error output for known patterns and return fix.

        Args:
            error_output: Full pytest error/traceback string

        Returns:
            ErrorFix if a known error is found, None otherwise
        """
        lower_output = error_output.lower()
        for error in cls.KNOWN_ERRORS:
            if error.pattern.lower() in lower_output:
                return error
        return None

    @classmethod
    def find_all_fixes(cls, error_output: str) -> list[ErrorFix]:
        """Find ALL matching errors in the output."""
        lower_output = error_output.lower()
        return [e for e in cls.KNOWN_ERRORS if e.pattern.lower() in lower_output]

    @classmethod
    def get_fix_summary(cls, error_output: str) -> str:
        """Return a human-readable fix summary for the Healer Agent prompt."""
        fixes = cls.find_all_fixes(error_output)
        if not fixes:
            return "No known Selenium error pattern matched. LLM analysis required."

        lines = ["KNOWN SELENIUM ERRORS DETECTED:\n"]
        for fix in fixes:
            lines.append(f"❌ {fix.exception}")
            lines.append(f"   Cause: {fix.cause}")
            lines.append(f"   Fix:   {fix.fix}")
            lines.append(f"   Before:\n{fix.code_before}")
            lines.append(f"   After:\n{fix.code_after}\n")

        return "\n".join(lines)

    @classmethod
    def list_all(cls) -> list[str]:
        """Return list of all known exception names."""
        return [e.exception for e in cls.KNOWN_ERRORS]
