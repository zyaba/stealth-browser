"""Cross-platform lifecycle control for a CDP browser instance.

Adds ``start`` / ``stop`` / ``status`` on top of the plain launcher. An
*instance* is identified by its CDP port, so several projects can run browsers
in parallel on different ports (each with its own ``--user-data-dir``; Chromium
locks a profile, so parallel instances must not share one).

State is kept beside the project: by default the launcher PID lands in
``.stealth-browser/browser-<port>.pid`` and the child log in
``.stealth-browser/browser-<port>.out`` (relative to the current working
directory), overridable with ``--pid-file`` / ``--log-file``.

Stopping NEVER uses ``pkill -f``: the pattern would also match the command line
of the shell running it, killing the controlling shell mid-command. Instead the
process that OWNS the CDP port is resolved via the OS socket table and its
process tree is terminated.
"""

from __future__ import annotations

import http.client
import json
import os
import re
import signal
import subprocess
import sys
import time
import urllib.error
import urllib.request
from collections.abc import Callable
from pathlib import Path
from typing import Any

DEFAULT_PORT = 9222
DEFAULT_URL = "about:blank"

# Recommended chrome-devtools-mcp flags. --no-usage-statistics opts out of the
# server's Google telemetry; it attaches to the stealth browser via --browserUrl
# rather than launching its own vanilla Chrome.
MCP_PACKAGE = "chrome-devtools-mcp@latest"
MCP_DEFAULT_NAME = "chrome-devtools"

# Proxy URL source for ``run``/``start``. ``start`` hands the proxy to its
# detached child through this variable, never on the command line, so
# credentials do not show up in process listings.
PROXY_ENV_VAR = "STEALTH_BROWSER_PROXY"

# Opener for loopback CDP probes that ignores HTTP(S)_PROXY and system proxies.
_DIRECT_OPENER = urllib.request.build_opener(urllib.request.ProxyHandler({}))

# Per-project runtime state dir (pid files + launcher logs), relative to the CWD.
_STATE_DIR = ".stealth-browser"

# How long to wait for the CDP endpoint to come up / go down (seconds).
_READY_TIMEOUT = 15.0
_STOP_TIMEOUT = 10.0
_POLL_INTERVAL = 0.5


def default_pid_file(port: int) -> Path:
    """Launcher PID file for an instance, relative to the CWD."""
    return Path(_STATE_DIR) / f"browser-{port}.pid"


def default_log_file(port: int) -> Path:
    """Child stdout/stderr log for an instance, relative to the CWD."""
    return Path(_STATE_DIR) / f"browser-{port}.out"


def cdp_alive(port: int) -> bool:
    """Whether a CDP endpoint answers on ``127.0.0.1:<port>``.

    The probe never goes through a proxy: ``urlopen`` would otherwise honor
    ``HTTP_PROXY`` (and crash on a malformed one) for a loopback address.
    """
    url = f"http://127.0.0.1:{port}/json/version"
    try:
        with _DIRECT_OPENER.open(url, timeout=2) as response:
            return response.status == 200
    except (urllib.error.URLError, http.client.HTTPException, OSError, ValueError):
        return False


def port_owner_pid(port: int) -> int | None:
    """PID of the process LISTENING on ``port``, resolved via the socket table.

    Never matches on a command line, so it can't return the calling shell.
    """
    if os.name == "nt":
        return _port_owner_pid_windows(port)
    return _port_owner_pid_posix(port)


def _port_owner_pid_windows(port: int) -> int | None:
    try:
        out = subprocess.run(
            ["netstat", "-ano"],
            capture_output=True,
            text=True,
            timeout=10,
            check=False,
        ).stdout
    except (OSError, subprocess.SubprocessError):
        return None
    for line in out.splitlines():
        if "LISTENING" not in line:
            continue
        if not re.search(rf":{port}\s", line):
            continue
        match = re.search(r"LISTENING\s+(\d+)\s*$", line)
        if match:
            return int(match.group(1))
    return None


def _port_owner_pid_posix(port: int) -> int | None:
    for command in (
        ["ss", "-ltnp"],
        ["lsof", "-ti", f"tcp:{port}", "-sTCP:LISTEN"],
    ):
        try:
            result = subprocess.run(
                command,
                capture_output=True,
                text=True,
                timeout=10,
                check=False,
            )
        except (OSError, subprocess.SubprocessError):
            continue
        if result.returncode != 0 or not result.stdout.strip():
            continue
        # lsof prints bare PIDs, one per line.
        if command[0] == "lsof":
            first = result.stdout.split()[0]
            if first.isdigit():
                return int(first)
            continue
        for line in result.stdout.splitlines():
            if not re.search(rf":{port}\b", line):
                continue
            match = re.search(r"pid=(\d+)", line)
            if match:
                return int(match.group(1))
    return None


