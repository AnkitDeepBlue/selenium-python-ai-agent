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
# NOTE: the leading `return` is load-bearing — Selenium's execute_script only
# hands the value back to Python if the script body explicitly returns it.
_SCAN_JS = """
return (function () {
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

    // ── Uniqueness helpers — a locator that matches several elements is a trap ──
    function cssCount(sel) {
        try { return document.querySelectorAll(sel).length; } catch (e) { return 0; }
    }
    function xpathCount(xp) {
        try {
            return document.evaluate('count(' + xp + ')', document, null,
                XPathResult.NUMBER_TYPE, null).numberValue;
        } catch (e) { return 0; }
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

        let css   = buildCSS(el);
        let xpath = buildXPath(el);

        const info = {
            tag:         el.tagName.toLowerCase(),
            href:        el.href         || null,
            options:     el.tagName === 'SELECT'
                             ? [...el.options].slice(0, 12)
                                   .map(o => o.textContent.trim()).filter(Boolean)
                             : null,
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

        // ── Uniquify ambiguous selectors by scoping to an ancestor with an id ──
        // e.g. 'input[type="submit"]' matching both a search icon and the real
        // form button becomes '#create_customer input[type="submit"]'.
        if ((css && cssCount(css) > 1) || (xpath && xpathCount(xpath) > 1)) {
            let anc = el.parentElement;
            while (anc && anc.tagName !== 'BODY') {
                if (anc.id) {
                    if (css && cssCount(css) > 1) {
                        const scoped = '#' + anc.id + ' ' + css;
                        if (cssCount(scoped) === 1) { info.css = scoped; css = scoped; }
                    }
                    if (xpath && xpathCount(xpath) > 1 && xpath.indexOf('//') === 0) {
                        const sx = '//*[@id="' + anc.id + '"]//' + xpath.slice(2);
                        if (xpathCount(sx) === 1) { info.xpath = sx; xpath = sx; }
                    }
                    if ((!css || cssCount(css) === 1) && (!xpath || xpathCount(xpath) === 1))
                        break;
                }
                anc = anc.parentElement;
            }
        }

        // Annotate whatever is STILL ambiguous so the LLM never guesses wrong
        if (css) {
            const n = cssCount(css);
            if (n > 1) info.css_matches = n;
        }
        if (xpath) {
            const n = xpathCount(xpath);
            if (n > 1) info.xpath_matches = n;
        }

        const key = (css || '') + '|' + (xpath || '');
        if (key !== '|' && !seen.has(key)) {
            seen.add(key);
            results.push(info);
        }
    });

    // ── Text-bearing leaf elements (labels, displayed values, messages) ──
    // Workflows often need to READ text from the page ("grab the username
    // shown in the credentials section"). Capture a bounded set of short
    // leaf text elements so the LLM has real locators for them too.
    const TEXTY = 'p, span, label, h1, h2, h3, h4, h5, h6, td, th, li, code, pre, strong, b, div[id]';
    let textCount = 0;
    document.querySelectorAll(TEXTY).forEach(function (el) {
        if (textCount >= 30) return;
        if (el.children.length !== 0) return;
        const txt = (el.textContent || '').trim();
        if (txt.length < 3 || txt.length > 80) return;
        const rect = el.getBoundingClientRect();
        if (rect.width === 0 && rect.height === 0) return;

        const tag = el.tagName.toLowerCase();
        let css = null;
        if (el.getAttribute('data-test'))
            css = '[data-test="' + el.getAttribute('data-test') + '"]';
        else if (el.getAttribute('data-testid'))
            css = '[data-testid="' + el.getAttribute('data-testid') + '"]';
        else if (el.id)
            css = '#' + el.id;
        else if (typeof el.className === 'string' && el.className.trim())
            css = tag + '.' + el.className.trim().split(/\\s+/).slice(0, 2).join('.');

        // A CSS that matches several elements is worse than none —
        // reading text through it silently returns the WRONG element.
        if (css && cssCount(css) !== 1) css = null;

        let xpath = null;
        if (txt.indexOf('"') === -1) {
            // "LABEL: value" pattern → anchor on the stable label part so the
            // locator survives when the value changes (status badges, etc.)
            const colon = txt.indexOf(':');
            if (colon > 0 && colon < 40) {
                const prefixXp = '//' + tag + '[contains(normalize-space(), "'
                                 + txt.slice(0, colon + 1) + '")]';
                if (xpathCount(prefixXp) === 1) xpath = prefixXp;
            }
            if (!xpath) {
                const exactXp = '//' + tag + '[normalize-space()="' + txt + '"]';
                if (xpathCount(exactXp) === 1) xpath = exactXp;
            }
        }

        if (!css && !xpath) return;
        const key = 'txt|' + (css || '') + '|' + txt;
        if (seen.has(key)) return;
        seen.add(key);
        textCount++;
        results.push({
            tag: tag, kind: 'text', href: null, type: null,
            id: el.id || null, name: null, placeholder: null,
            text: txt.slice(0, 60),
            data_test: el.getAttribute('data-test') || null,
            data_testid: el.getAttribute('data-testid') || null,
            data_cy: null, aria_label: null,
            css: css, xpath: xpath,
        });
    });

    // ── Bot-protection detection ──
    // A captcha (hCaptcha/reCAPTCHA/Turnstile) means automated flows that
    // trigger it CANNOT pass — agents must report this instead of endlessly
    // "fixing" locators.
    if (document.querySelector(
            'iframe[src*="hcaptcha"], iframe[src*="recaptcha"], ' +
            'iframe[src*="turnstile"], [data-sitekey]')) {
        results.push({
            tag: 'iframe', kind: 'captcha', href: null, type: null,
            id: null, name: null, placeholder: null,
            text: 'CAPTCHA / bot protection active on this page',
            data_test: null, data_testid: null, data_cy: null,
            aria_label: null, css: null, xpath: null,
        });
    }

    return results;
})();
"""


