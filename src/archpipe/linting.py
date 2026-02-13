"""Architecture lint checks for validated IR models."""

from __future__ import annotations

from collections import Counter
from pathlib import Path
import re

from archpipe.models.ir_schema import IRModel
from archpipe.models.profile import DEFAULT_PROFILE, NotationProfile
from archpipe.models.tags import get_tag_value, has_tag, is_external
from archpipe.models.validation import (
    ValidationIssue,
    ValidationLevel,
    ValidationLocation,
)


_ID_PATTERN = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
_PLACEHOLDER_TECH = {"n/a", "na", "unknown", "tbd", "todo", "-", "none"}


def run_lint_checks(
    hld_file: Path,
    model: IRModel,
    block_start_line: int,
    profile: NotationProfile | None = None,
    view_pack: str = "full",
) -> list[ValidationIssue]:
    """Run lint checks that improve readability and maintainability."""
    profile = profile or DEFAULT_PROFILE
    issues: list[ValidationIssue] = []
    location = ValidationLocation(
        file=str(hld_file),
        line=block_start_line,
        block="archpipe-model",
    )

    for raw_id in _iter_all_ids(model):
        if not _ID_PATTERN.match(raw_id):
            issues.append(
                ValidationIssue(
                    level=ValidationLevel.WARNING,
                    code="L001",
                    message=(
                        f"ID '{raw_id}' is not kebab-case. "
                        "Use lowercase letters, digits and '-' only."
                    ),
                    location=location,
                    suggestion="Rename id to kebab-case for stable references.",
                ),
            )

    issues.extend(_lint_kind_tags(model, profile, location))
    issues.extend(_lint_solution_gates(model, profile, location))
    issues.extend(_lint_view_limits(model, profile, location, view_pack=view_pack))

    for container in model.containers:
        if container.technology.strip().lower() in _PLACEHOLDER_TECH:
            issues.append(
                ValidationIssue(
                    level=ValidationLevel.WARNING,
                    code="L002",
                    message=f"Container '{container.id}' has placeholder technology value.",
                    location=location,
                    suggestion="Specify concrete technology stack.",
                ),
            )

    for relationship in model.relationships:
        if len(relationship.description.strip()) < 10:
            issues.append(
                ValidationIssue(
                    level=ValidationLevel.WARNING,
                    code="L003",
                    message=(
                        f"Relationship '{relationship.from_id} -> {relationship.to_id}' "
                        "has too short description."
                    ),
                    location=location,
                    suggestion="Use an action-oriented description (at least 10 characters).",
                ),
            )

    if not model.metadata.author:
        issues.append(
            ValidationIssue(
                level=ValidationLevel.WARNING,
                code="L004",
                message="metadata.author is missing.",
                location=location,
                suggestion="Set document owner in metadata.author.",
            ),
        )

    if not model.metadata.date:
        issues.append(
            ValidationIssue(
                level=ValidationLevel.WARNING,
                code="L005",
                message="metadata.date is missing.",
                location=location,
                suggestion="Set ISO date (YYYY-MM-DD) in metadata.date.",
            ),
        )

    outgoing = Counter(rel.from_id for rel in model.relationships)
    outgoing.update(integration.from_id for integration in model.integrations)
    for element_id, count in outgoing.items():
        if count > 8:
            issues.append(
                ValidationIssue(
                    level=ValidationLevel.WARNING,
                    code="L006",
                    message=f"Element '{element_id}' has high fan-out ({count} outgoing links).",
                    location=location,
                    suggestion=(
                        "Consider split into focused diagrams or add integration boundaries."
                    ),
                ),
            )

    return issues


def _iter_all_ids(model: IRModel) -> list[str]:
    ids = [container.id for container in model.containers]
    ids.extend(component.id for container in model.containers for component in container.components)
    ids.extend(external.id for external in model.external_systems)
    return ids


