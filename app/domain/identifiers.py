"""Product reference generation and identifier utilities."""

from __future__ import annotations

import hashlib


def generate_product_ref(
    product_id: str | None = None,
    gid: str | None = None,
    data_docid: str | None = None,
    title: str | None = None,
    seller: str | None = None,
    url: str | None = None,
) -> str:
    """Generate a stable product_ref following the priority rules.

    Priority: product_id > gid > data_docid > fallback hash.
    """
    if product_id:
        return f"dfs:gshopping:pid:{product_id}"
    if gid:
        return f"dfs:gshopping:gid:{gid}"
    if data_docid:
        return f"dfs:gshopping:doc:{data_docid}"
    raw = f"{_norm(title)}|{_norm(seller)}|{_norm(url)}"
    h = hashlib.sha256(raw.encode()).hexdigest()[:16]
    return f"dfs:gshopping:fallback:{h}"


def _norm(v: str | None) -> str:
    return (v or "").strip().lower()


def parse_product_ref(ref: str) -> dict[str, str | None]:
    """Extract identifier type and value from a product_ref string."""
    parts = ref.split(":")
    if len(parts) < 4:
        return {"type": "unknown", "value": ref}
    id_type = parts[2]  # pid, gid, doc, fallback
    value = ":".join(parts[3:])
    return {"type": id_type, "value": value}
