"""Tag parsing helpers for IR models.

Tags are stored as a list of strings in IR. We treat tags as case-insensitive and
support simple `key:value` pairs (e.g. `kind:process`, `scope:external`).
"""

from __future__ import annotations


def normalize_tag(tag: str) -> str:
    """Normalize tag for comparisons."""
    return " ".join(tag.strip().lower().split())


def get_tag_value(tags: list[str], key: str) -> str | None:
    """Return first `key:value` match from tags (case-insensitive)."""
    prefix = f"{key.strip().lower()}:"
    for raw in tags:
        tag = normalize_tag(raw)
        if tag.startswith(prefix):
            value = tag[len(prefix):].strip()
            return value or None
    return None


def has_tag(tags: list[str], needle: str) -> bool:
    """Check for an exact tag match (case-insensitive)."""
    wanted = normalize_tag(needle)
    return any(normalize_tag(tag) == wanted for tag in tags)


def is_external(tags: list[str]) -> bool:
    """Return True if tags mark an element as external."""
    return has_tag(tags, "external") or get_tag_value(tags, "scope") == "external"

