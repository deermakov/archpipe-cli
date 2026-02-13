"""Best-effort IR drafting from free-form HLD text."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import re
from typing import Any

import yaml

from archpipe.models.ir_schema import ElementType


@dataclass(slots=True)
class DraftResult:
    """Draft generation result."""

    ir_data: dict[str, Any]
    warnings: list[str]
    todo: list[str]


def generate_draft_ir(markdown: str) -> DraftResult:
    """Generate best-effort IR model from markdown text."""
    title = _extract_title(markdown)
    containers, warnings = _infer_containers(markdown)

    if not containers:
        containers = _fallback_containers()
        warnings.append(
            "Could not confidently infer architecture elements; inserted minimal defaults.",
        )

    relationships = _infer_relationships(containers)
    todo = _build_todo(containers, relationships)

    ir_data: dict[str, Any] = {
        "version": "1.0",
        "metadata": {
            "title": title,
            "description": "DRAFT - NOT GUARANTEED",
            "author": "archpipe draft-ir",
            "date": datetime.now(timezone.utc).date().isoformat(),
            "tags": ["draft", "not-guaranteed"],
        },
        "system": {
            "name": title,
            "description": "DRAFT - Derived from free-form HLD text",
        },
        "containers": containers,
        "relationships": relationships,
        "quality-attributes": [],
    }

    return DraftResult(ir_data=ir_data, warnings=warnings, todo=todo)


def render_ir_block(ir_data: dict[str, Any]) -> str:
    """Render IR data into archpipe-model fenced block."""
    yaml_text = yaml.safe_dump(ir_data, sort_keys=False, allow_unicode=False)
    return "\n".join(
        [
            "## Architecture Model (IR)",
            "",
            "```archpipe-model",
            "# DRAFT - NOT GUARANTEED",
            yaml_text.rstrip(),
            "```",
            "",
        ],
    )


def _extract_title(markdown: str) -> str:
    match = re.search(r"^#\s+(.+)$", markdown, flags=re.MULTILINE)
    if match:
        return match.group(1).strip()
    return "Draft Architecture"


def _infer_containers(markdown: str) -> tuple[list[dict[str, Any]], list[str]]:
    warnings: list[str] = []
    lower = markdown.lower()
    found: dict[str, tuple[str, ElementType]] = {}

    kebab_pattern = re.compile(
        r"\b([a-z][a-z0-9-]{1,40})-(service|api|gateway|db|database|queue|cache)\b",
    )
    title_pattern = re.compile(
        r"\b([A-Z][A-Za-z0-9]+(?:\s+[A-Z][A-Za-z0-9]+)*)\s+"
        r"(Service|API|Gateway|Database|Queue|Cache)\b",
    )

    for match in kebab_pattern.finditer(lower):
        base, kind = match.groups()
        identifier = f"{base}-{kind}"
        if identifier in found:
            continue
        name = " ".join(part.capitalize() for part in identifier.split("-"))
        found[identifier] = (name, _to_element_type(kind))

    for match in title_pattern.finditer(markdown):
        base, kind = match.groups()
        identifier = _slugify(f"{base}-{kind}")
        if identifier in found:
            continue
        name = f"{base} {kind}"
        found[identifier] = (name, _to_element_type(kind.lower()))

    containers: list[dict[str, Any]] = []
    for identifier, (name, element_type) in sorted(found.items()):
        containers.append(
            {
                "id": identifier,
                "name": name,
                "technology": "TODO",
                "description": "DRAFT - inferred from text",
                "type": element_type.value,
            },
        )

    if "database" in lower or "postgres" in lower or "mysql" in lower:
        has_db = any(c["type"] == ElementType.DATABASE.value for c in containers)
        if not has_db:
            containers.append(
                {
                    "id": "main-db",
                    "name": "Main Database",
                    "technology": "TODO",
                    "description": "DRAFT - inferred from text",
                    "type": ElementType.DATABASE.value,
                },
            )

    if containers:
        warnings.append(
            f"Inferred {len(containers)} container(s); verify IDs, technologies, and descriptions.",
        )

    return containers, warnings


def _infer_relationships(containers: list[dict[str, Any]]) -> list[dict[str, Any]]:
    if len(containers) < 2:
        return []

    relationships: list[dict[str, Any]] = []
    ids = [container["id"] for container in containers]

    non_db = [c for c in containers if c["type"] != ElementType.DATABASE.value]
    dbs = [c for c in containers if c["type"] == ElementType.DATABASE.value]

    if non_db and dbs:
        relationships.append(
            {
                "from": non_db[0]["id"],
                "to": dbs[0]["id"],
                "description": "DRAFT - inferred data access",
                "protocol": "TODO",
            },
        )

    for idx in range(len(ids) - 1):
        src = ids[idx]
        dst = ids[idx + 1]
        if any(r["from"] == src and r["to"] == dst for r in relationships):
            continue
        relationships.append(
            {
                "from": src,
                "to": dst,
                "description": "DRAFT - inferred dependency",
                "protocol": "TODO",
            },
        )

    return relationships


def _fallback_containers() -> list[dict[str, Any]]:
    return [
        {
            "id": "app",
            "name": "Application",
            "technology": "TODO",
            "description": "DRAFT - fallback application container",
            "type": ElementType.CONTAINER.value,
        },
        {
            "id": "db",
            "name": "Database",
            "technology": "TODO",
            "description": "DRAFT - fallback database container",
            "type": ElementType.DATABASE.value,
        },
    ]


def _build_todo(
    containers: list[dict[str, Any]],
    relationships: list[dict[str, Any]],
) -> list[str]:
    items: list[str] = [
        "Replace all `TODO` technology and protocol values.",
        "Validate every inferred container ID and name.",
        "Add external-systems and integrations if applicable.",
        "Add deployment-environments and quality-attributes.",
    ]

    if not relationships:
        items.append("Define at least one relationship between containers.")

    if len(containers) == 1:
        items.append("Add additional containers or external systems if system is distributed.")

    return items


def _slugify(value: str) -> str:
    lowered = value.lower().strip()
    lowered = re.sub(r"[^a-z0-9]+", "-", lowered)
    lowered = re.sub(r"-+", "-", lowered)
    return lowered.strip("-")


def _to_element_type(kind: str) -> ElementType:
    mapping = {
        "service": ElementType.CONTAINER,
        "api": ElementType.CONTAINER,
        "gateway": ElementType.CONTAINER,
        "db": ElementType.DATABASE,
        "database": ElementType.DATABASE,
        "queue": ElementType.QUEUE,
        "cache": ElementType.CACHE,
    }
    return mapping.get(kind.lower(), ElementType.CONTAINER)