def spawn_detached(port: int, url: str, user_data_dir: str | None,
                   extensions_dir: str | None, show_media: bool,
                   log_file: Path, proxy: str | None = None,
                   proxy_bypass: str | None = None) -> int:
    """Launch a detached ``run`` child; return the launcher PID.

    The proxy URL travels in the child's environment (``PROXY_ENV_VAR``), not
    in its argv, so credentials stay out of process listings.
    """
    command = [
        sys.executable,
        "-m",
        "stealth_browser",
        "run",
        "--port",
        str(port),
        "--url",
        url,
    ]
    if user_data_dir:
        command += ["--user-data-dir", user_data_dir]
    if extensions_dir:
        command += ["--extensions-dir", extensions_dir]
    if show_media:
        command.append("--show-media")
    if proxy_bypass:
        command += ["--proxy-bypass", proxy_bypass]

    child_env = os.environ.copy()
    if proxy:
        child_env[PROXY_ENV_VAR] = proxy
    else:
        child_env.pop(PROXY_ENV_VAR, None)

    log_file.parent.mkdir(parents=True, exist_ok=True)
    log_handle = open(log_file, "ab")

    kwargs: dict[str, Any] = {
        "stdin": subprocess.DEVNULL,
        "stdout": log_handle,
        "stderr": log_handle,
        "env": child_env,
    }
    if os.name == "nt":
        kwargs["creationflags"] = (
            subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP
        )
    else:
        kwargs["start_new_session"] = True

    try:
        process = subprocess.Popen(command, **kwargs)
    finally:
        log_handle.close()
    return process.pid


def _kill_tree_windows(pid: int) -> None:
    subprocess.run(
        ["taskkill", "/PID", str(pid), "/T", "/F"],
        capture_output=True,
        text=True,
        check=False,
    )


def _kill_tree_posix(pid: int, force: bool) -> None:
    sig = signal.SIGKILL if force else signal.SIGTERM
    # ``os.getpgid(pid)`` returns the target's group, which is the caller's own
    # group for a foreground instance - killpg on it would terminate the shell
    # running ``stop``. Target the group only when it is a separate session
    # (as ``start`` creates via start_new_session); otherwise kill just the pid.
    try:
        pgid = os.getpgid(pid)
    except OSError:
        return
    if pgid != os.getpgrp():
        try:
            os.killpg(pgid, sig)
            return
        except (ProcessLookupError, PermissionError, OSError):
            pass
    try:
        os.kill(pid, sig)
    except (ProcessLookupError, PermissionError, OSError):
        pass


def kill_tree(pid: int, force: bool = False) -> None:
    """Terminate a process tree. Windows always force-kills (taskkill /F)."""
    if os.name == "nt":
        _kill_tree_windows(pid)
    else:
        _kill_tree_posix(pid, force=force)


def _pid_alive(pid: int) -> bool:
    """Whether a process with ``pid`` is still running.

    On Windows ``os.kill(pid, 0)`` is NOT a liveness probe (signals are
    emulated via ``TerminateProcess``), so use ``OpenProcess`` + exit code.
    """
    if pid <= 0:
        return False
    if os.name == "nt":
        return _pid_alive_windows(pid)
    try:
        os.kill(pid, 0)
        return True
    except ProcessLookupError:
        return False
    except PermissionError:
        # Process exists but belongs to another user.
        return True
    except OSError:
        return False


def _pid_alive_windows(pid: int) -> bool:
    import ctypes

    process_query_limited_information = 0x1000
    still_active = 259
    kernel32 = ctypes.windll.kernel32
    handle = kernel32.OpenProcess(process_query_limited_information, False, pid)
    if not handle:
        return False
    try:
        exit_code = ctypes.c_ulong()
        if not kernel32.GetExitCodeProcess(handle, ctypes.byref(exit_code)):
            return False
        return exit_code.value == still_active
    finally:
        kernel32.CloseHandle(handle)


def _command_line(pid: int) -> str:
    """Best-effort command line of a process (empty when unavailable)."""
    if os.name == "nt":
        out = _run_text(
            ["wmic", "process", "where", f"ProcessId={pid}", "get", "CommandLine"]
        )
        if not out:
            # wmic is deprecated/absent on newer Windows; fall back to CIM.
            out = _run_text(
                [
                    "powershell",
                    "-NoProfile",
                    "-Command",
                    f"(Get-CimInstance Win32_Process -Filter 'ProcessId={pid}').CommandLine",
                ]
            )
        return out
    # Linux exposes it via procfs; macOS/BSD have no /proc, so use ps.
    try:
        raw = Path(f"/proc/{pid}/cmdline").read_bytes()
        return raw.replace(b"\x00", b" ").decode("utf-8", "replace")
    except OSError:
        return _run_text(["ps", "-p", str(pid), "-o", "command="])


