"""Usage examples for the stealth-browser library.

Run as a regular CONSUMER of the installed package, not from the library
directory:

    uv pip install <path-to-browser>     # or: pip install stealth-browser
    python example.py

Imports here are absolute (`from browser...`); the package comes from the
environment. The profile and extensions directories are paths owned by the
consumer; the library never writes into its own directory. When no profile is
set, the browser uses a directory in the system temp and removes it on close.
"""

from __future__ import annotations

import asyncio
from pathlib import Path

from browser import BrowserConfig, BrowserManager

# Data directories are chosen by the consumer — intentionally OUTSIDE the library package.
DATA_DIR = Path.home() / ".cache" / "stealth-browser-demo"


async def temporary_profile() -> None:
    """Temporary profile (default behavior).

    With ``user_data_dir=None`` the manager creates a profile in the system
    temp (``tempfile.mkdtemp``) and removes it on close — nothing is left on
    disk and nothing is written into the library directory.
    """
    async with BrowserManager(BrowserConfig()) as browser:
        await browser.page.goto("https://example.com", wait_until="domcontentloaded")
        print(await browser.page.title())


async def persistent_profile() -> None:
    """Persistent profile: cookies/storage persist between runs.

    The path is chosen by the consumer. Here it is under ``~/.cache`` to avoid
    cluttering either the library directory or the current working directory.
    """
    config = BrowserConfig(user_data_dir=DATA_DIR / "profile")
    async with BrowserManager(config) as browser:
        await browser.page.goto("https://example.com", wait_until="domcontentloaded")
        print(await browser.page.title())


async def with_extensions_and_custom_blocking() -> None:
    """Extensions from the consumer's directory + analytics-domain blocking.

    Extensions are not bundled with the library: ``extensions_dir`` points to a
    directory of unpacked extensions (each in its own subfolder). When the
    directory is not set, the browser starts without extensions.
    """
    config = BrowserConfig(
        extensions_dir=DATA_DIR / "extensions",
        blocked_domains=("google-analytics.com", "mc.yandex.ru"),
    )
    async with BrowserManager(config, logger_name="demo") as browser:
        await browser.page.goto("https://example.com", wait_until="domcontentloaded")


if __name__ == "__main__":
    asyncio.run(temporary_profile())
