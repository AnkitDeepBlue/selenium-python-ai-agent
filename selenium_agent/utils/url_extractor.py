"""
URL EXTRACTOR
=============
Extracts a base URL from user instruction using regex.

Priority:
  1. Full URL in instruction  (https://saucedemo.com/login → https://saucedemo.com/login)
  2. Bare domain pattern      (saucedemo.com → https://www.saucedemo.com)
  3. None                     → caller uses saved base_url or lets LLM decide
"""

import re

# Looks like a real domain: at least one letter segment + known TLD
_DOMAIN_RE = re.compile(
    r'\b([a-zA-Z0-9][a-zA-Z0-9-]*\.[a-zA-Z]{2,})\b'
)

# Things that look like domains but aren't (file extensions, abbreviations)
_FAKE_TLDS = {"py", "js", "ts", "java", "md", "txt", "csv", "json", "xml",
              "html", "css", "yml", "yaml", "sh", "env", "g", "e"}


def extract_url(instruction: str) -> str | None:
    """
    Extract target URL from a natural language instruction.

    Returns the base URL (no trailing path) so it can be saved as base_url.
    """
    # 1. Full URL — return as-is (strip trailing punctuation)
    full = re.search(r'https?://\S+', instruction)
    if full:
        url = full.group(0).rstrip(".,)")
        return _to_base(url)

    # 2. Bare domain like saucedemo.com / myapp.io / staging.company.co.in
    for match in _DOMAIN_RE.finditer(instruction):
        domain = match.group(1).lower()
        tld = domain.rsplit(".", 1)[-1]
        if tld not in _FAKE_TLDS:
            return f"https://www.{domain}"

    return None


def _to_base(url: str) -> str:
    """Strip path — keep scheme + netloc only for use as base_url."""
    from urllib.parse import urlparse
    p = urlparse(url)
    if p.scheme and p.netloc:
        return f"{p.scheme}://{p.netloc}"
    return url
