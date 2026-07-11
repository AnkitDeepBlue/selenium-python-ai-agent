"""
DRIVER FACTORY — WebDriver setup utility.
Supports Chrome, Firefox, Edge with headless, proxy, and common options.

Usage:
    from selenium_agent.selenium.driver_factory import DriverFactory
    driver = DriverFactory.create(browser="chrome", headless=True)
"""

from __future__ import annotations
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class DriverConfig:
    browser: str = "chrome"
    headless: bool = False
    implicit_wait: int = 0
    page_load_timeout: int = 30
    window_size: tuple = (1920, 1080)
    proxy: Optional[str] = None
    user_agent: Optional[str] = None
    disable_notifications: bool = True
    ignore_certificate_errors: bool = False
    extra_args: list = field(default_factory=list)


class DriverFactory:
    """
    Factory for creating Selenium WebDriver instances.

    Primary method : DriverFactory.create(browser, headless, ...)
    Aliases        : DriverFactory.get_driver(...)
                     DriverFactory.get_chrome_driver(...)
                     DriverFactory.get_firefox_driver(...)
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
            browser: 'chrome' | 'firefox' | 'edge' (default: chrome)
            headless: Run without UI — great for CI/CD (default: False)
            implicit_wait: Global implicit wait seconds — prefer 0 + explicit waits
            page_load_timeout: Max seconds to wait for page load (default: 30)
            window_size: (width, height) tuple (default: 1920x1080)
            proxy: Proxy URL e.g. 'http://proxy.example.com:8080'
            user_agent: Custom User-Agent string
            disable_notifications: Block browser popups (default: True)
            ignore_certificate_errors: Ignore SSL errors (default: False)
            extra_args: Additional browser arguments

        Returns:
            Configured WebDriver instance

        Example:
            driver = DriverFactory.create(browser="chrome", headless=True)
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
            "chrome":  DriverFactory._create_chrome,
            "firefox": DriverFactory._create_firefox,
            "edge":    DriverFactory._create_edge,
        }

        if config.browser not in creators:
            raise ValueError(
                f"Unsupported browser: '{browser}'. Supported: {', '.join(creators)}"
            )

        driver = creators[config.browser](config)
        driver.set_page_load_timeout(config.page_load_timeout)
        if config.implicit_wait > 0:
            driver.implicitly_wait(config.implicit_wait)
        # maximize_window is more reliable than set_window_size on Mac/headless
        if config.headless:
            driver.set_window_size(*config.window_size)
        else:
            driver.maximize_window()
        return driver

    # ── Aliases — LLM commonly generates these names ──────────────────

    @staticmethod
    def get_driver(browser: str = "chrome", headless: bool = False, **kwargs):
        """Alias for create(). Use DriverFactory.create() in new code."""
        return DriverFactory.create(browser=browser, headless=headless, **kwargs)

    @staticmethod
    def get_chrome_driver(headless: bool = False, **kwargs):
        """Alias: create Chrome driver directly."""
        return DriverFactory.create(browser="chrome", headless=headless, **kwargs)

    @staticmethod
    def get_firefox_driver(headless: bool = False, **kwargs):
        """Alias: create Firefox driver directly."""
        return DriverFactory.create(browser="firefox", headless=headless, **kwargs)

    @staticmethod
    def get_edge_driver(headless: bool = False, **kwargs):
        """Alias: create Edge driver directly."""
        return DriverFactory.create(browser="edge", headless=headless, **kwargs)

    @staticmethod
    def chrome(headless: bool = False, **kwargs):
        """Alias: DriverFactory.chrome(headless=True)"""
        return DriverFactory.create(browser="chrome", headless=headless, **kwargs)

    @staticmethod
    def firefox(headless: bool = False, **kwargs):
        """Alias: DriverFactory.firefox(headless=True)"""
        return DriverFactory.create(browser="firefox", headless=headless, **kwargs)

    # ── Private browser creators ──────────────────

    @staticmethod
    def _create_chrome(config: DriverConfig):
        from selenium import webdriver
        from selenium.webdriver.chrome.service import Service
        from webdriver_manager.chrome import ChromeDriverManager

        options = webdriver.ChromeOptions()
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

        options.add_argument("--no-sandbox")
        options.add_argument("--disable-dev-shm-usage")
        options.add_argument("--disable-blink-features=AutomationControlled")
        options.add_experimental_option("excludeSwitches", ["enable-automation"])
        options.add_experimental_option("useAutomationExtension", False)
        # Disable password manager / save password / breach popups
        options.add_experimental_option("prefs", {
            "credentials_enable_service": False,
            "profile.password_manager_enabled": False,
            "profile.password_manager_leak_detection": False,
        })

        for arg in config.extra_args:
            options.add_argument(arg)

        return webdriver.Chrome(service=Service(ChromeDriverManager().install()), options=options)

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

        return webdriver.Firefox(service=Service(GeckoDriverManager().install()), options=options)

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

        return webdriver.Edge(service=Service(EdgeChromiumDriverManager().install()), options=options)