def scan_page_locators(url: str, headless: bool = True, max_wait: int = 25) -> list[dict]:
    """
    Open browser, navigate to url, scan DOM, return elements with real CSS + XPath.

    SPA-aware: client-side apps (React/Vue/Angular) render the form long after
    document.readyState is 'complete' — some behind boot animations where
    elements exist in the DOM but are still zero-sized. So instead of one shot,
    the scan JS is POLLED every second until visible interactive elements
    appear (up to max_wait seconds).

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
        import time

        # Wait for full page load
        WebDriverWait(driver, 10).until(
            lambda d: d.execute_script("return document.readyState") == "complete"
        )

        # Wait for redirect to settle — URL stops changing
        initial_url = driver.current_url
        time.sleep(1.5)
        final_url = driver.current_url
        if final_url != initial_url:
            logger.info(f"🔄 Redirected to: {final_url}")
            WebDriverWait(driver, 10).until(
                lambda d: d.execute_script("return document.readyState") == "complete"
            )

        # Poll until VISIBLE interactive elements render (SPA hydration,
        # boot animations, lazy data fetches)
        deadline = time.time() + max_wait
        elements: list[dict] = []
        while time.time() < deadline:
            elements = driver.execute_script(_SCAN_JS) or []
            if elements:
                # settle pass — catch elements that render moments later
                time.sleep(1.0)
                more = driver.execute_script(_SCAN_JS) or []
                if len(more) > len(elements):
                    elements = more
                break
            time.sleep(1.0)

        if not elements:
            logger.warning(f"⚠️  No visible interactive elements after {max_wait}s on: {driver.current_url}")
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


def rank_links_by_relevance(links: list[dict], instruction: str) -> list[str]:
    """
    Order candidate links so the ones RELEVANT to the instruction come first.

    Exploring the first N links in document order wastes the budget on nav
    noise (search, about-us, ...) while the page the flow actually needs
    (e.g. /account/register for a sign-up instruction) is never scanned.
    Scores each link by how many instruction words appear in its visible
    text or href; ties keep document order.

    links: [{"href": ..., "text": ...}]  →  ordered list of hrefs
    """
    import re

    stop = {"the", "and", "for", "with", "then", "that", "this", "page",
            "open", "click", "verify", "form", "button", "link", "fill",
            "random", "generated", "runtime", "unique", "finally", "was"}
    tokens = {
        w for w in re.findall(r"[a-z]+", instruction.lower())
        if len(w) >= 3 and w not in stop
    }

    def score(link: dict) -> int:
        haystack = f"{link.get('text') or ''} {link.get('href') or ''}".lower()
        return sum(1 for t in tokens if t in haystack)

    ranked = sorted(
        enumerate(links),
        key=lambda pair: (-score(pair[1]), pair[0]),
    )
    return [link.get("href") for _, link in ranked]


def scan_site_locators(
    url: str,
    headless: bool = True,
    max_extra_pages: int = 3,
    instruction: str = "",
) -> dict[str, list[dict]]:
    """
    Bounded same-origin exploration (Playwright-planner style):
    scan the target URL, then follow up to `max_extra_pages` same-origin
    links discovered on it and scan those pages too. When an instruction
    is given, links relevant to it are explored first.

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

    def collect_links(page_elements: list[dict]) -> list[dict]:
        found = []
        for el in page_elements:
            href = el.get("href") or ""
            if not href.startswith("http"):
                continue
            clean = href.split("#")[0].rstrip("/")
            if urlparse(href).netloc == origin and clean and clean not in seen:
                seen.add(clean)
                found.append({"href": clean, "text": el.get("text") or ""})
        return found

    # Multi-hop, relevance-first exploration: links discovered on explored
    # pages join the pool, so a page one hop deeper (e.g. a register form
    # linked only from the login page) is still reachable within budget.
    pool = collect_links(elements)
    for _ in range(max_extra_pages):
        if not pool:
            break
        if instruction:
            best = rank_links_by_relevance(pool, instruction)[0]
        else:
            best = pool[0]["href"]
        pool = [c for c in pool if c["href"] != best]

        logger.info(f"🧭 Exploring same-origin page: {best}")
        extra_elements = scan_page_locators(best, headless=headless)
        if extra_elements:
            results[best] = extra_elements
            pool.extend(collect_links(extra_elements))

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

    if any(el.get("kind") == "captcha" for el in elements):
        lines += [
            "🚫 CAPTCHA / BOT PROTECTION IS ACTIVE ON THIS PAGE.",
            "   Flows that trigger it (form submits, logins, sign-ups) CANNOT pass",
            "   with automation and MUST NOT be bypassed. Do not keep fixing",
            "   locators — report this as the root cause instead.",
            "",
        ]

    for el in elements:
        if el.get("kind") == "captcha":
            continue
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
            if el.get("css_matches"):
                line += f"  ⚠️ NOT UNIQUE (matches {el['css_matches']} elements — use XPATH)"
        if xpath:
            line += f"  |  XPATH → By.XPATH, '{xpath}'"
            if el.get("xpath_matches"):
                line += f"  ⚠️ NOT UNIQUE (matches {el['xpath_matches']} elements)"
        if el.get("options"):
            line += (f"  OPTIONS(sample): {el['options'][:8]}"
                     f"{' …' if len(el['options']) > 8 else ''}"
                     f" ← use option text EXACTLY as listed")
        lines.append(line)

    lines += [
        "",
        "RULES:",
        "  • Prefer CSS over XPath — but NEVER use a CSS marked NOT UNIQUE",
        "    for a single element (it silently returns the WRONG element);",
        "    use that element's XPATH instead",
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