def _lint_kind_tags(
    model: IRModel,
    profile: NotationProfile,
    location: ValidationLocation,
) -> list[ValidationIssue]:
    issues: list[ValidationIssue] = []
    kind_key = profile.diagram.kind_tag_key

    allowed_kinds: set[str] = set(profile.diagram.kind_fill_colors.keys())
    for spec in profile.diagram.views.values():
        allowed_kinds.update(spec.include_kinds)
        allowed_kinds.update(spec.exclude_kinds)
    allowed_kinds.discard("")

    def check_element(element_id: str, tags: list[str]) -> None:
        kind = get_tag_value(tags, kind_key)
        if not kind:
            level = ValidationLevel.ERROR if profile.diagram.require_kind_tags else ValidationLevel.WARNING
            issues.append(
                ValidationIssue(
                    level=level,
                    code="L100",
                    message=f"Element '{element_id}' is missing required tag '{kind_key}:<kind>'.",
                    location=location,
                    suggestion=(
                        "Add kind tag, e.g. kind:client|read|process|data|async|rules|product|ops."
                    ),
                ),
            )
            return
        if allowed_kinds and kind not in allowed_kinds:
            issues.append(
                ValidationIssue(
                    level=ValidationLevel.ERROR if profile.diagram.require_kind_tags else ValidationLevel.WARNING,
                    code="L101",
                    message=f"Element '{element_id}' has unknown kind '{kind}'.",
                    location=location,
                    suggestion=f"Use one of: {', '.join(sorted(allowed_kinds))}.",
                ),
            )

    for container in model.containers:
        check_element(container.id, container.tags)
    for external in model.external_systems:
        check_element(external.id, external.tags)

    return issues


def _lint_solution_gates(
    model: IRModel,
    profile: NotationProfile,
    location: ValidationLocation,
) -> list[ValidationIssue]:
    """Domain-agnostic quality gates driven by tags/patterns."""
    issues: list[ValidationIssue] = []
    kind_key = profile.diagram.kind_tag_key

    element_tags: dict[str, list[str]] = {c.id: c.tags for c in model.containers}
    element_tags.update({e.id: e.tags for e in model.external_systems})

    def kind_of(element_id: str) -> str | None:
        return get_tag_value(element_tags.get(element_id, []), kind_key)

    # SoT status owner (exactly one recommended; at least one required).
    sot_candidates = [
        element_id
        for element_id, tags in element_tags.items()
        if has_tag(tags, "role:sot-status")
    ]
    if not sot_candidates:
        issues.append(
                ValidationIssue(
                    level=ValidationLevel.ERROR,
                    code="L200",
                    message="No single source of truth (SoT) for process status defined (missing tag 'role:sot-status').",
                    location=location,
                    suggestion="Mark the process/status owner (e.g. process-service) with tag role:sot-status.",
                ),
            )
    elif len(sot_candidates) > 1:
        issues.append(
            ValidationIssue(
                level=ValidationLevel.ERROR,
                code="L201",
                message=f"Multiple SoT candidates found: {', '.join(sorted(sot_candidates))}.",
                location=location,
                suggestion="Keep exactly one role:sot-status element to avoid split-brain statuses.",
            ),
        )

    # PII in async links.
    for rel in model.relationships:
        protocol = (rel.protocol or "").lower()
        patterns = {p.strip().lower() for p in rel.patterns}
        is_async = "async" in protocol or "async" in patterns
        if is_async and "pii" in patterns and "no_pii" not in patterns:
            issues.append(
                ValidationIssue(
                    level=ValidationLevel.ERROR,
                    code="L202",
                    message=f"PII is forbidden in async relationship: {rel.from_id} -> {rel.to_id}.",
                    location=location,
                    suggestion="Remove PII from async payloads or tokenize; mark relationship patterns with no_pii.",
                ),
            )

    # Offline legacy calls: if one side is legacy, protocol/pattern must be batch.
    legacy_ids = {
        element_id
        for element_id, tags in element_tags.items()
        if has_tag(tags, "legacy") or has_tag(tags, "role:legacy")
    }
    for rel in model.relationships:
        if rel.from_id not in legacy_ids and rel.to_id not in legacy_ids:
            continue
        protocol = (rel.protocol or "").lower()
        patterns = {p.strip().lower() for p in rel.patterns}
        if "batch" not in protocol and "etl" not in protocol and "file" not in protocol and "batch" not in patterns:
            issues.append(
                ValidationIssue(
                    level=ValidationLevel.ERROR,
                    code="L203",
                    message=f"Legacy integration must be offline batch: {rel.from_id} -> {rel.to_id}.",
                    location=location,
                    suggestion="Use protocol Batch/ETL/File and avoid online sync calls to legacy.",
                ),
            )

    # Read model should not be the writer.
    write_patterns = {"write", "update", "delete", "create"}
    for rel in model.relationships:
        patterns = {p.strip().lower() for p in rel.patterns}
        if not (patterns & write_patterns):
            continue
        from_kind = kind_of(rel.from_id)
        if from_kind == "read":
            issues.append(
                ValidationIssue(
                    level=ValidationLevel.ERROR,
                    code="L204",
                    message=f"Read-model element writes data: {rel.from_id} -> {rel.to_id}.",
                    location=location,
                    suggestion="Write operations must be owned by process/data pipeline components, not read models.",
                ),
            )

    return issues


