# stealth-browser

[![Python](https://img.shields.io/badge/python-%3E%3D3.10-blue.svg)](https://www.python.org/)
[![Version](https://img.shields.io/badge/version-0.3.0-informational.svg)](pyproject.toml)
[![Built on Patchright](https://img.shields.io/badge/built%20on-Patchright-8A2BE2.svg)](https://github.com/Kaliiiiiiiiii-Vinyzu/patchright)

A small, portable Python library and CLI for launching an **anti-detect Chromium** on [Patchright](https://github.com/Kaliiiiiiiiii-Vinyzu/patchright) (a Playwright fork). Drive it from an async API, or run it as a CLI that opens a CDP port for [Chrome DevTools MCP](https://github.com/ChromeDevTools/chrome-devtools-mcp).

## Why use it

- **Stealth by default** — Patchright's anti-detect patches, harder to fingerprint than vanilla Playwright.
- **One dependency** — just Patchright; drop it into any project.
- **Flexible profiles** — temporary (wiped on close) or persistent (cookies/storage kept between runs).
- **Unpacked extensions** — load your own (e.g. an ad blocker) from a directory you control.
- **Quieter pages** — block images/media/fonts and analytics/ad domains out of the box.
- **MCP-ready lifecycle** — `start`/`stop`/`status` manage detached instances keyed by CDP port, so several projects run in parallel without hand-rolled process handling.

> Headless is never used: Patchright always launches headed (harder to detect). On a server, wrap the command in `xvfb-run` to hide the window.

## Requirements

- Python **>= 3.10**
- [`patchright`](https://github.com/Kaliiiiiiiiii-Vinyzu/patchright) `~=1.60` (installed automatically)
- A Chromium binary for Patchright, installed once per machine: `patchright install chromium`

## Installation

```bash
# As a project dependency (library + CLI). Use -e for live edits.
uv pip install -e <path-to-stealth-browser>

# Or as a global CLI tool (no venv needed; not importable in your code).
uv tool install <path-to-stealth-browser>   # or: pipx install ...
```

## Usage

### Library

```python
import asyncio
from stealth_browser import BrowserConfig, BrowserManager


async def main():
    # Temporary profile (removed on close). Use user_data_dir to persist between runs.
    async with BrowserManager(BrowserConfig()) as browser:
        await browser.page.goto("https://example.com", wait_until="domcontentloaded")
        print(await browser.page.title())


asyncio.run(main())
```

See [`examples/example.py`](examples/example.py) for persistent profiles, extensions, and custom blocking.

### CLI

`run` (the default) launches in the foreground until `Ctrl+C` or the browser is closed. `start`/`stop`/`status` manage a **detached** instance identified by its CDP port, so parallel projects use distinct ports.

```bash
# foreground (bare form == `run`)
stealth-browser --url "https://example.com" --port 9222

# detached lifecycle
stealth-browser start  --port 9222 --url "https://example.com" --user-data-dir ./profile
stealth-browser status --port 9222
stealth-browser stop   --port 9222
```

Good to know:

- **Point MCP at the same port**: `--browserUrl=http://127.0.0.1:<port>`. The port is static per project — there is no auto-picking.
- `start` refuses if the port already serves CDP or is held by another process.
- `stop` finds the CDP port owner via the OS socket table and kills its process tree (never `pkill -f`); a recorded PID is only killed after its command line is verified, so PID reuse can't hit an unrelated process.

## Options

### CLI flags

| Flag | Commands | Default | Purpose |
|---|---|---|---|
| `--url` | run, start | `about:blank` | first navigation target |
| `--port` | all | `9222` | CDP port; also the instance id |
| `--user-data-dir` | run, start | *(temporary)* | persistent profile directory |
| `--extensions-dir` | run, start | *(none)* | directory of unpacked extensions |
| `--show-media` | run, start | off | do not block media/domains |
| `--pid-file` | start, stop, status | `.stealth-browser/browser-<port>.pid` | launcher PID file |
| `--log-file` | start | `.stealth-browser/browser-<port>.out` | detached child log |

Also: `stealth-browser --version`, and `stealth-browser <command> -h` for per-command help.

### `BrowserConfig`

| Field | Default | Purpose |
|---|---|---|
| `block_media` | `True` | block `blocked_resource_types` and `blocked_domains` |
| `no_viewport` | `False` | disable the fixed viewport |
| `viewport_width` / `viewport_height` | `1920` / `1080` | viewport size |
| `extra_args` | `None` | extra Chromium args (e.g. `--remote-debugging-port=9222`) |
| `user_data_dir` | `None` | persistent profile dir; `None` → temporary |
| `extensions_dir` | `None` | unpacked-extensions dir; `None` → none |
| `blocked_resource_types` | `("image", "media", "font")` | resource types to block |
| `blocked_domains` | `()` | domain substrings to block |

Extensions are **not** bundled: point `extensions_dir` (or `--extensions-dir`) at a directory of unpacked extensions, each in its own subfolder.

## Getting help

- [`examples/`](examples/) for runnable setups.
- [Patchright](https://github.com/Kaliiiiiiiiii-Vinyzu/patchright) and [Playwright for Python](https://playwright.dev/python/) for the browser API.
- [chrome-devtools-mcp](https://github.com/ChromeDevTools/chrome-devtools-mcp) for MCP integration.

## Contributing & license

Issues and pull requests are welcome. No `LICENSE` file is included yet, so usage and distribution rights are not formally granted — please contact the maintainers before relying on it in production.
