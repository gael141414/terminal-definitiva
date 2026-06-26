from __future__ import annotations

import base64
import re
from pathlib import Path


VISUAL_PREFIX_PATTERN = re.compile(r"^[^A-Za-zÁÉÍÓÚÜÑáéíóúüñ0-9]+")


def asset_to_data_uri(path: Path) -> str:
    """Convert a local image asset into a data URI for stable CSS/HTML usage."""

    try:
        if not path.exists():
            return ""

        suffix = path.suffix.lower()
        if suffix == ".png":
            mime = "image/png"
        elif suffix in {".jpg", ".jpeg"}:
            mime = "image/jpeg"
        elif suffix == ".webp":
            mime = "image/webp"
        elif suffix == ".svg":
            mime = "image/svg+xml"
        else:
            mime = "application/octet-stream"

        encoded = base64.b64encode(path.read_bytes()).decode("utf-8")
        return f"data:{mime};base64,{encoded}"
    except Exception:
        return ""


def strip_visual_prefix(texto: str) -> str:
    """Remove emoji/symbol prefixes from legacy labels without changing router keys."""

    limpio = VISUAL_PREFIX_PATTERN.sub("", texto or "").strip()
    return limpio or texto
