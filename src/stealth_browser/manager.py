"""Patchright stealth browser manager.

Launches an anti-detect Chromium with extensions and a temporary or persistent
profile. A portable, self-contained implementation with no project-specific
dependencies - suitable for reuse in other projects.
"""

from __future__ import annotations

import logging
import tempfile
from pathlib import Path
from typing import Any

from patchright.async_api import (
    BrowserContext,
    Page,
    Playwright,
    async_playwright,
)

from .config import BrowserConfig
from .extensions import discover_extensions

logger = logging.getLogger(__name__)


class BrowserManager:
    """Manages the lifecycle of a Patchright stealth browser.

    Supports:
    - resource blocking (images, media, fonts, domains);
    - loading unpacked extensions;
    - a temporary profile (removed on close) or a persistent one
      (``user_data_dir`` - kept between runs).

    Usage::

        async with BrowserManager(BrowserConfig()) as browser:
            page = browser.page
            await page.goto("https://example.com")
    """

    def __init__(
        self,
        config: BrowserConfig | None = None,
        logger_name: str | None = None,
    ) -> None:
        """Initialize the manager.

        Args:
            config: Launch configuration. Defaults are used when ``None``.
            logger_name: Log prefix (e.g. a task/source name).
        """
        self.config = config or BrowserConfig()
        self._logger = logging.getLogger(__name__)
        self._logger_prefix = f"[{logger_name}]" if logger_name else None

        self._playwright: Playwright | None = None
        self._context: BrowserContext | None = None
        self._page: Page | None = None
        self._temp_profile: tempfile.TemporaryDirectory | None = None

    @property
    def page(self) -> Page | None:
        """Current browser page."""
        return self._page

    @property
    def context(self) -> BrowserContext | None:
        """Current browser context."""
        return self._context

    def _log(self, level: str, message: str, **kwargs: Any) -> None:
        prefixed = f"{self._logger_prefix} {message}" if self._logger_prefix else message
        getattr(self._logger, level)(prefixed, **kwargs)

    def _resolve_user_data_dir(self) -> str:
        """Return the profile directory: persistent from config, or temporary.

        Persistent (``config.user_data_dir``) is used as-is and never removed.
        Otherwise a self-cleaning ``TemporaryDirectory`` is kept on the instance
        as a finalizer backstop if ``close()`` is skipped (not proof against
        SIGKILL).
        """
        if self.config.user_data_dir is not None:
            user_data_dir = Path(self.config.user_data_dir)
            user_data_dir.mkdir(parents=True, exist_ok=True)
            self._log("info", f"Persistent browser profile: {user_data_dir}")
            return str(user_data_dir)

        self._temp_profile = tempfile.TemporaryDirectory(prefix="chrome_profile_")
        self._log("info", f"Created temporary browser profile: {self._temp_profile.name}")
        return self._temp_profile.name

    def _get_base_browser_args(self) -> list[str]:
        """Base Chromium launch args + ``extra_args`` from config."""
        args = [
            "--disable-blink-features=AutomationControlled",
            "--test-type",
        ]
        if self.config.extra_args:
            args.extend(self.config.extra_args)
        return args

    def _load_extensions_args(self) -> list[str]:
        """Extension-loading args (or an empty list).

        When ``extensions_dir`` is not set, no extensions are loaded (silently).
        """
        if self.config.extensions_dir is None:
            return []

        extensions = discover_extensions(self.config.extensions_dir)
        if not extensions:
            self._log("warning", "No extensions found - launching without them")
            return []

        joined = ",".join(str(path) for path in extensions)
        for extension in extensions:
            self._log("info", f"Loaded extension: {extension.name}")
        return [
            f"--disable-extensions-except={joined}",
            f"--load-extension={joined}",
        ]

    def _should_block_resource(self, route: Any) -> bool:
        """Whether to block a resource by type or domain."""
        request = route.request
        if request.resource_type in self.config.blocked_resource_types:
            return True
        return any(domain in request.url for domain in self.config.blocked_domains)

    async def _setup_media_blocking(self) -> None:
        """Enable resource blocking if configured."""
        if not self.config.block_media or not self._context:
            return
        await self._context.route(
            "**/*",
            lambda route: route.abort() if self._should_block_resource(route) else route.continue_(),
        )
        self._log(
            "info",
            f"Blocking active: {len(self.config.blocked_resource_types)} resource types, "
            f"{len(self.config.blocked_domains)} domains",
        )

    def _build_viewport(self) -> dict[str, int] | None:
        if self.config.no_viewport:
            return None
        return {"width": self.config.viewport_width, "height": self.config.viewport_height}

    async def start(self) -> Page:
        """Launch the browser and return a ready page.

        Returns:
            The browser page.

        Raises:
            RuntimeError: If the page could not be created.
        """
        self._log("info", "Launching browser")
        self._playwright = await async_playwright().start()

        launch_args = self._get_base_browser_args()
        launch_args.extend(self._load_extensions_args())

        viewport = self._build_viewport()

        # Single code path: a persistent context covers both profile modes and
        # is required to load extensions.
        user_data_dir = self._resolve_user_data_dir()
        self._context = await self._playwright.chromium.launch_persistent_context(
            user_data_dir=user_data_dir,
            headless=False,
            viewport=viewport,
            # without [no_viewport=True] getting cookies from qrator is not possible when [viewport] is not set
            no_viewport=self.config.no_viewport,
            args=launch_args or None,
        )
        self._log("info", "Browser launched (persistent context)")
        self._page = self._context.pages[0] if self._context.pages else await self._context.new_page()

        if self._page is None:
            raise RuntimeError("Failed to create browser page")

        await self._setup_media_blocking()
        return self._page

    async def close(self) -> None:
        """Close the browser and clean up resources.

        Each step is isolated in ``try/except`` so a failure at one stage does
        not leave a dangling Chromium process or temporary profile. A persistent
        profile (``user_data_dir``) is NOT removed.
        """
        if self._context:
            try:
                await self._context.close()
            except Exception as exc:
                self._log("warning", f"Failed to close context: {exc}")

        if self._playwright:
            try:
                await self._playwright.stop()
            except Exception as exc:
                self._log("warning", f"Failed to stop playwright: {exc}")

        self._log("info", "Browser closed")
        self._cleanup_temp_profile()

    def _cleanup_temp_profile(self) -> None:
        """Remove the temporary profile (leaves a persistent one untouched)."""
        if not self._temp_profile:
            return
        temp_path = self._temp_profile.name
        try:
            self._temp_profile.cleanup()
            self._log("info", f"Temporary profile removed: {temp_path}")
        except Exception as exc:
            self._log("warning", f"Failed to remove temporary profile: {exc}")
        finally:
            self._temp_profile = None

    async def __aenter__(self) -> "BrowserManager":
        await self.start()
        return self

    async def __aexit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        await self.close()
