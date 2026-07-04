"""stealth-browser - an anti-detect browser built on Patchright.

Public API:
    from stealth_browser import BrowserConfig, BrowserManager
"""

from __future__ import annotations

from importlib.metadata import PackageNotFoundError, version

from .config import BrowserConfig
from .manager import BrowserManager

try:
    __version__ = version("stealth-browser")
except PackageNotFoundError:  # package not installed (running from source)
    __version__ = "0.0.0+unknown"

__all__ = ["BrowserConfig", "BrowserManager", "__version__"]