def _pid_matches_launcher(pid: int, port: int) -> bool:
    """Whether a recorded PID still looks like the launcher for ``port``.

    Guards the pid-file path of ``stop`` against PID reuse: after a reboot a
    recycled PID could otherwise point at an unrelated process and
    ``kill_tree`` would destroy it. Uninspectable command lines answer False.
    """
    text = _command_line(pid)
    if "stealth_browser" not in text:
        return False
    return re.search(rf"--port\s+{port}(?:\s|$)", text) is not None


def _run_text(command: list[str]) -> str:
    try:
        result = subprocess.run(
            command, capture_output=True, text=True, timeout=10, check=False
        )
    except (OSError, subprocess.SubprocessError):
        return ""
    return result.stdout.strip() if result.returncode == 0 else ""


def _read_pid(pid_file: Path) -> int | None:
    try:
        text = pid_file.read_text().strip()
    except OSError:
        return None
    return int(text) if text.isdigit() else None


def _remove_pid_file(pid_file: Path) -> None:
    try:
        pid_file.unlink()
    except OSError:
        pass


def _log_has_ready(log_file: Path, offset: int) -> bool:
    """Whether the child logged its readiness marker after ``offset``."""
    try:
        with open(log_file, "rb") as handle:
            handle.seek(offset)
            return "STEALTH_BROWSER_READY" in handle.read().decode("utf-8", "replace")
    except OSError:
        return False


def _tail(path: Path, lines: int) -> list[str]:
    """Last ``lines`` lines of a text file (empty if unreadable)."""
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return []
    return text.splitlines()[-lines:]


def _wait_until(predicate: Callable[[], bool], timeout: float) -> bool:
    """Poll ``predicate`` until true or timeout; return final state."""
    deadline = time.monotonic() + timeout
    while True:
        if predicate():
            return True
        if time.monotonic() >= deadline:
            return False
        time.sleep(_POLL_INTERVAL)


def cmd_start(port: int, url: str, user_data_dir: str | None,
              extensions_dir: str | None, show_media: bool,
              pid_file: str | Path | None, log_file: str | Path | None,
              proxy: str | None = None, proxy_bypass: str | None = None) -> int:
    """Start one instance on ``port``; refuse if the port is already in use."""
    if proxy:
        # Fail fast in the foreground instead of in the detached child's log.
        from .proxy import build_proxy_settings

        try:
            build_proxy_settings(proxy, proxy_bypass)
        except ValueError as error:
            print(f"ERROR: {error}", file=sys.stderr)
            return 1
    pid_file = Path(pid_file) if pid_file else default_pid_file(port)
    log_file = Path(log_file) if log_file else default_log_file(port)

    if cdp_alive(port):
        print(f"CDP already up on {port} (not launching a second instance)")
        existing = _read_pid(pid_file)
        if existing is not None:
            print(f"pid_file={existing}")
        return 0

    owner = port_owner_pid(port)
    if owner is not None:
        print(f"ERROR: port {port} is held by pid {owner} (not a CDP endpoint); "
              f"refusing to launch. Free the port or pick another.", file=sys.stderr)
        return 1

    # Capture the log size BEFORE spawning so the readiness scan starts at the
    # right offset (a previous run's READY line must not count).
    offset = log_file.stat().st_size if log_file.exists() else 0
    pid = spawn_detached(port, url, user_data_dir, extensions_dir, show_media, log_file,
                         proxy=proxy, proxy_bypass=proxy_bypass)
    pid_file.parent.mkdir(parents=True, exist_ok=True)
    pid_file.write_text(f"{pid}\n")
    print(f"launched pid={pid} (log: {log_file})")

    deadline = time.monotonic() + _READY_TIMEOUT
    while True:
        # The browser is really up when CDP answers AND the launcher logged
        # readiness. CDP answering alone can be a leftover probe or a proxy;
        # the readiness line (and a live launcher) is authoritative.
        if _log_has_ready(log_file, offset) and cdp_alive(port):
            print(f"CDP up on {port}")
            return 0
        if not _pid_alive(pid):
            print(f"ERROR: launcher exited before CDP came up on {port}; "
                  f"see {log_file} (last lines below)", file=sys.stderr)
            for line in _tail(log_file, 5):
                print(f"  {line}", file=sys.stderr)
            _remove_pid_file(pid_file)
            return 1
        if time.monotonic() >= deadline:
            break
        time.sleep(_POLL_INTERVAL)

    print(f"WARN: CDP not up yet on {port} after ~{int(_READY_TIMEOUT)}s; "
          f"check {log_file}", file=sys.stderr)
    return 1


