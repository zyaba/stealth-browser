"""Stealth browser with an open CDP port for Chrome DevTools MCP.

``run`` (default) launches an anti-detect browser and opens
``--remote-debugging-port``, which ``chrome-devtools-mcp`` connects to via
``--browserUrl``. The browser stays up until stopped (Ctrl+C).

``start`` / ``stop`` / ``status`` manage a *detached* instance so agents and
scripts don't hand-roll process handling. An instance is identified by its CDP
port; run several projects in parallel on different ports (each with its own
``--user-data-dir`` - Chromium locks a profile).

``--extensions-dir`` accepts a relative path; it is resolved to absolute
(relative to the CWD) before being passed to Chromium::

    stealth-browser --url "https://example.com" --port 9222
    stealth-browser run --url "https://example.com" --user-data-dir ./profile
    stealth-browser start --port 9222 --user-data-dir ./profile --show-media
    stealth-browser status --port 9222
    stealth-browser stop --port 9222
"""

from __future__ import annotations

import argparse
import asyncio
import contextlib
import logging
import signal
import sys
from typing import Any

from . import __version__, lifecycle
from .config import BrowserConfig
from .manager import BrowserManager

DEFAULT_REMOTE_DEBUGGING_PORT = lifecycle.DEFAULT_PORT
DEFAULT_URL = lifecycle.DEFAULT_URL

logger = logging.getLogger(__name__)

_SUBCOMMANDS = ("run", "start", "stop", "status")
_TOP_LEVEL_OPTIONS = ("-h", "--help", "--version")


def _port_type(value: str) -> int:
    port = int(value)
    if not 1 <= port <= 65535:
        raise argparse.ArgumentTypeError(f"port must be in 1..65535, got {port}")
    return port


async def run_cdp_browser(
    target_url: str = DEFAULT_URL,
    remote_debugging_port: int = DEFAULT_REMOTE_DEBUGGING_PORT,
    block_media: bool = True,
    user_data_dir: str | None = None,
    extensions_dir: str | None = None,
) -> None:
    """Launch a browser with a CDP port and keep it open until cancelled.

    Returns when the browser/context closes (so an external shutdown lets a
    detached launcher exit and run its cleanup) or on Ctrl+C.

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
    # Machine-readable readiness line so ``start`` can bound its wait on the
    # browser actually being up (not just its CDP port answering).
    print(f"STEALTH_BROWSER_READY {remote_debugging_port}", flush=True)

    try:
        if target_url and target_url != DEFAULT_URL:
            logger.info("Navigating: %s", target_url)
            await page.goto(target_url, wait_until="domcontentloaded")

        context = manager.context
        assert context is not None
        closed = asyncio.Event()
        context.on("close", lambda *_: closed.set())
        logger.info("Browser is up. Stop with Ctrl+C or by closing the browser.")
        await closed.wait()
    finally:
        await manager.close()


def _add_launch_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--url", default=DEFAULT_URL, help="First navigation target.")
    parser.add_argument("--port", type=_port_type, default=DEFAULT_REMOTE_DEBUGGING_PORT, help="CDP port.")
    parser.add_argument("--user-data-dir", default=None, help="Persistent profile (temporary by default).")
    parser.add_argument("--extensions-dir", default=None, help="Directory with unpacked extensions (none by default).")
    parser.add_argument("--show-media", action="store_true", help="Do not block media/domains.")


def _add_lifecycle_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--port", type=_port_type, default=DEFAULT_REMOTE_DEBUGGING_PORT, help="CDP port (instance id).")
    parser.add_argument("--pid-file", default=None, help="Launcher PID file (default: .stealth-browser/browser-<port>.pid).")


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m stealth_browser",
        description="Patchright stealth browser with a CDP port for Chrome DevTools MCP.",
    )
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    subparsers = parser.add_subparsers(dest="command")

    run_parser = subparsers.add_parser("run", help="Launch in the foreground until Ctrl+C (default).")
    _add_launch_arguments(run_parser)

    start_parser = subparsers.add_parser("start", help="Launch a detached instance on a CDP port.")
    _add_launch_arguments(start_parser)
    start_parser.add_argument("--pid-file", default=None, help="Launcher PID file (default: .stealth-browser/browser-<port>.pid).")
    start_parser.add_argument("--log-file", default=None, help="Child log file (default: .stealth-browser/browser-<port>.out).")

    stop_parser = subparsers.add_parser("stop", help="Stop the instance on a CDP port.")
    _add_lifecycle_arguments(stop_parser)

    status_parser = subparsers.add_parser("status", help="Report CDP liveness + launcher PID.")
    _add_lifecycle_arguments(status_parser)

    return parser


def _parse_arguments(argv: list[str] | None = None) -> argparse.Namespace:
    argv = list(sys.argv[1:] if argv is None else argv)
    parser = _build_parser()
    # Back-compat: a bare ``stealth-browser --url ...`` (or no args) means ``run``.
    if not argv or (argv[0] not in _SUBCOMMANDS and argv[0] not in _TOP_LEVEL_OPTIONS):
        argv = ["run", *argv]
    return parser.parse_args(argv)


def _install_termination_handler() -> None:
    """Make SIGTERM raise ``KeyboardInterrupt`` like SIGINT, so ``kill <pid>``
    runs the cleanup ``finally``. SIGKILL / power loss can't be handled here.
    """

    def _handler(_signum: int, _frame: Any) -> None:
        raise KeyboardInterrupt

    with contextlib.suppress(ValueError, OSError):
        signal.signal(signal.SIGTERM, _handler)


def _run_foreground(args: argparse.Namespace) -> int:
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
    return 0


def main() -> None:
    """Launcher entry point."""
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
    _install_termination_handler()
    args = _parse_arguments()

    if args.command == "start":
        raise SystemExit(
            lifecycle.cmd_start(
                port=args.port,
                url=args.url,
                user_data_dir=args.user_data_dir,
                extensions_dir=args.extensions_dir,
                show_media=args.show_media,
                pid_file=args.pid_file,
                log_file=args.log_file,
            )
        )
    if args.command == "stop":
        raise SystemExit(lifecycle.cmd_stop(port=args.port, pid_file=args.pid_file))
    if args.command == "status":
        raise SystemExit(lifecycle.cmd_status(port=args.port, pid_file=args.pid_file))

    raise SystemExit(_run_foreground(args))


if __name__ == "__main__":
    main()
