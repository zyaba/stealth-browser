# stealth-browser

[![Python](https://img.shields.io/badge/python-%3E%3D3.10-blue.svg)](https://www.python.org/)
[![Version](https://img.shields.io/badge/version-0.2.0-informational.svg)](pyproject.toml)
[![Built on Patchright](https://img.shields.io/badge/built%20on-Patchright-8A2BE2.svg)](https://github.com/Kaliiiiiiiiii-Vinyzu/patchright)

A standalone, portable Python library for launching an **anti-detect Chromium**
browser on [Patchright](https://github.com/Kaliiiiiiiiii-Vinyzu/patchright) (a
Playwright fork). Drive it from code with a small async API, or run it as a CLI
that opens a CDP port for [Chrome DevTools MCP](https://github.com/ChromeDevTools/chrome-devtools-mcp).

## Why use it

- **Stealth by default** - launches Chromium with Patchright's anti-detect
  patches, harder to fingerprint than vanilla Playwright.
- **Portable** - a single dependency (Patchright); drop it into any project.
- **Flexible profiles** - a temporary profile that is wiped on close, or a
  persistent one that keeps cookies/storage/cache between runs.
- **Unpacked extensions** - load your own extensions (e.g. an ad blocker) from a
  directory you control.
- **Faster, quieter pages** - block images/media/fonts and specific domains
  (analytics, ads) out of the box.
- **MCP-ready** - opens a remote-debugging (CDP) port so `chrome-devtools-mcp`
  can drive the browser via `--browserUrl`.

> Headless is intentionally never used: Patchright always launches headed (it is
> harder to detect). To hide the window on a server, run under `xvfb-run` - see
> [Running headless on Linux/VPS](#running-headless-on-linuxvps).

## Requirements

- Python **>= 3.10**
- [`patchright`](https://github.com/Kaliiiiiiiiii-Vinyzu/patchright) `~=1.60`
  (installed automatically as a dependency)
- A Chromium binary for Patchright (installed once per machine, see below)

## Installation

The Chromium binary for Patchright is needed once. By default it lands in a
shared per-user cache (`~/.cache/ms-playwright`) and is reused everywhere:

```bash
patchright install chromium      # or: uv run patchright install chromium
```

### Option 1 - as a dependency of your project

Install into your project's environment. Both the CLI
(`python -m stealth_browser`) and imports
(`from stealth_browser import BrowserManager`) become available.

```bash
uv pip install -e <path-to-stealth-browser>   # editable - edits apply immediately
uv pip install <path-to-stealth-browser>      # regular snapshot install
```

### Option 2 - globally as a CLI tool

An isolated install after which the `stealth-browser` command works from any
directory without activating a venv. Good for ad-hoc launches; not suitable for
`import stealth_browser` in your code - use Option 1 for that.

```bash
uv tool install <path-to-stealth-browser>     # or: pipx install <path-to-stealth-browser>
stealth-browser --url "https://example.com" --port 9222
```

## Quick start

### Use as a library

```python
import asyncio
from stealth_browser import BrowserConfig, BrowserManager


async def main():
    # Temporary profile (removed on close)
    async with BrowserManager(BrowserConfig()) as browser:
        await browser.page.goto("https://example.com", wait_until="domcontentloaded")
        print(await browser.page.title())

    # Persistent profile (data persists between runs)
    config = BrowserConfig(user_data_dir="./profile")
    async with BrowserManager(config) as browser:
        await browser.page.goto("https://example.com")


asyncio.run(main())
```

More examples live in [`examples/example.py`](examples/example.py).

### Use as a CLI

```bash
# temporary profile + CDP port for MCP
python -m stealth_browser --url "https://example.com" --port 9222

# persistent profile
python -m stealth_browser --url "https://example.com" --user-data-dir ./profile

# with unpacked extensions (each in its own subfolder)
python -m stealth_browser --url "https://example.com" --extensions-dir ./extensions

# do not block media/analytics (full Network picture)
python -m stealth_browser --url "https://example.com" --show-media
```

The browser stays open until you stop it with `Ctrl+C`.

| Flag | Default | Purpose |
|---|---|---|
| `--url` | `about:blank` | first navigation target |
| `--port` | `9222` | CDP remote-debugging port |
| `--user-data-dir` | *(temporary)* | persistent profile directory |
| `--extensions-dir` | *(none)* | directory of unpacked extensions |
| `--show-media` | off | do not block media/domains |

## Configuration

`BrowserConfig` controls how the browser launches:

| Field | Default | Purpose |
|---|---|---|
| `block_media` | `True` | block image/media/font resources and `blocked_domains` |
| `no_viewport` | `False` | disable the fixed viewport |
| `viewport_width` / `viewport_height` | `1920` / `1080` | viewport size |
| `extra_args` | `None` | extra Chromium args (e.g. `--remote-debugging-port=9222`) |
| `user_data_dir` | `None` | persistent profile directory; `None` → temporary |
| `extensions_dir` | `None` | unpacked-extensions directory; `None` → no extensions |
| `blocked_resource_types` | `("image", "media", "font")` | resource types to block |
| `blocked_domains` | `()` | domain substrings to block |

### Extensions

Extensions are **not** bundled with the library. Point `extensions_dir` (or the
`--extensions-dir` flag) at a directory of unpacked extensions, each in its own
subfolder. When unset, the browser starts without extensions.

## CDP port for Chrome DevTools MCP

The launcher opens a remote-debugging port that `chrome-devtools-mcp` connects
to via `--browserUrl`:

```bash
python -m stealth_browser --url "https://example.com" --port 9222
```

Then point the MCP server at `--browserUrl=http://127.0.0.1:9222`.

### Multiple instances

Run several browsers on different ports. The MCP server takes a static port from
`--browserUrl`, so the launcher's `--port` must match the target server:

```bash
python -m stealth_browser --url "<url1>" --port 9222   # → chrome-devtools-9222
python -m stealth_browser --url "<url2>" --port 9223   # → chrome-devtools-9223
```

Use different `--user-data-dir` values to isolate data across parallel
instances.

## Running headless on Linux/VPS

Patchright always launches headed. To hide the window on a server, wrap it with
Xvfb:

```bash
xvfb-run -a -s '-screen 0 1920x1080x24' python -m stealth_browser --url "https://example.com"
```

## Project layout

```
.
├── src/stealth_browser/
│   ├── __init__.py     # public API: BrowserConfig, BrowserManager, __version__
│   ├── config.py       # BrowserConfig dataclass
│   ├── manager.py      # BrowserManager: launch/close, profiles, blocking
│   ├── extensions.py   # unpacked-extension discovery
│   ├── mcp_launcher.py # CLI entry point; opens a CDP port
│   ├── __main__.py     # python -m stealth_browser
│   └── py.typed        # PEP 561 typing marker
├── examples/
│   └── example.py
├── pyproject.toml
└── README.md
```

## Getting help

- Browse the runnable [`examples/`](examples/) for common setups.
- For the underlying browser automation API, see the
  [Patchright](https://github.com/Kaliiiiiiiiii-Vinyzu/patchright) and
  [Playwright for Python](https://playwright.dev/python/) docs.
- For MCP integration, see
  [chrome-devtools-mcp](https://github.com/ChromeDevTools/chrome-devtools-mcp).
- Found a bug or have a question? Open an issue in the project's issue tracker.

## License

No license file is currently included in this repository. Until one is added,
usage and distribution rights are not formally granted - please contact the
maintainers before relying on it in production.