def cmd_stop(port: int, pid_file: str | Path | None) -> int:
    """Stop the instance on ``port``.

    Order matters: terminate the CDP port owner (the browser) first, then let a
    detached launcher notice the closed context and exit on its own (running its
    cleanup, which removes a temporary profile). The recorded PID is force-killed
    only if it overstays, so graceful cleanup is not pre-empted.
    """
    pid_file = Path(pid_file) if pid_file else default_pid_file(port)
    stopped = False

    # Resolve and verify the recorded launcher BEFORE touching the port owner:
    # once the owner dies the launcher may exit on its own, after which its
    # command line can no longer be read (identity check would race).
    launcher = _read_pid(pid_file)
    launcher_is_ours = (
        launcher is not None
        and _pid_alive(launcher)
        and _pid_matches_launcher(launcher, port)
    )
    launcher_foreign = launcher is not None and _pid_alive(launcher) and not launcher_is_ours

    owner = port_owner_pid(port)
    if owner is not None:
        kill_tree(owner)
        stopped = True
        print(f"terminated CDP port owner pid={owner} (port {port})")
    else:
        print(f"no process owns port {port}")

    if launcher_is_ours:
        stopped = True
        # The owner is gone; let the launcher notice the closed context and exit
        # on its own (running cleanup, which removes a temporary profile).
        if _wait_until(lambda: not _pid_alive(launcher), _STOP_TIMEOUT):
            print(f"launcher pid={launcher} exited cleanly")
        else:
            kill_tree(launcher)
            print(f"terminated launcher pid={launcher}")
    elif launcher_foreign:
        print(f"pid {launcher} in {pid_file} is not this launcher; left alone")
    _remove_pid_file(pid_file)

    if not stopped:
        return 0

    if _wait_until(lambda: not cdp_alive(port), _STOP_TIMEOUT):
        print("CDP down")
        return 0

    # Escalate once on the port owner if it is still up.
    owner = port_owner_pid(port)
    if owner is not None:
        kill_tree(owner, force=True)
        _wait_until(lambda: not cdp_alive(port), _STOP_TIMEOUT)

    if cdp_alive(port):
        print(f"WARN: CDP still up on {port} after force kill; investigate manually.",
              file=sys.stderr)
        return 1
    print("CDP down")
    return 0


def cmd_status(port: int, pid_file: str | Path | None) -> int:
    """Report CDP liveness and the recorded launcher PID."""
    pid_file = Path(pid_file) if pid_file else default_pid_file(port)
    print(f"CDP {'up' if cdp_alive(port) else 'down'} on {port}")
    launcher = _read_pid(pid_file)
    if launcher is None:
        print("no pid file")
    elif not _pid_alive(launcher):
        print(f"pid={launcher} (not running)")
    elif _pid_matches_launcher(launcher, port):
        print(f"pid={launcher} (running)")
    else:
        print(f"pid={launcher} (pid reused; not this launcher)")
    return 0


def mcp_server_args(port: int) -> list[str]:
    """chrome-devtools-mcp launch args that attach to the stealth browser on
    ``port`` with Google usage statistics disabled (see MCP_PACKAGE)."""
    return [
        "npx",
        "-y",
        MCP_PACKAGE,
        f"--browserUrl=http://127.0.0.1:{port}",
        "--no-usage-statistics",
    ]


def cmd_mcp_config(port: int, name: str, fmt: str) -> int:
    """Print a ready-to-paste chrome-devtools-mcp config for ``port``.

    The MCP attaches to a running ``stealth-browser start --port <port>``; it
    does not launch its own browser. ``fmt`` selects the client schema.
    """
    args = mcp_server_args(port)
    if fmt == "opencode":
        block = {"mcp": {name: {"type": "local", "command": args, "enabled": True}}}
    elif fmt == "mcpServers":
        # Claude / Cursor / Kiro (.kiro/settings/mcp.json) shape.
        block = {"mcpServers": {name: {"command": args[0], "args": args[1:]}}}
    elif fmt == "args":
        print(" ".join(args))
        return 0
    else:
        print(f"ERROR: unknown format {fmt!r} (use: opencode, mcpServers, args)",
              file=sys.stderr)
        return 2
    print(json.dumps(block, indent=2))
    return 0
