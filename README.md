# stealth-browser

A standalone library for launching an anti-detect browser on
[Patchright](https://github.com/Kaliiiiiiiiii-Vinyzu/patchright) (a Playwright
fork). Portable across projects: no external dependencies beyond Patchright.

Features:
- stealth Chromium launch (Patchright anti-detect);
- loading unpacked extensions from a given path (`extensions_dir`);
- a **temporary** profile (removed on close) or a **persistent** one
  (`user_data_dir` — cookies/storage/cache persist between runs);
- resource blocking by type (image/media/font) and by domain;
- opening a CDP port for control via **Chrome DevTools MCP**.

> Headless is intentionally not used: Patchright always launches the browser
> headed (harder to detect). To hide the window on a server/Linux, run it under
> `xvfb-run` (see below).

## Installation

In all cases the Chromium binary for Patchright is needed once. By default it is
placed in a shared per-user cache (`~/.cache/ms-playwright`) and reused by all
environments — usually one install per machine is enough:

```bash
patchright install chromium      # or: uv run patchright install chromium
```

### Option 1 — as a dependency of a consumer project

Install the library into the consumer's environment. Both the CLI
(`python -m browser`) and code imports (`from browser.manager import BrowserManager`)
become available.

```bash
# from the consumer's environment (the browser/ repo sits nearby)
uv pip install -e <path-to-browser>     # editable — imports from the working copy, edits apply immediately
# or a regular install (snapshot in site-packages, edits not seen until reinstall):
uv pip install <path-to-browser>
```

Run (with the consumer environment active; in a uv project — via `uv run`):

```bash
python -m browser --url "https://example.com" --port 9222
# uv project: uv run python -m browser --url "https://example.com" --port 9222
```

### Option 2 — globally as a CLI tool

An isolated install after which the `stealth-browser` command is available
**from any directory without activating a venv**. Good for ad-hoc launches of
the browser; not suitable for `import browser` in your code — use Option 1 for
that.

```bash
uv tool install <path-to-browser>       # or: pipx install <path-to-browser>
stealth-browser --url "https://example.com" --port 9222
```

> To develop the library itself: from the repo run `uv venv && uv pip install -e .`,
> then `uv run python -m browser --url ...` (uses the local `.venv`).

## Use as a library

Install the package (see "Installation") and import the public API:

```python
import asyncio
from browser import BrowserConfig, BrowserManager


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

Equivalent submodule imports:

```python
from browser.config import BrowserConfig
from browser.manager import BrowserManager
```

Examples — `examples/example.py`.

### Configuration (`BrowserConfig`)

| Field | Default | Purpose |
|---|---|---|
| `block_media` | `True` | block image/media/font and `blocked_domains` |
| `no_viewport` | `False` | disable the fixed viewport |
| `viewport_width` / `viewport_height` | `1920` / `1080` | viewport size |
| `extra_args` | `None` | extra Chromium args (e.g. `--remote-debugging-port=9222`) |
| `persistent_context` | `True` | on-disk profile vs plain launch |
| `user_data_dir` | `None` | persistent profile directory; `None` → temporary |
| `extensions_dir` | `None` | extensions directory; `None` → no extensions |
| `blocked_resource_types` | `("image","media","font")` | resource types to block |
| `blocked_domains` | `()` | domain substrings to block |

### Extensions

Extensions are **not bundled** with the library. To load some (e.g. uBlock
Origin Lite), point to a directory of unpacked extensions via
`BrowserConfig(extensions_dir=...)` or the launcher's `--extensions-dir` flag.
When `extensions_dir` is not set, the browser starts without extensions. Inside
the directory each extension is a separate subfolder (an unpacked crx).

## CDP port for Chrome DevTools MCP

The launcher starts the browser and opens a remote debugging port, which
`chrome-devtools-mcp` connects to via `--browserUrl`:

```bash
# temporary profile
python -m browser --url "https://example.com" --port 9222

# persistent profile
python -m browser --url "https://example.com" --user-data-dir ./profile

# with extensions from a directory (unpacked, each in its own subfolder)
python -m browser --url "https://example.com" --extensions-dir ./extensions

# show media/analytics (full Network picture)
python -m browser --url "https://example.com" --show-media
```

> Commands work from any directory (CWD does not matter) — given an active
> environment where the package is installed (Option 1), or a global
> `stealth-browser` install (Option 2). Inside the library repo — via
> `uv run python -m browser ...` (local `.venv`).

The browser stays open until stopped with `Ctrl+C`. Point the MCP server at
`--browserUrl=http://127.0.0.1:9222`.

Hide the window on Linux/VPS:

```bash
xvfb-run -a -s '-screen 0 1920x1080x24' python -m browser --url "https://example.com"
```

## Layout

```
.
├── src/browser/
│   ├── __init__.py     # public API: BrowserConfig, BrowserManager, __version__
│   ├── config.py       # BrowserConfig
│   ├── manager.py      # BrowserManager (launch/close, profiles, blocking)
│   ├── extensions.py   # unpacked-extension discovery
│   ├── mcp_launcher.py # launch the browser with a CDP port
│   ├── __main__.py     # python -m browser
│   └── py.typed        # typing marker (PEP 561)
├── examples/
│   └── example.py      # example of using the installed package
├── pyproject.toml
└── README.md
```

## Multi-instance (several browsers)

The launcher supports running several browsers on different CDP ports via
`--port`. `chrome-devtools-mcp` takes the port from `--browserUrl` (static), so
the launcher's port must match the port of the target MCP server:

```bash
python -m browser --url "<url1>" --port 9222   # → chrome-devtools-9222
python -m browser --url "<url2>" --port 9223   # → chrome-devtools-9223
```

For data isolation across parallel instances, use different `--user-data-dir`.

## Agent usage and consumers

Everything an agent needs to drive the browser (steering policy,
`settings/mcp.json` with `chrome-devtools` servers, helper scripts, custom
agents/hooks) lives in the **consumer project**, in its own `.kiro/`. The
library itself ships no Kiro context.

To make the library importable for a consumer, install it as a package
(`uv pip install -e <path-to-browser>`) or put `browser/` on `PYTHONPATH`. Kiro
context is loaded per workspace, not via the Python import — so MCP/steering
stay with the consumer, not in this library.
