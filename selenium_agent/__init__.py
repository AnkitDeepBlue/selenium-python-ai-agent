"""
Selenium Python AI Agent
========================
A multi-agent framework to plan, code and heal Selenium Python tests using Anthropic or OpenAI.

Usage (Python Library):
    from selenium_agent import SeleniumAgent

    agent = SeleniumAgent(provider="openai", api_key="your-openai-key")
    agent.run("test login page of github.com")

Usage (CLI):
    selenium-agent --provider openai "test login page of github.com" --api-key YOUR_KEY
"""

from selenium_agent.core.orchestrator import Orchestrator as SeleniumAgent

__version__ = "0.1.0"
__author__ = "Ankit Tripathi"
__all__ = ["SeleniumAgent"]
