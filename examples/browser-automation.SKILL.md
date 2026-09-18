---
name: browser-automation
description: Use when an agent needs to open and drive a REAL browser (navigate, click, read DOM/Network, run JS, take screenshots) for recon, scraping, or debugging — especially on anti-bot/qrator-protected sites or when a logged-in session matters. Covers launching the stealth browser and attaching Chrome DevTools MCP. Triggers on "open a browser", "stealth-browser", "chrome-devtools", "CDP port", "scrape/inspect a site".
---

<!--
  CANONICAL TEMPLATE. This is the source of truth for the generic browser
  automation policy shared across projects. Install it as a global opencode
  skill so agents load it on demand without a per-repo copy:

    copy this file to  ~/.config/opencode/skill/browser-automation/SKILL.md
    then restart opencode.

  Project repos keep only a small delta (port, target site, selectors, login)
  that defers to this skill. Edit the policy here and re-copy; keep the two in
  sync.
-->

# Browser automation (stealth-browser + Chrome DevTools MCP)

Generic policy for driving a real browser from an agent. Project-specific rules
(ports, target sites, selectors, login) live in each repo's own
`browser-automation.md` and extend this.

## When to use

Open a real browser for: reconnaissance on a new site, finding hidden JSON APIs,
inspecting Network/DOM, debugging anti-bot, reproducing SPA rendering. Do **not**
write one-off Playwright/Patchright scripts for this — use the stealth browser +
`chrome-devtools` MCP.

For plain `webfetch`-able content, prefer that; a browser is for interaction and
anti-bot sites.

## Mechanism

The `chrome-devtools` MCP **attaches** to a running browser via
`--browserUrl=http://127.0.0.1:<port>`; it does not launch the stealth browser
itself. So the order is always: **start stealth-browser first, then use the MCP
tools.**

The port is chosen per task/project. A repo that drives a browser declares its
own `chrome-devtools` MCP server on its own port; for ad-hoc use the global
config ships a default (`9227`). The launcher `--port` MUST match the MCP
server's `--browserUrl`.

## Workflow

1. Bring the browser up (detached, isolated temp profile by default — omit
   `--user-data-dir` for a throwaway session, pass it for a persistent login):

   ```bash
   stealth-browser start --port <port> --url "<target-url>" --show-media
   ```

   `start` waits for CDP readiness and writes `.stealth-browser/browser-<port>.pid`;
   it refuses a second instance on the same port. Check with
   `stealth-browser status --port <port>`.

2. Confirm the MCP tools are present (`list_pages`, `navigate_page`,
   `take_snapshot`, `evaluate_script`). If missing, the `chrome-devtools` server
   isn't loaded — MCP servers load at session start, so restart the session after
   config changes. Generate a matching server config with
   `stealth-browser mcp-config --port <port>`.

3. Drive the page through the `chrome-devtools` MCP tools.

4. Stop when done:

   ```bash
   stealth-browser stop --port <port>
   ```

## NEVER `pkill -f`

Stop only via `stealth-browser stop --port <port>`. `pkill -f stealth-browser`
(or `pkill -f <port>`) also matches the shell running it and kills that shell
mid-command. `stealth-browser stop` resolves the port owner via the OS socket
table (`netstat -ano` on Windows, `ss`/`lsof` on POSIX), verifies it is this
launcher, and kills its process tree cross-platform.

## Context discipline on long sessions

- For bulky output from `evaluate_script`, `take_snapshot`, `take_screenshot`,
  `get_network_request`, `performance_*`, set `filePath`/`responseFilePath` — the
  result goes to a file, not the model context.
- `evaluate_script` without `filePath` must return compact results (counters /
  short objects), never raw arrays of hundreds of items or full `innerHTML`.
- Persist intermediate data to files in chunks (≤50 lines/call); one-off dumps go
  to a scratch dir like `.agent/`, not the repo root.

## Boundaries

Browser recon/debug is for development. Regular/production extraction belongs in
a real pipeline (Patchright/`BrowserManager` or a worker), not through MCP.
