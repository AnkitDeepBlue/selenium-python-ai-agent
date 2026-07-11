"""
BASE PAGE — Base class for all generated Page Objects.
Includes fluent waits, smart conditional waits, and method aliases.
"""

from __future__ import annotations
import os
from datetime import datetime

from selenium.webdriver.common.action_chains import ActionChains
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.remote.webdriver import WebDriver
from selenium.webdriver.remote.webelement import WebElement
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait, Select
from selenium.webdriver.support.wait import WebDriverWait as FluentWebDriverWait
from selenium.common.exceptions import (
    TimeoutException,
    NoSuchElementException,
    StaleElementReferenceException,
    ElementClickInterceptedException,
)

Locator = tuple[str, str]


_EDITABLE_TAGS = {"input", "textarea", "select"}


def _normalize_locator(locator) -> Locator:
    """
    Accept ('css selector', '#x') tuples AND bare selector strings.

    LLM-generated fixes occasionally pass a raw string where a locator tuple
    is expected; Selenium then unpacks the string character-by-character into
    find_element(*locator) and crashes with a bizarre arity error. Treat a
    bare string as a CSS selector (or XPath when it looks like one).
    """
    if isinstance(locator, str):
        from selenium.webdriver.common.by import By
        if locator.startswith(("/", "(", "./")):
            return (By.XPATH, locator)
        return (By.CSS_SELECTOR, locator)
    return locator


def _first_usable_element(locator: Locator, require_enabled: bool = False,
                          prefer_editable: bool = False):
    """
    Expected condition: the first DISPLAYED (optionally enabled) element
    matching the locator.

    Real pages often contain duplicate matches for one selector — a desktop
    form plus an off-canvas mobile drawer with the SAME element ids, or a
    wrapper element sharing its id with the input nested inside it.
    Selenium's stock conditions grab the first DOM match, which may be the
    hidden twin or the non-editable wrapper, causing
    ElementNotInteractable/InvalidElementState exceptions. This condition
    considers every match and prefers, in order:
      1. an editable form control (when prefer_editable — for type/clear)
      2. an element laid out inside the viewport
    """
    locator = _normalize_locator(locator)

    def _condition(driver):
        candidates = []
        for el in driver.find_elements(*locator):
            try:
                if el.is_displayed() and (not require_enabled or el.is_enabled()):
                    candidates.append(el)
            except StaleElementReferenceException:
                continue
        if not candidates:
            return False

        if prefer_editable and len(candidates) > 1:
            editable = []
            for el in candidates:
                try:
                    if el.tag_name.lower() in _EDITABLE_TAGS or \
                            el.get_attribute("contenteditable") == "true":
                        editable.append(el)
                except StaleElementReferenceException:
                    continue
            if editable:
                candidates = editable

        if len(candidates) == 1:
            return candidates[0]
        try:
            viewport_width = driver.execute_script("return window.innerWidth") or 0
            for el in candidates:
                rect = el.rect
                if 0 <= rect.get("x", -1) < viewport_width:
                    return el
        except Exception:
            pass
        return candidates[0]
    return _condition


