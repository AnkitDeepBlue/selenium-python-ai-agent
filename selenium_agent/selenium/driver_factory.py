"""
DRIVER FACTORY
==============
Selenium WebDriver setup utility.
Supports Chrome, Firefox, Edge — with headless, proxy, and common options.

Generated Page Objects should use this for driver setup.

Usage:
    from selenium_agent.selenium.driver_factory import DriverFactory

    driver = DriverFactory.create(browser="chrome", headless=True)
    driver = DriverFactory.create(browser="firefox")
    driver = DriverFactory.create(browser="edge", headless=True)
"""

from __future__ import annotations
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class DriverConfig:
    """Configuration options for WebDriver creation."""
    browser: str = "chrome"           # chrome | firefox | edge
    headless: bool = False            # Run without UI (CI/CD friendly)
    implicit_wait: int = 0            # Seconds (prefer explicit waits)
    page_load_timeout: int = 30       # Seconds before page load timeout
    window_size: tuple = (1920, 1080) # Default window size
    proxy: Optional[str] = None       # e.g. "http://proxy:8080"
    user_agent: Optional[str] = None  # Custom user agent string
    disable_notifications: bool = True
    ignore_certificate_errors: bool = False
    extra_args: list = field(default_factory=list)


class DriverFactory:
    """
    Factory class for creating Selenium WebDriver instances.

    Supports Chrome, Firefox, and Edge with sensible defaults
    for test automation.
    """

    @staticmethod
    def create(
        browser: str = "chrome",
        headless: bool = False,
        implicit_wait: int = 0,
        page_load_timeout: int = 30,
        window_size: tuple = (1920, 1080),
        proxy: Optional[str] = None,
        user_agent: Optional[str] = None,
        disable_notifications: bool = True,
        ignore_certificate_errors: bool = False,
        extra_args: list = None,
    ):
        """
        Create and return a configured WebDriver instance.

        Args:
            browser: Browser to use — 'chrome', 'firefox', or 'edge'
            headless: Run browser without UI (great for CI/CD)
            implicit_wait: Global implicit wait in seconds (0 = disabled)
                          Prefer explicit waits (WebDriverWait) over this.
            page_load_timeout: Max seconds to wait for page load
            window_size: Browser window dimensions (width, height)
            proxy: Proxy server URL e.g. 'http://proxy.example.com:8080'
            user_agent: Custom User-Agent string
            disable_notifications: Block browser notification popups
            ignore_certificate_errors: Ignore SSL/TLS cert errors
            extra_args: Additional browser arguments list

        Returns:
            WebDriver: Configured Selenium WebDriver instance

        Example:
            driver = DriverFactory.create(browser="chrome", headless=True)
            driver = DriverFactory.create(browser="firefox", window_size=(1366, 768))
        """
        config = DriverConfig(
            browser=browser.lower().strip(),
            headless=headless,
            implicit_wait=implicit_wait,
            page_load_timeout=page_load_timeout,
            window_size=window_size,
            proxy=proxy,
            user_agent=user_agent,
            disable_notifications=disable_notifications,
            ignore_certificate_errors=ignore_certificate_errors,
            extra_args=extra_args or [],
        )

        creators = {
            "chrome": DriverFactory._create_chrome,
            "firefox": DriverFactory._create_firefox,
            "edge": DriverFactory._create_edge,
        }

        if config.browser not in creators:
            supported = ", ".join(creators.keys())
            raise ValueError(
                f"Unsupported browser: '{browser}'. Supported: {supported}"
            )

        driver = creators[config.browser](config)

        # Apply timeouts
        driver.set_page_load_timeout(config.page_load_timeout)
        if config.implicit_wait > 0:
            driver.implicitly_wait(config.implicit_wait)

        # Set window size
        driver.set_window_size(*config.window_size)

        return driver

    @staticmethod
    def _create_chrome(config: DriverConfig):
        from selenium import webdriver
        from selenium.webdriver.chrome.service import Service
        from webdriver_manager.chrome import ChromeDriverManager

        options = webdriver.ChromeOptions()

        if config.headless:
            options.add_argument("--headless=new")  # new headless mode (Chrome 112+)

        if config.disable_notifications:
            options.add_argument("--disable-notifications")

        if config.ignore_certificate_errors:
            options.add_argument("--ignore-certificate-errors")

        if config.user_agent:
            options.add_argument(f"--user-agent={config.user_agent}")

        if config.proxy:
            options.add_argument(f"--proxy-server={config.proxy}")

        # Common stability args
        options.add_argument("--no-sandbox")
        options.add_argument("--disable-dev-shm-usage")
        options.add_argument("--disable-blink-features=AutomationControlled")
        options.add_experimental_option("excludeSwitches", ["enable-automation"])
        options.add_experimental_option("useAutomationExtension", False)

        for arg in config.extra_args:
            options.add_argument(arg)

        service = Service(ChromeDriverManager().install())
        return webdriver.Chrome(service=service, options=options)

    @staticmethod
    def _create_firefox(config: DriverConfig):
        from selenium import webdriver
        from selenium.webdriver.firefox.service import Service
        from webdriver_manager.firefox import GeckoDriverManager

        options = webdriver.FirefoxOptions()

        if config.headless:
            options.add_argument("--headless")

        if config.user_agent:
            options.set_preference("general.useragent.override", config.user_agent)

        if config.disable_notifications:
            options.set_preference("dom.webnotifications.enabled", False)

        if config.ignore_certificate_errors:
            options.set_preference("accept_untrusted_certs", True)

        if config.proxy:
            host, port = config.proxy.replace("http://", "").split(":")
            options.set_preference("network.proxy.type", 1)
            options.set_preference("network.proxy.http", host)
            options.set_preference("network.proxy.http_port", int(port))

        for arg in config.extra_args:
            options.add_argument(arg)

        service = Service(GeckoDriverManager().install())
        return webdriver.Firefox(service=service, options=options)

    @staticmethod
    def _create_edge(config: DriverConfig):
        from selenium import webdriver
        from selenium.webdriver.edge.service import Service
        from webdriver_manager.microsoft import EdgeChromiumDriverManager

        options = webdriver.EdgeOptions()

        if config.headless:
            options.add_argument("--headless=new")

        if config.disable_notifications:
            options.add_argument("--disable-notifications")

        if config.ignore_certificate_errors:
            options.add_argument("--ignore-certificate-errors")

        if config.user_agent:
            options.add_argument(f"--user-agent={config.user_agent}")

        if config.proxy:
            options.add_argument(f"--proxy-server={config.proxy}")

        for arg in config.extra_args:
            options.add_argument(arg)

        service = Service(EdgeChromiumDriverManager().install())
        return webdriver.Edge(service=service, options=options)
