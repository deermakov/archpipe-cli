"""Notation profile models and loader."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml


class ProfileError(Exception):
    """Profile loading or validation error."""


@dataclass(slots=True, frozen=True)
class PlantUMLTheme:
    """PlantUML visual settings."""

    background_color: str = "#FFFFFF"
    boundary_color: str = "#2E6171"
    line_color: str = "#1F2937"
    internal_bg: str = "#CCF6FB"
    external_bg: str = "#F2FDFF"
    text_color: str = "#111111"
    font_name: str = "Segoe UI"
    dpi: int = 160
    ranksep: int = 130
    nodesep: int = 70


@dataclass(slots=True, frozen=True)
class C4Theme:
    """Structurizr/C4 visual settings."""

    internal_bg: str = "#CCF6FB"
    external_bg: str = "#F2FDFF"
    text_color: str = "#111111"
    stroke_color: str = "#2E6171"
    auto_layout: str = "lr"


@dataclass(slots=True, frozen=True)
class ArchimateSettings:
    """ArchiMate export settings."""

    include_layer_properties: bool = True
    include_tag_properties: bool = True
    include_organizations: bool = True
    include_viewpoints_file: bool = True


@dataclass(slots=True, frozen=True)
class ViewSpec:
    """Declarative element/edge selection rules for a single view."""

    include_kinds: list[str] = field(default_factory=list)
    exclude_kinds: list[str] = field(default_factory=list)
    include_tags: list[str] = field(default_factory=list)
    exclude_tags: list[str] = field(default_factory=list)
    include_external: bool = True
    max_nodes: int = 20
    max_edges: int = 30


@dataclass(slots=True, frozen=True)
class DiagramSettings:
    """Cross-generator diagram rules (selection, limits, determinism)."""

    require_kind_tags: bool = True
    kind_tag_key: str = "kind"
    kind_fill_colors: dict[str, str] = field(default_factory=dict)
    views: dict[str, ViewSpec] = field(default_factory=dict)


@dataclass(slots=True, frozen=True)
class NotationProfile:
    """Top-level notation profile."""

    name: str
    plantuml: PlantUMLTheme = PlantUMLTheme()
    c4: C4Theme = C4Theme()
    archimate: ArchimateSettings = ArchimateSettings()
    diagram: DiagramSettings = DiagramSettings()


DEFAULT_PROFILE = NotationProfile(
    name="default",
    diagram=DiagramSettings(
        require_kind_tags=True,
        kind_tag_key="kind",
        kind_fill_colors={
            "client": "#FFF2CC",
            "process": "#CCF6FB",
            "read": "#DAE8FC",
            "data": "#F8CECC",
            "async": "#D5E8D4",
            "rules": "#E1D5E7",
            "product": "#F5F5F5",
            "ops": "#E7F5FF",
        },
        views={
            "context": ViewSpec(
                include_kinds=["client", "process", "read", "async", "rules", "product", "ops"],
                include_external=True,
                max_nodes=20,
                max_edges=30,
            ),
            "solution": ViewSpec(
                include_kinds=[
                    "client",
                    "process",
                    "rules",
                    "read",
                    "data",
                    "async",
                    "product",
                    "ops",
                ],
                include_external=True,
                max_nodes=30,
                max_edges=60,
            ),
            "data_async": ViewSpec(
                include_kinds=["data", "read", "process", "rules", "async", "product", "ops"],
                include_external=True,
                max_nodes=25,
                max_edges=50,
            ),
            # Primary end-to-end process flow.
            "flow_process": ViewSpec(
                include_kinds=["client", "process", "rules", "read", "async", "product", "ops"],
                include_external=True,
                max_nodes=20,
                max_edges=35,
            ),
            # Backward-compatible alias (do not document).
            "flow_renewal": ViewSpec(
                include_kinds=["client", "process", "rules", "read", "async", "product", "ops"],
                include_external=True,
                max_nodes=20,
                max_edges=35,
            ),
            "flow_ingestion": ViewSpec(
                include_kinds=["data", "read", "process", "rules", "ops"],
                include_external=True,
                max_nodes=20,
                max_edges=35,
            ),
            "operations": ViewSpec(
                include_kinds=["process", "async", "product", "ops"],
                include_external=True,
                max_nodes=20,
                max_edges=35,
            ),
        },
    ),
)


def load_profile(profile_ref: str | None) -> NotationProfile:
    """Load notation profile by name or YAML path."""
    if profile_ref is None or profile_ref == "default":
        return DEFAULT_PROFILE

    path = Path(profile_ref)
    if not path.exists():
        raise ProfileError(
            f"Profile '{profile_ref}' not found. Use 'default' or a path to YAML file.",
        )

    try:
        raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    except yaml.YAMLError as exc:
        raise ProfileError(f"Invalid profile YAML: {exc}") from exc

    if not isinstance(raw, dict):
        raise ProfileError("Profile YAML root must be a mapping/object.")

    return _build_profile(path, raw)


def _build_profile(path: Path, raw: dict[str, Any]) -> NotationProfile:
    name = _get_str(raw, "name", path.stem)

    plantuml_raw = _get_mapping(raw, "plantuml")
    c4_raw = _get_mapping(raw, "c4")
    archimate_raw = _get_mapping(raw, "archimate")
    diagram_raw = _get_mapping(raw, "diagram")

    plantuml = PlantUMLTheme(
        background_color=_get_str(plantuml_raw, "background_color", DEFAULT_PROFILE.plantuml.background_color),
        boundary_color=_get_str(plantuml_raw, "boundary_color", DEFAULT_PROFILE.plantuml.boundary_color),
        line_color=_get_str(plantuml_raw, "line_color", DEFAULT_PROFILE.plantuml.line_color),
        internal_bg=_get_str(plantuml_raw, "internal_bg", DEFAULT_PROFILE.plantuml.internal_bg),
        external_bg=_get_str(plantuml_raw, "external_bg", DEFAULT_PROFILE.plantuml.external_bg),
        text_color=_get_str(plantuml_raw, "text_color", DEFAULT_PROFILE.plantuml.text_color),
        font_name=_get_str(plantuml_raw, "font_name", DEFAULT_PROFILE.plantuml.font_name),
        dpi=_get_int(plantuml_raw, "dpi", DEFAULT_PROFILE.plantuml.dpi),
        ranksep=_get_int(plantuml_raw, "ranksep", DEFAULT_PROFILE.plantuml.ranksep),
        nodesep=_get_int(plantuml_raw, "nodesep", DEFAULT_PROFILE.plantuml.nodesep),
    )

    c4 = C4Theme(
        internal_bg=_get_str(c4_raw, "internal_bg", DEFAULT_PROFILE.c4.internal_bg),
        external_bg=_get_str(c4_raw, "external_bg", DEFAULT_PROFILE.c4.external_bg),
        text_color=_get_str(c4_raw, "text_color", DEFAULT_PROFILE.c4.text_color),
        stroke_color=_get_str(c4_raw, "stroke_color", DEFAULT_PROFILE.c4.stroke_color),
        auto_layout=_get_str(c4_raw, "auto_layout", DEFAULT_PROFILE.c4.auto_layout),
    )

    archimate = ArchimateSettings(
        include_layer_properties=_get_bool(
            archimate_raw,
            "include_layer_properties",
            DEFAULT_PROFILE.archimate.include_layer_properties,
        ),
        include_tag_properties=_get_bool(
            archimate_raw,
            "include_tag_properties",
            DEFAULT_PROFILE.archimate.include_tag_properties,
        ),
        include_organizations=_get_bool(
            archimate_raw,
            "include_organizations",
            DEFAULT_PROFILE.archimate.include_organizations,
        ),
        include_viewpoints_file=_get_bool(
            archimate_raw,
            "include_viewpoints_file",
            DEFAULT_PROFILE.archimate.include_viewpoints_file,
        ),
    )

    diagram = _build_diagram_settings(diagram_raw)

    return NotationProfile(name=name, plantuml=plantuml, c4=c4, archimate=archimate, diagram=diagram)


def _build_diagram_settings(raw: dict[str, Any]) -> DiagramSettings:
    require_kind_tags = _get_bool(raw, "require_kind_tags", DEFAULT_PROFILE.diagram.require_kind_tags)
    kind_tag_key = _get_str(raw, "kind_tag_key", DEFAULT_PROFILE.diagram.kind_tag_key)
    kind_fill_colors = _get_str_dict(
        raw,
        "kind_fill_colors",
        DEFAULT_PROFILE.diagram.kind_fill_colors,
    )
    views_raw = _get_mapping(raw, "views")

    views: dict[str, ViewSpec] = dict(DEFAULT_PROFILE.diagram.views)
    for view_name, view_payload in views_raw.items():
        if not isinstance(view_payload, dict):
            raise ProfileError(f"diagram.views.{view_name} must be an object.")
        views[view_name] = ViewSpec(
            include_kinds=_get_str_list(view_payload, "include_kinds", views.get(view_name, ViewSpec()).include_kinds),
            exclude_kinds=_get_str_list(view_payload, "exclude_kinds", views.get(view_name, ViewSpec()).exclude_kinds),
            include_tags=_get_str_list(view_payload, "include_tags", views.get(view_name, ViewSpec()).include_tags),
            exclude_tags=_get_str_list(view_payload, "exclude_tags", views.get(view_name, ViewSpec()).exclude_tags),
            include_external=_get_bool(view_payload, "include_external", views.get(view_name, ViewSpec()).include_external),
            max_nodes=_get_int(view_payload, "max_nodes", views.get(view_name, ViewSpec()).max_nodes),
            max_edges=_get_int(view_payload, "max_edges", views.get(view_name, ViewSpec()).max_edges),
        )

    return DiagramSettings(
        require_kind_tags=require_kind_tags,
        kind_tag_key=kind_tag_key,
        kind_fill_colors=kind_fill_colors,
        views=views,
    )


def _get_mapping(data: dict[str, Any], key: str) -> dict[str, Any]:
    value = data.get(key, {})
    if value is None:
        return {}
    if not isinstance(value, dict):
        raise ProfileError(f"Field '{key}' in profile must be an object.")
    return value


def _get_str(data: dict[str, Any], key: str, default: str) -> str:
    value = data.get(key, default)
    if not isinstance(value, str) or not value.strip():
        raise ProfileError(f"Field '{key}' must be a non-empty string.")
    return value


def _get_int(data: dict[str, Any], key: str, default: int) -> int:
    value = data.get(key, default)
    if isinstance(value, bool) or not isinstance(value, int):
        raise ProfileError(f"Field '{key}' must be an integer.")
    return value


def _get_bool(data: dict[str, Any], key: str, default: bool) -> bool:
    value = data.get(key, default)
    if not isinstance(value, bool):
        raise ProfileError(f"Field '{key}' must be a boolean.")
    return value


def _get_str_list(data: dict[str, Any], key: str, default: list[str]) -> list[str]:
    value = data.get(key, default)
    if value is None:
        return []
    if not isinstance(value, list) or any(not isinstance(item, str) for item in value):
        raise ProfileError(f"Field '{key}' must be a list of strings.")
    return [item.strip() for item in value if item.strip()]


def _get_str_dict(data: dict[str, Any], key: str, default: dict[str, str]) -> dict[str, str]:
    value = data.get(key, default)
    if value is None:
        return {}
    if not isinstance(value, dict):
        raise ProfileError(f"Field '{key}' must be an object mapping strings to strings.")
    parsed: dict[str, str] = {}
    for raw_key, raw_val in value.items():
        if not isinstance(raw_key, str) or not isinstance(raw_val, str):
            raise ProfileError(f"Field '{key}' must map strings to strings.")
        k = raw_key.strip().lower()
        v = raw_val.strip()
        if not k or not v:
            continue
        parsed[k] = v
    return parsed