def _lint_view_limits(
    model: IRModel,
    profile: NotationProfile,
    location: ValidationLocation,
    view_pack: str,
) -> list[ValidationIssue]:
    issues: list[ValidationIssue] = []
    kind_key = profile.diagram.kind_tag_key

    element_meta: dict[str, tuple[str | None, bool]] = {}
    for container in model.containers:
        kind = get_tag_value(container.tags, kind_key)
        element_meta[container.id] = (kind, is_external(container.tags))
    for external in model.external_systems:
        kind = get_tag_value(external.tags, kind_key)
        element_meta[external.id] = (kind, True)

    def select_ids(view_name: str, spec: object) -> set[str]:
        include_kinds = set(getattr(spec, "include_kinds", []))
        exclude_kinds = set(getattr(spec, "exclude_kinds", []))
        include_external = bool(getattr(spec, "include_external", True))

        selected: set[str] = set()
        for element_id, (kind, external) in element_meta.items():
            if kind in exclude_kinds:
                continue
            if external and include_external:
                selected.add(element_id)
                continue
            if kind in include_kinds:
                selected.add(element_id)
        return selected

    view_names = _view_names_for_pack(profile, view_pack)
    for view_name in view_names:
        spec = profile.diagram.views.get(view_name)
        if spec is None:
            continue
        selected = select_ids(view_name, spec)
        rels = [
            rel
            for rel in model.relationships
            if rel.from_id in selected and rel.to_id in selected
        ]
        max_nodes = int(getattr(spec, "max_nodes", 20))
        max_edges = int(getattr(spec, "max_edges", 30))
        if len(selected) > max_nodes or len(rels) > max_edges:
            issues.append(
                ValidationIssue(
                    level=ValidationLevel.ERROR,
                    code="L300",
                    message=(
                        f"View '{view_name}' exceeds readability limits: "
                        f"{len(selected)} nodes/{len(rels)} edges (max {max_nodes}/{max_edges})."
                    ),
                    location=location,
                    suggestion="Reduce scope, split view, or adjust diagram.views.* limits in profile.",
                ),
            )

    return issues


def _view_names_for_pack(profile: NotationProfile, view_pack: str) -> list[str]:
    """Return view names that must satisfy readability limits for a given view-pack."""
    pack = (view_pack or "full").strip().lower()
    if pack == "draft":
        candidates = ["context", "solution"]
    elif pack == "review":
        candidates = [
            "context",
            "solution",
            "data_async",
            "flow_process",
            "flow_renewal",
            "flow_ingestion",
            "operations",
        ]
    else:
        # Full pack: enforce everything declared in profile.
        candidates = list(profile.diagram.views.keys())

    return [name for name in candidates if name in profile.diagram.views]
