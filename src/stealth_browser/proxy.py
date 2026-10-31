"""Proxy URL parsing for Patchright's ``proxy`` launch option."""

from __future__ import annotations

import re
from urllib.parse import quote, unquote, urlsplit

# Schemes Chromium accepts for a browser-wide proxy.
SUPPORTED_PROXY_SCHEMES: tuple[str, ...] = ("http", "https", "socks4", "socks5")

# Provider form ``host:port:user:password``. Host and user hold no ``:`` or
# ``@``; the password is the rest and may contain anything.
_PROVIDER_NETLOC = re.compile(r"(?P<host>[^:@\[\]/]+):(?P<port>\d+):(?P<username>[^:@]+):(?P<password>.+)")

# ``host:port`` after the last ``@`` marks the standard userinfo form, which
# wins over the provider form (e.g. ``user:1234:abc@host:8080``).
_STANDARD_HOST_PORT = re.compile(r"[^:@/\[\]]+:\d+/?")


def build_proxy_settings(proxy_url: str, bypass: str | None = None) -> dict[str, str]:
    """Convert a proxy URL into Playwright ``proxy`` settings.

    Error messages never include any part of ``proxy_url``, so a typo cannot
    print the password to a console or log.

    Args:
        proxy_url: ``scheme://[user:password@]host:port``, e.g.
            ``http://user:secret@1.2.3.4:8000``, or the provider form
            ``scheme://host:port:user:password``. In the ``@`` form, special
            characters in the username or password must be percent-encoded
            (``@`` -> ``%40``, ``:`` -> ``%3A``, ``/`` -> ``%2F``); they are
            decoded here. The provider form takes them raw (a trailing ``/``
            is dropped).
        bypass: Comma-separated hosts that skip the proxy, e.g.
            ``".example.com, localhost"``.

    Returns:
        A dict with ``server`` and, when present, ``username``, ``password``
        and ``bypass``.

    Raises:
        ValueError: If the URL is malformed, has no scheme, an unsupported
            scheme, no host, no port, an empty username, or credentials on a
            SOCKS proxy (Chromium cannot authenticate to SOCKS proxies).
    """
    text = proxy_url.strip()
    if "://" not in text:
        raise ValueError("proxy URL must include a scheme, e.g. http://host:port (value not shown)")

    try:
        parts = urlsplit(_normalize_provider_format(text))
        port = parts.port
        malformed = False
    except ValueError:
        # Raised below, outside the handler, so the original message (which
        # quotes the input) is not even kept as ``__context__``.
        malformed = True
    if malformed:
        raise ValueError(
            "proxy URL is malformed; percent-encode special characters in the "
            "user:password@ form (value not shown)"
        )

    scheme = parts.scheme.lower()
    if scheme not in SUPPORTED_PROXY_SCHEMES:
        raise ValueError(f"unsupported proxy scheme; use one of {', '.join(SUPPORTED_PROXY_SCHEMES)}")
    if not parts.hostname:
        raise ValueError("proxy URL has no host")
    if port is None:
        raise ValueError("proxy URL must include a port, e.g. http://host:8000")

    host = f"[{parts.hostname}]" if ":" in parts.hostname else parts.hostname
    settings = {"server": f"{scheme}://{host}:{port}"}

    if parts.username is not None or parts.password is not None:
        if scheme.startswith("socks"):
            raise ValueError(
                "Chromium does not support SOCKS proxy authentication; "
                "use an http:// proxy for username/password"
            )
        username = unquote(parts.username or "")
        if not username:
            # Playwright silently drops credentials without a username.
            raise ValueError("proxy username is empty")
        settings["username"] = username
        settings["password"] = unquote(parts.password or "")

    if bypass and bypass.strip():
        settings["bypass"] = bypass.strip()
    return settings


def _normalize_provider_format(proxy_url: str) -> str:
    """Rewrite ``scheme://host:port:user:password`` to ``scheme://user:password@host:port``.

    Proxy sellers often hand out credentials in the colon-separated form. A URL
    whose part after the last ``@`` is ``host:port`` (the standard form) or
    that has no credentials is returned unchanged.

    Args:
        proxy_url: A proxy URL that includes a scheme.

    Returns:
        The URL in standard userinfo form.
    """
    scheme, _, rest = proxy_url.partition("://")
    if "@" in rest and _STANDARD_HOST_PORT.fullmatch(rest.rpartition("@")[2]):
        return proxy_url
    # A proxy URL has no meaningful path, so the whole rest is the netloc and
    # a raw password may even contain "/".
    match = _PROVIDER_NETLOC.fullmatch(rest.rstrip("/"))
    if match is None:
        return proxy_url
    # Raw credentials: encode them so urlsplit sees one userinfo block;
    # build_proxy_settings decodes them back.
    username = quote(match["username"], safe="")
    password = quote(match["password"], safe="")
    return f"{scheme}://{username}:{password}@{match['host']}:{match['port']}"
