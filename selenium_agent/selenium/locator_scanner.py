"""
LOCATOR SCANNER
===============
Opens a real browser, scans the page DOM, and returns BOTH CSS and XPath
for every interactive element — so LLM never has to guess.

CSS  → preferred (faster, readable)
XPath → fallback (when CSS not expressive enough)
"""

from selenium_agent.utils.logger import setup_logger

logger = setup_logger("LocatorScanner")

# ── JS: scan every interactive element → CSS + XPath ──────────────────────────
_SCAN_JS = """
(function () {
    // ── XPath builder (relative, attribute-based — never absolute) ────────────
    function buildXPath(el) {
        const tag = el.tagName.toLowerCase();

        if (el.getAttribute('data-test'))
            return '//' + tag + '[@data-test="' + el.getAttribute('data-test') + '"]';
        if (el.getAttribute('data-testid'))
            return '//' + tag + '[@data-testid="' + el.getAttribute('data-testid') + '"]';
        if (el.getAttribute('data-cy'))
            return '//' + tag + '[@data-cy="' + el.getAttribute('data-cy') + '"]';
        if (el.id)
            return '//' + tag + '[@id="' + el.id + '"]';
        if (el.name)
            return '//' + tag + '[@name="' + el.name + '"]';
        if (el.getAttribute('aria-label'))
            return '//' + tag + '[@aria-label="' + el.getAttribute('aria-label') + '"]';

        const txt = (el.innerText || el.value || '').trim().slice(0, 40);
        if (txt && (tag === 'button' || tag === 'a'))
            return '//' + tag + '[normalize-space()="' + txt + '"]';

        if (el.placeholder)
            return '//' + tag + '[@placeholder="' + el.placeholder + '"]';

        // Last resort: type attribute
        if (el.type)
            return '//' + tag + '[@type="' + el.type + '"]';

        return null;
    }

    // ── CSS builder (priority: data-test > id > name > placeholder > type) ────
    function buildCSS(el) {
        const tag = el.tagName.toLowerCase();

        if (el.getAttribute('data-test'))
            return '[data-test="' + el.getAttribute('data-test') + '"]';
        if (el.getAttribute('data-testid'))
            return '[data-testid="' + el.getAttribute('data-testid') + '"]';
        if (el.getAttribute('data-cy'))
            return '[data-cy="' + el.getAttribute('data-cy') + '"]';
        if (el.id)
            return '#' + el.id;
        if (el.name)
            return tag + '[name="' + el.name + '"]';
        if (el.placeholder)
            return tag + '[placeholder="' + el.placeholder + '"]';
        if (el.type && el.type !== 'text')
            return tag + '[type="' + el.type + '"]';

        return null;
    }

    const INTERACTIVE = [
        'input', 'button', 'a[href]', 'select', 'textarea',
        '[role="button"]', '[role="link"]', '[role="textbox"]',
        '[role="checkbox"]', '[role="radio"]', '[type="submit"]'
    ].join(',');

    const results = [];
    const seen = new Set();

    document.querySelectorAll(INTERACTIVE).forEach(function (el) {
        // Skip hidden elements
        const rect = el.getBoundingClientRect();
        if (rect.width === 0 && rect.height === 0) return;

        const css   = buildCSS(el);
        const xpath = buildXPath(el);

        const info = {
            tag:         el.tagName.toLowerCase(),
            href:        el.href         || null,
            type:        el.type         || null,
            id:          el.id           || null,
            name:        el.name         || null,
            placeholder: el.placeholder  || null,
            text:        (el.innerText   || el.value || '').trim().slice(0, 60) || null,
            data_test:   el.getAttribute('data-test')   || null,
            data_testid: el.getAttribute('data-testid') || null,
            data_cy:     el.getAttribute('data-cy')     || null,
            aria_label:  el.getAttribute('aria-label')  || null,
            css:         css,
            xpath:       xpath,
        };

        const key = (css || '') + '|' + (xpath || '');
        if (key !== '|' && !seen.has(key)) {
            seen.add(key);
            results.push(info);
        }
    });

    return results;
})();
"""


