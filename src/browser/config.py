"""Launch configuration for the Patchright stealth browser."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

DEFAULT_VIEWPORT_WIDTH = 1920
DEFAULT_VIEWPORT_HEIGHT = 1080

# Resource types to block by default (speeds up loading, saves traffic).
DEFAULT_BLOCKED_RESOURCE_TYPES: tuple[str, ...] = ("image", "media", "font")


@dataclass
class BrowserConfig:
    """Browser launch parameters.

    Attributes:
        block_media: Block images/media/fonts and the domains listed in
            ``blocked_domains``.
        no_viewport: Disable the fixed viewport (some sites need this to work
            correctly, e.g. when setting cookies).
        viewport_width: Viewport width (when ``no_viewport=False``).
        viewport_height: Viewport height (when ``no_viewport=False``).
        extra_args: Extra Chromium launch arguments (e.g.
            ``--remote-debugging-port=9222`` for CDP/MCP).
        persistent_context: Use a persistent context (on-disk profile) instead
            of a plain launch + new_context. A persistent profile
            (``user_data_dir``) is possible ONLY in this mode, so it is forced
            on whenever ``user_data_dir`` is set.
        user_data_dir: Browser profile directory. When set, browser data
            (cookies, storage, cache) persists between runs (PERSISTENT storage)
            and the persistent context is enabled automatically. When ``None``
            and ``persistent_context=True``, a temporary profile is created and
            removed on close (EPHEMERAL storage).
        extensions_dir: Directory with unpacked extensions. When set, extensions
            from it are loaded; when ``None`` the browser starts without
            extensions. Extensions are NOT bundled with the library — the path
            is provided by the consumer.
        blocked_resource_types: Resource types to block when
            ``block_media=True``.
        blocked_domains: Domain substrings to block (analytics, ads).

    Note:
        Headless mode is intentionally never set. Patchright (an anti-detect
        Playwright fork) patches the ``headless`` flag: even with
        ``headless=True`` the browser launches headed. To hide the window on
        Linux/VPS, use Xvfb (see README).
    """

    block_media: bool = True
    no_viewport: bool = False
    viewport_width: int = DEFAULT_VIEWPORT_WIDTH
    viewport_height: int = DEFAULT_VIEWPORT_HEIGHT
    extra_args: list[str] | None = None
    persistent_context: bool = True
    user_data_dir: str | Path | None = None
    extensions_dir: str | Path | None = None
    blocked_resource_types: tuple[str, ...] = DEFAULT_BLOCKED_RESOURCE_TYPES
    blocked_domains: tuple[str, ...] = ()