class BasePage:
    def __init__(self, driver: WebDriver, timeout: int = 10):
        self.driver = driver
        self.timeout = timeout
        self.wait = WebDriverWait(driver, timeout)

    # ── Navigation ────────────────────────────────

    def open(self, url: str) -> "BasePage":
        self.driver.get(url)
        return self

    def get_title(self) -> str:
        return self.driver.title

    def get_url(self) -> str:
        return self.driver.current_url

    def refresh(self) -> "BasePage":
        self.driver.refresh()
        return self

    def go_back(self) -> "BasePage":
        self.driver.back()
        return self

    # ── Finding Elements ──────────────────────────

    def find(self, locator: Locator, timeout: int = None) -> WebElement:
        wait = WebDriverWait(self.driver, timeout or self.timeout)
        return wait.until(_first_usable_element(locator))

    def find_clickable(self, locator: Locator, timeout: int = None) -> WebElement:
        wait = WebDriverWait(self.driver, timeout or self.timeout)
        return wait.until(_first_usable_element(locator, require_enabled=True))

    def find_present(self, locator: Locator, timeout: int = None) -> WebElement:
        """Find element in DOM even if not visible (e.g. hidden inputs)."""
        locator = _normalize_locator(locator)
        wait = WebDriverWait(self.driver, timeout or self.timeout)
        return wait.until(EC.presence_of_element_located(locator))

    def find_editable(self, locator: Locator, timeout: int = None) -> WebElement:
        """Find the editable form control for a locator — when a selector also
        matches a wrapper/label twin, this picks the input/textarea/select."""
        wait = WebDriverWait(self.driver, timeout or self.timeout)
        return wait.until(_first_usable_element(
            locator, require_enabled=True, prefer_editable=True))

    def find_all(self, locator: Locator, timeout: int = None) -> list[WebElement]:
        locator = _normalize_locator(locator)
        wait = WebDriverWait(self.driver, timeout or self.timeout)
        wait.until(EC.presence_of_all_elements_located(locator))
        return self.driver.find_elements(*locator)

    def is_visible(self, locator: Locator, timeout: int = 3) -> bool:
        locator = _normalize_locator(locator)
        try:
            WebDriverWait(self.driver, timeout).until(EC.visibility_of_element_located(locator))
            return True
        except (TimeoutException, NoSuchElementException):
            return False

    def is_present(self, locator: Locator, timeout: int = 3) -> bool:
        locator = _normalize_locator(locator)
        try:
            WebDriverWait(self.driver, timeout).until(EC.presence_of_element_located(locator))
            return True
        except (TimeoutException, NoSuchElementException):
            return False

    # ── Interactions ──────────────────────────────

    def click(self, locator: Locator, timeout: int = None) -> "BasePage":
        element = self.find_clickable(locator, timeout)
        try:
            element.click()
        except ElementClickInterceptedException:
            self.driver.execute_script("arguments[0].click();", element)
        return self

    def safe_type(self, locator: Locator, text: str) -> "BasePage":
        """
        Type text with auto JS fallback.
        1. Regular click + type
        2. Verify value was actually entered
        3. If empty → JS inject + React event dispatch
        4. Assert value present before continuing
        """
        import time
        self.type(locator, text)
        time.sleep(0.3)

        el = self.find_editable(locator)
        actual = el.get_attribute("value") or ""
        if actual.strip() == text.strip():
            return self

        # JS fallback — pass text as an argument so quotes/newlines can't break the script
        self.execute_js("arguments[0].value = arguments[1];", el, text)
        self.execute_js("arguments[0].dispatchEvent(new Event('input', { bubbles: true }));", el)
        self.execute_js("arguments[0].dispatchEvent(new Event('change', { bubbles: true }));", el)
        time.sleep(0.2)

        actual = self.find_editable(locator).get_attribute("value") or ""
        assert actual.strip() == text.strip(), \
            f"Field empty after JS inject! expected='{text}', got='{actual}'"
        return self

    def type(self, locator: Locator, text: str, clear_first: bool = True) -> "BasePage":
        element = self.find_editable(locator)
        element.click()  # click first — required for React/SPA forms
        if clear_first:
            element.clear()
        element.send_keys(text)
        return self

    def clear(self, locator: Locator) -> "BasePage":
        element = self.find_editable(locator)
        element.send_keys(Keys.CONTROL + "a")
        element.send_keys(Keys.DELETE)
        return self

    def submit(self, locator: Locator) -> "BasePage":
        self.find_editable(locator).send_keys(Keys.RETURN)
        return self

    def select_by_text(self, locator: Locator, text: str) -> "BasePage":
        select = Select(self.find_editable(locator))
        try:
            select.select_by_visible_text(text)
        except NoSuchElementException:
            # Option labels rarely match test data verbatim ("United States"
            # vs "United States of America (the)") — fall back to the first
            # option containing the requested text, case-insensitively.
            wanted = text.strip().lower()
            for option in select.options:
                label = (option.text or "").strip()
                if wanted in label.lower():
                    select.select_by_visible_text(label)
                    break
            else:
                raise
        return self

    def select_by_value(self, locator: Locator, value: str) -> "BasePage":
        Select(self.find_editable(locator)).select_by_value(value)
        return self

    def select_by_index(self, locator: Locator, index: int) -> "BasePage":
        Select(self.find_editable(locator)).select_by_index(index)
        return self

    # ── Getting Values ────────────────────────────

    def get_text(self, locator: Locator) -> str:
        return self.find(locator).text

    def get_value(self, locator: Locator) -> str:
        return self.find_editable(locator).get_attribute("value") or ""

    def get_attribute(self, locator: Locator, attribute: str) -> str:
        return self.find(locator).get_attribute(attribute) or ""

    def is_checked(self, locator: Locator) -> bool:
        return self.find(locator).is_selected()

    def is_enabled(self, locator: Locator) -> bool:
        return self.find(locator).is_enabled()

    # ── Smart Fluent Waits ────────────────────────
    #
    # fluent_wait() is the PREFERRED wait method.
    # It retries every `poll` seconds, ignoring transient DOM exceptions
    # (NoSuchElement, StaleElement) — much more robust than plain WebDriverWait.
    #
    # Use condition=:
    #   'visible'   → element rendered and visible         (DEFAULT)
    #   'present'   → element in DOM, may be hidden
    #   'clickable' → visible + enabled (use before clicks)
    #   'invisible' → element gone/hidden (use after loaders)
    #
    # Examples:
    #   self.fluent_wait((By.CSS_SELECTOR, '[data-test="login-button"]'), 'clickable')
    #   self.fluent_wait((By.ID, 'username'), 'visible')
    #   self.fluent_wait((By.XPATH, '//div[@class="loader"]'), 'invisible', timeout=15)

    def fluent_wait(
        self,
        locator: Locator,
        condition: str = "visible",
        timeout: int = None,
        poll: float = 0.5,
    ) -> WebElement:
        locator = _normalize_locator(locator)
        _timeout = timeout or self.timeout
        wait = FluentWebDriverWait(
            self.driver,
            _timeout,
            poll_frequency=poll,
            ignored_exceptions=[NoSuchElementException, StaleElementReferenceException],
        )
        _cond_map = {
            "visible":   _first_usable_element(locator),
            "present":   EC.presence_of_element_located(locator),
            "clickable": _first_usable_element(locator, require_enabled=True),
            "invisible": EC.invisibility_of_element_located(locator),
        }
        return wait.until(_cond_map.get(condition, _cond_map["visible"]))

    # ── Standard Waits ───────────────────────────

    def wait_for_url(self, url_contains: str, timeout: int = None) -> "BasePage":
        WebDriverWait(self.driver, timeout or self.timeout).until(EC.url_contains(url_contains))
        return self

    def wait_for_title(self, title_contains: str, timeout: int = None) -> "BasePage":
        WebDriverWait(self.driver, timeout or self.timeout).until(EC.title_contains(title_contains))
        return self

    def wait_for_invisible(self, locator: Locator, timeout: int = None) -> "BasePage":
        locator = _normalize_locator(locator)
        WebDriverWait(self.driver, timeout or self.timeout).until(
            EC.invisibility_of_element_located(locator))
        return self

    def wait_for_text(self, locator: Locator, text: str, timeout: int = None) -> "BasePage":
        locator = _normalize_locator(locator)
        WebDriverWait(self.driver, timeout or self.timeout).until(
            EC.text_to_be_present_in_element(locator, text))
        return self

    # ── Scrolling & Hover ─────────────────────────

    def scroll_to(self, locator: Locator) -> "BasePage":
        self.driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", self.find(locator))
        return self

    def scroll_to_top(self) -> "BasePage":
        self.driver.execute_script("window.scrollTo(0, 0);")
        return self

    def scroll_to_bottom(self) -> "BasePage":
        self.driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
        return self

    def hover(self, locator: Locator) -> "BasePage":
        ActionChains(self.driver).move_to_element(self.find(locator)).perform()
        return self

    def drag_and_drop(self, source: Locator, target: Locator) -> "BasePage":
        ActionChains(self.driver).drag_and_drop(self.find(source), self.find(target)).perform()
        return self

    # ── Alerts & Frames ───────────────────────────

    def accept_alert(self, timeout: int = 5) -> str:
        WebDriverWait(self.driver, timeout).until(EC.alert_is_present())
        alert = self.driver.switch_to.alert
        text = alert.text
        alert.accept()
        return text

    def dismiss_alert(self, timeout: int = 5) -> str:
        WebDriverWait(self.driver, timeout).until(EC.alert_is_present())
        alert = self.driver.switch_to.alert
        text = alert.text
        alert.dismiss()
        return text

    def switch_to_frame(self, locator: Locator) -> "BasePage":
        self.driver.switch_to.frame(self.find(locator))
        return self

    def switch_to_default(self) -> "BasePage":
        self.driver.switch_to.default_content()
        return self

    # ── Screenshots ───────────────────────────────

    def screenshot(self, filename: str = None) -> str:
        os.makedirs("screenshots", exist_ok=True)
        if not filename:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"screenshots/screenshot_{timestamp}.png"
        self.driver.save_screenshot(filename)
        return filename

    def screenshot_on_failure(self, test_name: str) -> str:
        return self.screenshot(f"screenshots/FAILED_{test_name}.png")

    def get_page_source(self) -> str:
        return self.driver.page_source

    def execute_js(self, script: str, *args) -> object:
        return self.driver.execute_script(script, *args)

    # ── Window & Tab ──────────────────────────────

    def switch_to_new_window(self) -> "BasePage":
        WebDriverWait(self.driver, self.timeout).until(EC.number_of_windows_to_be(2))
        self.driver.switch_to.window(self.driver.window_handles[-1])
        return self

    def close_current_window(self) -> "BasePage":
        self.driver.close()
        self.driver.switch_to.window(self.driver.window_handles[0])
        return self

    # ── Aliases ───────────────────────────────────

    def wait_for_element_to_be_visible(self, locator: Locator, timeout: int = None) -> WebElement:
        return self.find(locator, timeout)

    def wait_for_element_to_be_clickable(self, locator: Locator, timeout: int = None) -> WebElement:
        return self.find_clickable(locator, timeout)

    def wait_for_element_present(self, locator: Locator, timeout: int = None) -> WebElement:
        return self.find(locator, timeout)

    def get_element(self, locator: Locator, timeout: int = None) -> WebElement:
        return self.find(locator, timeout)

    def send_keys(self, locator: Locator, text: str) -> "BasePage":
        return self.type(locator, text)

    def input_text(self, locator: Locator, text: str) -> "BasePage":
        return self.type(locator, text)

    def enter_text(self, locator: Locator, text: str) -> "BasePage":
        return self.type(locator, text)

    def click_element(self, locator: Locator) -> "BasePage":
        return self.click(locator)

    def is_element_visible(self, locator: Locator, timeout: int = 3) -> bool:
        return self.is_visible(locator, timeout)

    def is_element_present(self, locator: Locator, timeout: int = 3) -> bool:
        return self.is_present(locator, timeout)

    def get_element_text(self, locator: Locator) -> str:
        return self.get_text(locator)

    def navigate_to(self, url: str) -> "BasePage":
        return self.open(url)
