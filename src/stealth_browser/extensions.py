"""Discovery of unpacked browser extensions."""

from __future__ import annotations

import logging
from pathlib import Path

logger = logging.getLogger(__name__)


def discover_extensions(extensions_dir: str | Path | None) -> list[Path]:
    """Return paths to all unpacked extensions in a directory.

    Args:
        extensions_dir: Directory with extensions. Extensions are not bundled
            with the library - the path is provided by the consumer. When
            ``None``, no extensions are loaded.

    Returns:
        List of ABSOLUTE paths to extension subdirectories (empty if the
        directory is not set or does not exist). Paths are resolved to absolute
        because Chromium resolves a relative ``--load-extension`` against its
        own binary directory (not the CWD), which would break loading.
    """
    if extensions_dir is None:
        logger.debug("Extensions directory not set - no extensions loaded.")
        return []
    base = Path(extensions_dir).resolve()
    if not base.is_dir():
        logger.warning("Extensions directory not found: %s", base)
        return []
    return sorted(item for item in base.iterdir() if item.is_dir())