def scan_page_locators(url: str, headless: bool = True) -> list[dict]:
    """
    Open browser, navigate to url, scan DOM, return elements with real CSS + XPath.
    Returns [] on any failure — callers handle gracefully.
    """
    try:
        from selenium_agent.selenium.driver_factory import DriverFactory
        driver = DriverFactory.create(browser="chrome", headless=headless)
    except Exception as e:
        logger.warning(f"⚠️  Browser launch failed for scan: {e}")
        return []

    try:
        logger.info(f"🔍 Scanning DOM: {url}")
        driver.get(url)

        from selenium.webdriver.support.ui import WebDriverWait
        from selenium.webdriver.support import expected_conditions as EC
        from selenium.webdriver.common.by import By

        # Wait for full page load
        WebDriverWait(driver, 10).until(
            lambda d: d.execute_script("return document.readyState") == "complete"
        )

        # Wait for redirect to settle — URL stops changing
        initial_url = driver.current_url
        import time
        time.sleep(1.5)
        final_url = driver.current_url
        if final_url != initial_url:
            logger.info(f"🔄 Redirected to: {final_url}")
            WebDriverWait(driver, 10).until(
                lambda d: d.execute_script("return document.readyState") == "complete"
            )
            time.sleep(1)  # extra wait for React to render after redirect

        # Wait for at least one interactive element (React may need extra time)
        try:
            WebDriverWait(driver, 12).until(
                EC.presence_of_element_located((By.CSS_SELECTOR,
                    "input, button, a[href], [role='button'], [type='submit']"))
            )
            import time as _t; _t.sleep(1)  # let remaining React elements render
        except Exception:
            pass

        elements = driver.execute_script(_SCAN_JS) or []
        logger.info(f"✅ {len(elements)} interactive elements found on: {driver.current_url}")
        return elements

    except Exception as e:
        logger.warning(f"⚠️  DOM scan failed: {e}")
        return []

    finally:
        try:
            driver.quit()
        except Exception:
            pass


def scan_site_locators(
    url: str,
    headless: bool = True,
    max_extra_pages: int = 3,
) -> dict[str, list[dict]]:
    """
    Bounded same-origin exploration (Playwright-planner style):
    scan the target URL, then follow up to `max_extra_pages` same-origin
    links discovered on it and scan those pages too.

    Returns {page_url: [elements]} — the target URL is always first.
    Pages behind auth simply return whatever the redirect target renders.
    """
    from urllib.parse import urlparse

    results: dict[str, list[dict]] = {}
    elements = scan_page_locators(url, headless=headless)
    results[url] = elements
    if not elements or max_extra_pages <= 0:
        return results

    origin = urlparse(url).netloc
    seen = {url.rstrip("/"), url.rstrip("/") + "/"}
    candidates = []
    for el in elements:
        href = el.get("href") or ""
        if not href.startswith("http"):
            continue
        parsed = urlparse(href)
        clean = href.split("#")[0].rstrip("/")
        if parsed.netloc == origin and clean and clean not in seen:
            seen.add(clean)
            candidates.append(clean)

    for extra_url in candidates[:max_extra_pages]:
        logger.info(f"🧭 Exploring same-origin page: {extra_url}")
        extra_elements = scan_page_locators(extra_url, headless=headless)
        if extra_elements:
            results[extra_url] = extra_elements

    return results


def format_site_for_llm(site: dict[str, list[dict]], context: str = "general") -> str:
    """Format multi-page scan results, one labeled block per page."""
    blocks = []
    for page_url, elements in site.items():
        if not elements:
            continue
        block = format_for_llm(elements, context=context)
        blocks.append(f"═══ PAGE: {page_url} ═══\n{block}")
    return "\n\n".join(blocks)


def format_for_llm(elements: list[dict], context: str = "general") -> str:
    """
    Format scanned elements into a clear prompt block for LLM.
    context: 'planning' | 'healing' | 'general'
    """
    if not elements:
        return ""

    header = {
        "planning": "🔍 REAL DOM LOCATORS — scanned before generating plan. Use ONLY these:",
        "healing":  "🔍 REAL DOM LOCATORS — re-scanned from live page. Fix failed locators using these:",
        "general":  "🔍 REAL DOM LOCATORS (from actual browser scan):",
    }.get(context, "🔍 REAL DOM LOCATORS:")

    lines = [header, ""]
    for el in elements:
        label = (
            el.get("placeholder") or
            el.get("text") or
            el.get("aria_label") or
            el.get("data_test") or
            el.get("id") or
            el.get("name") or
            f"<{el['tag']}>"
        )
        css   = el.get("css")
        xpath = el.get("xpath")

        line = f"  [{label[:40]}]"
        if css:
            line += f"  CSS  → By.CSS_SELECTOR, '{css}'"
        if xpath:
            line += f"  |  XPATH → By.XPATH, '{xpath}'"
        lines.append(line)

    lines += [
        "",
        "RULES:",
        "  • Prefer CSS over XPath",
        "  • Use XPath only when CSS cannot express the condition",
        "  • NEVER invent locators not listed above",
        "",
    ]
    return "\n".join(lines)


def extract_failed_locator_value(pytest_output: str) -> str | None:
    """
    Parse pytest output and extract the locator value that caused
    NoSuchElementException or TimeoutException.
    """
    import re
    patterns = [
        r'Message:\s*Unable to locate element:\s*["{]?([^"}\n]+)',
        r'NoSuchElementException.*?["\']([^"\']+)["\']',
        r'TimeoutException.*?["\']([^"\']+)["\']',
        r'find_element.*?["\']([^"\']+)["\']',
    ]
    for pattern in patterns:
        m = re.search(pattern, pytest_output, re.IGNORECASE | re.DOTALL)
        if m:
            return m.group(1).strip()
    return None
