"""Stealth browser with an open CDP port for Chrome DevTools MCP.

Launches an anti-detect browser and opens ``--remote-debugging-port``, which
``chrome-devtools-mcp`` connects to via ``--browserUrl``. The browser stays up
until stopped (Ctrl+C).

``--extensions-dir`` accepts a relative path; it is resolved to absolute
(relative to the CWD) before being passed to Chromium::

    stealth-browser --url "https://example.com" --port 9222
    python -m stealth_browser --url "https://example.com" --user-data-dir ./profile
    python -m stealth_browser --url "https://example.com" --extensions-dir ./extensions
"""

from __future__ import annotations

import argparse
import asyncio
import contextlib
import logging
import signal
from typing import Any

from .config import BrowserConfig
from .manager import BrowserManager

DEFAULT_REMOTE_DEBUGGING_PORT = 9222

logger = logging.getLogger(__name__)


async def run_cdp_browser(
    target_url: str = "about:blank",
    remote_debugging_port: int = DEFAULT_REMOTE_DEBUGGING_PORT,
    block_media: bool = True,
    user_data_dir: str | None = None,
    extensions_dir: str | None = None,
) -> None:
    """Launch a browser with a CDP port and keep it open until cancelled.

    Args:
        target_url: First navigation target (``about:blank`` for none).
        remote_debugging_port: Remote debugging port for the MCP connection.
        block_media: Whether to block images/media/domains.
        user_data_dir: Persistent profile (None - temporary).
        extensions_dir: Directory with unpacked extensions (None - none;
            extensions are not bundled with the library, the consumer provides
            the path).
    """
    config = BrowserConfig(
        block_media=block_media,
        user_data_dir=user_data_dir,
        extensions_dir=extensions_dir,
        extra_args=[f"--remote-debugging-port={remote_debugging_port}"],
    )
    manager = BrowserManager(config=config, logger_name="cdp")

    page = await manager.start()
    logger.info("CDP available at http://127.0.0.1:%d", remote_debugging_port)
    logger.info(
        "Connect Chrome DevTools MCP: --browserUrl=http://127.0.0.1:%d",
        remote_debugging_port,
    )

    try:
        if target_url and target_url != "about:blank":
            logger.info("Navigating: %s", target_url)
            await page.goto(target_url, wait_until="domcontentloaded")
        logger.info("Browser is up. Stop with Ctrl+C.")
        await asyncio.Event().wait()
    finally:
        await manager.close()


def _parse_arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="python -m stealth_browser",
        description="Patchright stealth browser with a CDP port for Chrome DevTools MCP.",
    )
    parser.add_argument("--url", default="about:blank", help="First navigation target.")
    parser.add_argument("--port", type=int, default=DEFAULT_REMOTE_DEBUGGING_PORT, help="CDP port.")
    parser.add_argument("--user-data-dir", default=None, help="Persistent profile (temporary by default).")
    parser.add_argument("--extensions-dir", default=None, help="Directory with unpacked extensions (none by default).")
    parser.add_argument("--show-media", action="store_true", help="Do not block media/domains.")
    return parser.parse_args()


def _install_termination_handler() -> None:
    """Make SIGTERM raise ``KeyboardInterrupt`` like SIGINT, so ``kill <pid>``
    runs the cleanup ``finally``. SIGKILL / power loss can't be handled here.
    """

    def _handler(_signum: int, _frame: Any) -> None:
        raise KeyboardInterrupt

    with contextlib.suppress(ValueError, OSError):
        signal.signal(signal.SIGTERM, _handler)


def main() -> None:
    """Launcher entry point."""
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
    _install_termination_handler()
    args = _parse_arguments()
    with contextlib.suppress(KeyboardInterrupt):
        asyncio.run(
            run_cdp_browser(
                target_url=args.url,
                remote_debugging_port=args.port,
                block_media=not args.show_media,
                user_data_dir=args.user_data_dir,
                extensions_dir=args.extensions_dir,
            )
        )
    logger.info("Launcher stopped.")


if __name__ == "__main__":
    main()
