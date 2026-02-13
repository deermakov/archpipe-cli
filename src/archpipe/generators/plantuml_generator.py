"""PlantUML diagram generator."""

from __future__ import annotations

from collections import defaultdict
from pathlib import Path
from typing import Literal

from archpipe.generators.base import BaseGenerator
from archpipe.models.ir_schema import ElementType, IRModel, Integration, Relationship
from archpipe.models.profile import DEFAULT_PROFILE, NotationProfile
from archpipe.models.tags import get_tag_value, has_tag, is_external


ViewPack = Literal["draft", "review", "full"]


def _alias(value: str) -> str:
    sanitized = "".join(ch if ch.isalnum() else "_" for ch in value)
    sanitized = sanitized.strip("_")
    if not sanitized:
        sanitized = "node"
    if sanitized[0].isdigit():
        sanitized = f"id_{sanitized}"
    return sanitized


def _escape(value: str) -> str:
    return value.replace('"', "'")


def _wrap_label(text: str, max_chars: int) -> str:
    words = text.split()
    if not words:
        return text

    lines: list[str] = []
    current = words[0]
    for word in words[1:]:
        if len(current) + len(word) + 1 <= max_chars:
            current = f"{current} {word}"
        else:
            lines.append(current)
            current = word
    lines.append(current)

    return "\\n".join(lines)


def _short_label(text: str, max_words: int = 4, max_chars: int = 28) -> str:
    words = text.split()
    if not words:
        return text

    short = " ".join(words[:max_words])
    if len(short) <= max_chars:
        return short
    return f"{short[: max_chars - 1]}…"


def _is_async_link(protocol: str | None, patterns: list[str] | None = None) -> bool:
    proto = (protocol or "").strip().lower()
    if "async" in proto:
        return True
    if patterns:
        pat = {item.strip().lower() for item in patterns}
        return "async" in pat
    return False


def _plantuml_theme_lines(profile: NotationProfile) -> list[str]:
    theme = profile.plantuml
    return [
        f"skinparam backgroundColor {theme.background_color}",
        "skinparam shadowing false",
        f"skinparam defaultFontName {theme.font_name}",
        "skinparam componentStyle rectangle",
        "skinparam linetype polyline",
        f"skinparam ArrowColor {theme.line_color}",
        "skinparam ArrowThickness 1",
        f"skinparam ArrowFontColor {theme.text_color}",
        f"skinparam PackageBorderColor {theme.boundary_color}",
        f"skinparam PackageBackgroundColor {theme.external_bg}",
        f"skinparam ComponentBorderColor {theme.boundary_color}",
        f"skinparam ComponentBackgroundColor {theme.internal_bg}",
        f"skinparam ComponentFontColor {theme.text_color}",
        f"skinparam RectangleBorderColor {theme.boundary_color}",
        f"skinparam RectangleBackgroundColor {theme.internal_bg}",
        f"skinparam RectangleFontColor {theme.text_color}",
        f"skinparam DatabaseBorderColor {theme.boundary_color}",
        f"skinparam DatabaseBackgroundColor {theme.internal_bg}",
        f"skinparam DatabaseFontColor {theme.text_color}",
        f"skinparam ArtifactBorderColor {theme.boundary_color}",
        f"skinparam ArtifactBackgroundColor {theme.internal_bg}",
        f"skinparam ArtifactFontColor {theme.text_color}",
        f"skinparam NodeBorderColor {theme.boundary_color}",
        f"skinparam NodeBackgroundColor {theme.external_bg}",
        f"skinparam NodeFontColor {theme.text_color}",
        f"skinparam ranksep {theme.ranksep}",
        f"skinparam nodesep {theme.nodesep}",
        f"skinparam dpi {theme.dpi}",
    ]


class PlantUMLGenerator(BaseGenerator):
    """Generate PlantUML component/deployment diagrams."""

    name = "plantuml"

    def __init__(
        self,
        profile: NotationProfile | None = None,
        view_pack: ViewPack = "full",
        notation_mode: Literal["default", "standard"] = "default",
    ) -> None:
        self.profile = profile or DEFAULT_PROFILE
        self.view_pack = view_pack
        self.notation_mode = notation_mode

    def generate(self, model: IRModel, output_dir: Path, force: bool = False) -> list[Path]:
        base_dir = output_dir / "diagrams" / "plantuml"
        file_renderers: dict[str, tuple[Path, str]] = {
            "components": (base_dir / "components.puml", self._render_components_overview(model)),
            "components-full": (base_dir / "components-full.puml", self._render_components_full(model)),
            "full-system": (base_dir / "full-system.puml", self._render_components_full(model)),
            "data-stores": (base_dir / "data-stores.puml", self._render_data_stores(model)),
            "deployment": (base_dir / "deployment.puml", self._render_deployment(model)),
            "flow-process": (base_dir / "flow-process.puml", self._render_flow_process(model)),
            "flow-ingestion": (base_dir / "flow-ingestion.puml", self._render_flow_ingestion(model)),
            "legend": (base_dir / "relations-legend.md", self._render_relations_legend(model)),
        }
        if self.notation_mode == "standard":
            # Additional diagrams (do not replace the existing ones).
            file_renderers.update(
                {
                    "archimate-context": (
                        base_dir / "archimate-context.puml",
                        self._render_archimate_context(model),
                    ),
                    "archimate-container": (
                        base_dir / "archimate-container.puml",
                        self._render_archimate_container(model),
                    ),
                },
            )

        selected_keys = self._selected_diagrams(self.view_pack)
        if self.notation_mode == "standard":
            selected_keys.extend(["archimate-context", "archimate-container"])
        generated: list[Path] = []
        for key in selected_keys:
            target, content = file_renderers[key]
            self._write_file(target, content, force)
            generated.append(target)

        return generated

    def _selected_diagrams(self, view_pack: ViewPack) -> list[str]:
        mapping: dict[ViewPack, list[str]] = {
            "draft": [
                "components",
                "data-stores",
                "flow-process",
                "legend",
            ],
            "review": [
                "components",
                "full-system",
                "data-stores",
                "flow-process",
                "flow-ingestion",
                "deployment",
                "legend",
            ],
            "full": [
                "components",
                "components-full",
                "full-system",
                "data-stores",
                "deployment",
                "flow-process",
                "flow-ingestion",
                "legend",
            ],
        }
        return mapping[view_pack]

    def _render_components_overview(self, model: IRModel) -> str:
        internal = {
            container.id
            for container in model.containers
            if container.type != ElementType.DATABASE
        }
        include_ids = internal | {ext.id for ext in model.external_systems}

        element_kind = self._element_kind_map(model)
        relationships = [
            rel
            for rel in model.relationships
            if rel.from_id in include_ids and rel.to_id in include_ids
        ]
        # Exclude ops/audit nodes from overview to keep it readable.
        relationships = [
            rel
            for rel in relationships
            if element_kind.get(rel.from_id) != "ops" and element_kind.get(rel.to_id) != "ops"
        ]
        integrations = [
            integration
            for integration in model.integrations
            if integration.from_id in include_ids and integration.to_id in include_ids
        ]
        integrations = [
            integration
            for integration in integrations
            if element_kind.get(integration.from_id) != "ops" and element_kind.get(integration.to_id) != "ops"
        ]

        return self._render_component_diagram(
            model=model,
            title="Architecture Components (Overview)",
            include_ids=include_ids,
            relationships=relationships,
            integrations=integrations,
            include_protocol=False,
            label_mode="text",
            label_width=26,
        )

    def _render_components_full(self, model: IRModel) -> str:
        include_ids = {container.id for container in model.containers}
        include_ids.update(ext.id for ext in model.external_systems)

        return self._render_component_diagram(
            model=model,
            title="Architecture Components (Full)",
            include_ids=include_ids,
            relationships=model.relationships,
            integrations=model.integrations,
            include_protocol=False,
            label_mode="id_short",
            label_width=22,
        )

    def _render_data_stores(self, model: IRModel) -> str:
        relationships = [
            rel
            for rel in model.relationships
            if self._is_data_store_relation(model, rel)
        ]
        include_ids: set[str] = set()
        for rel in relationships:
            include_ids.add(rel.from_id)
            include_ids.add(rel.to_id)

        return self._render_component_diagram(
            model=model,
            title="Data Stores and Synchronization",
            include_ids=include_ids,
            relationships=relationships,
            integrations=[],
            include_protocol=False,
            label_mode="text",
            label_width=24,
        )

    def _render_flow_process(self, model: IRModel) -> str:
        # Prefer generic key; fallback to legacy key for older profiles.
        include_ids = self._select_ids_by_view(model, "flow_process") or self._select_ids_by_view(model, "flow_renewal")

        relationships = [
            rel
            for rel in model.relationships
            if rel.from_id in include_ids and rel.to_id in include_ids
        ]
        integrations = [
            integration
            for integration in model.integrations
            if integration.from_id in include_ids and integration.to_id in include_ids
        ]

        return self._render_component_diagram(
            model=model,
            title="Process Flow (Start -> Async -> Result)",
            include_ids=include_ids,
            relationships=relationships,
            integrations=integrations,
            include_protocol=False,
            label_mode="text",
            label_width=24,
        )

    def _render_flow_renewal(self, model: IRModel) -> str:
        # Backward-compatible alias for older view-pack mappings.
        return self._render_flow_process(model)

    def _render_flow_ingestion(self, model: IRModel) -> str:
        include_ids = self._select_ids_by_view(model, "flow_ingestion")

        relationships = [
            rel
            for rel in model.relationships
            if rel.from_id in include_ids and rel.to_id in include_ids
        ]
        integrations = [
            integration
            for integration in model.integrations
            if integration.from_id in include_ids and integration.to_id in include_ids
        ]

        return self._render_component_diagram(
            model=model,
            title="Ingestion Flow (Batch -> Canonical -> Read)",
            include_ids=include_ids,
            relationships=relationships,
            integrations=integrations,
            include_protocol=False,
            label_mode="text",
            label_width=24,
        )

    def _render_relations_legend(self, model: IRModel) -> str:
        id_to_name = {container.id: container.name for container in model.containers}
        id_to_name.update({ext.id: ext.name for ext in model.external_systems})

        lines: list[str] = [
            "# Relations Legend",
            "",
            "Use this table together with compact diagrams where edge labels are hidden.",
            "",
            "| ID | Kind | From | To | Description | Protocol |",
            "|---|---|---|---|---|---|",
        ]

        for idx, rel in enumerate(model.relationships, start=1):
            relation_id = f"R{idx:02d}"
            from_name = id_to_name.get(rel.from_id, rel.from_id)
            to_name = id_to_name.get(rel.to_id, rel.to_id)
            protocol = rel.protocol or "-"
            lines.append(
                "| "
                f"{relation_id} | relationship | {from_name} | {to_name} | "
                f"{_escape_markdown(rel.description)} | {_escape_markdown(protocol)} |",
            )

        for idx, integration in enumerate(model.integrations, start=1):
            relation_id = f"I{idx:02d}"
            from_name = id_to_name.get(integration.from_id, integration.from_id)
            to_name = id_to_name.get(integration.to_id, integration.to_id)
            description = integration.description or "Integration"
            protocol = integration.protocol or "-"
            lines.append(
                "| "
                f"{relation_id} | integration | {from_name} | {to_name} | "
                f"{_escape_markdown(description)} | {_escape_markdown(protocol)} |",
            )

        lines.extend([
            "",
            "## Notes",
            "",
            "- `Rxx` rows come from `relationships` section in IR.",
            "- `Ixx` rows come from `integrations` section in IR.",
            "- On full diagrams, edge labels use `ID + short text` to keep layout readable.",
            "",
        ])

        return "\n".join(lines)

    def _render_component_diagram(
        self,
        model: IRModel,
        title: str,
        include_ids: set[str],
        relationships: list[Relationship],
        integrations: list[Integration],
        include_protocol: bool,
        label_mode: str,
        label_width: int,
    ) -> str:
        # Stable ordering for deterministic outputs and stable Rxx/Ixx numbering.
        relationships = sorted(
            relationships,
            key=lambda item: (item.from_id, item.to_id, item.description, item.protocol or ""),
        )
        integrations = sorted(
            integrations,
            key=lambda item: (item.from_id, item.to_id, item.description or "", item.protocol or ""),
        )

        alias_map = self._build_alias_map(model)
        lines: list[str] = [
            "@startuml",
            f"title {title}",
            "left to right direction",
            *_plantuml_theme_lines(self.profile),
            "",
            f'package "{_escape(model.system.name)}" {{',
        ]

        for container in sorted(model.containers, key=lambda item: item.id):
            if container.id not in include_ids:
                continue
            stereotype = container.type.value
            keyword = self._container_keyword(container.type)
            alias = alias_map[container.id]
            lines.append(
                f'  {keyword} "{_escape(container.name)}" as {alias} <<{stereotype}>>',
            )

        lines.append("}")
        lines.append("")

        for ext in sorted(model.external_systems, key=lambda item: item.id):
            if ext.id not in include_ids:
                continue
            alias = alias_map[ext.id]
            lines.append(f'rectangle "{_escape(ext.name)}" as {alias} <<external>>')

        lines.append("")

        for idx, rel in enumerate(relationships, start=1):
            src = alias_map.get(rel.from_id, _alias(rel.from_id))
            dst = alias_map.get(rel.to_id, _alias(rel.to_id))
            arrow = "..>" if _is_async_link(rel.protocol, rel.patterns) else "-->"
            if label_mode == "text":
                label = self._relationship_label(
                    rel.description,
                    rel.protocol,
                    include_protocol,
                    label_width,
                )
                lines.append(f"{src} {arrow} {dst} : {label}")
            elif label_mode == "id_short":
                short = _short_label(rel.description)
                lines.append(f"{src} {arrow} {dst} : R{idx:02d} {short}")
            elif label_mode == "id":
                lines.append(f"{src} {arrow} {dst} : R{idx:02d}")
            else:
                lines.append(f"{src} {arrow} {dst}")

        for idx, integration in enumerate(integrations, start=1):
            src = alias_map.get(integration.from_id, _alias(integration.from_id))
            dst = alias_map.get(integration.to_id, _alias(integration.to_id))
            arrow = "..>" if _is_async_link(integration.protocol) else "-->"
            if label_mode == "text":
                label = self._relationship_label(
                    integration.description or "Integration",
                    integration.protocol,
                    include_protocol,
                    label_width,
                )
                lines.append(f"{src} {arrow} {dst} : {label}")
            elif label_mode == "id_short":
                short = _short_label(integration.description or "Integration")
                lines.append(f"{src} {arrow} {dst} : I{idx:02d} {short}")
            elif label_mode == "id":
                lines.append(f"{src} {arrow} {dst} : I{idx:02d}")
            else:
                lines.append(f"{src} {arrow} {dst}")

        lines.extend(["", "@enduml", ""])
        return "\n".join(lines)

    def _relationship_label(
        self,
        description: str,
        protocol: str | None,
        include_protocol: bool,
        label_width: int,
    ) -> str:
        label = _wrap_label(_escape(description), label_width)
        if include_protocol and protocol:
            protocol_line = _wrap_label(f"[{protocol}]", label_width)
            return f"{label}\\n{protocol_line}"
        return label

    def _is_data_store_relation(self, model: IRModel, relation: Relationship) -> bool:
        db_ids = {
            container.id
            for container in model.containers
            if container.type == ElementType.DATABASE
        }
        return relation.from_id in db_ids or relation.to_id in db_ids

    def _render_archimate_context(self, model: IRModel) -> str:
        """PlantUML ArchiMate-style context diagram (does not alter the IR model)."""
        alias_map = self._build_alias_map(model)

        subsystem_id = "subsystem"
        subsystem_name = model.system.name

        internal_ids = {c.id for c in model.containers}
        external_ids = {e.id for e in model.external_systems}

        # Collapse external<->internal relationships into external<->subsystem.
        edges: dict[tuple[str, str], list[str]] = defaultdict(list)
        for rel in model.relationships:
            if rel.from_id in external_ids and rel.to_id in internal_ids:
                edges[(rel.from_id, subsystem_id)].append(rel.protocol or "")
            elif rel.from_id in internal_ids and rel.to_id in external_ids:
                edges[(subsystem_id, rel.to_id)].append(rel.protocol or "")

        # Layout goals (per requirements):
        # - orthogonal lines (no curves),
        # - more spacing (do not compress),
        # - fewer crossings via explicit left/center/right columns.
        lines: list[str] = [
            "@startuml",
            "title ArchiMate (Context)",
            "left to right direction",
            "!include <archimate/Archimate>",
            "!theme archimate-standard from <archimate/themes>",
            "skinparam linetype ortho",
            "skinparam ranksep 220",
            "skinparam nodesep 140",
            "skinparam ArrowFontSize 10",
            "",
        ]

        externals_sorted = sorted(model.external_systems, key=lambda e: e.id)
        left_group: list[tuple[str, str]] = []
        right_group: list[tuple[str, str]] = []
        for ext in externals_sorted:
            macro = self._archimate_macro_for(ext.id, ext.tags, element_type=ext.type)
            alias = alias_map.get(ext.id, _alias(ext.id))
            kind = (get_tag_value(ext.tags, self.profile.diagram.kind_tag_key) or "").strip().lower()
            if kind in {"product"}:
                right_group.append((macro, alias))
            else:
                left_group.append((macro, alias))

        # External elements (left column).
        lines.append('package "External (Actors & Sources)" {')
        for ext in externals_sorted:
            kind = (get_tag_value(ext.tags, self.profile.diagram.kind_tag_key) or "").strip().lower()
            if kind == "product":
                continue
            macro = self._archimate_macro_for(ext.id, ext.tags, element_type=ext.type)
            alias = alias_map.get(ext.id, _alias(ext.id))
            lines.append(f'  {macro}({alias}, "{_escape(ext.name)}")')
        lines.append("}")
        lines.append("")

        # Subsystem as an application component (center column).
        lines.append(f'Application_Component({subsystem_id}, "{_escape(subsystem_name)}")')
        lines.append("")

        # External elements (right column).
        lines.append('package "External (Products)" {')
        for ext in externals_sorted:
            kind = (get_tag_value(ext.tags, self.profile.diagram.kind_tag_key) or "").strip().lower()
            if kind != "product":
                continue
            macro = self._archimate_macro_for(ext.id, ext.tags, element_type=ext.type)
            alias = alias_map.get(ext.id, _alias(ext.id))
            lines.append(f'  {macro}({alias}, "{_escape(ext.name)}")')
        lines.append("}")

        lines.append("")

        # Layout hints: keep 3 columns and stack externals vertically.
        left_aliases = [
            alias_map.get(ext.id, _alias(ext.id))
            for ext in externals_sorted
            if (get_tag_value(ext.tags, self.profile.diagram.kind_tag_key) or "").strip().lower() != "product"
        ]
        right_aliases = [
            alias_map.get(ext.id, _alias(ext.id))
            for ext in externals_sorted
            if (get_tag_value(ext.tags, self.profile.diagram.kind_tag_key) or "").strip().lower() == "product"
        ]
        if left_aliases:
            lines.append(f"{left_aliases[0]} -[hidden]-> {subsystem_id}")
            for a, b in zip(left_aliases, left_aliases[1:]):
                lines.append(f"{a} -down[hidden]-> {b}")
        if right_aliases:
            lines.append(f"{subsystem_id} -[hidden]-> {right_aliases[0]}")
            for a, b in zip(right_aliases, right_aliases[1:]):
                lines.append(f"{a} -down[hidden]-> {b}")

        lines.append("")

        for (src, dst), protos in sorted(edges.items(), key=lambda item: (item[0][0], item[0][1])):
            src_alias = src if src == subsystem_id else alias_map.get(src, _alias(src))
            dst_alias = dst if dst == subsystem_id else alias_map.get(dst, _alias(dst))
            label = _short_label(" / ".join(sorted({p for p in protos if p}))) if protos else ""
            rel_macro = "Rel_Flow"
            if any(p.strip().lower() == "async" for p in protos if p):
                rel_macro = "Rel_Flow"
            lines.append(f'{rel_macro}({src_alias}, {dst_alias}, "{_escape(label) if label else " "}")')

        lines.extend(["", "@enduml", ""])
        return "\n".join(lines)

    def _render_archimate_container(self, model: IRModel) -> str:
        """PlantUML ArchiMate-style container diagram based on the solution view selection."""
        alias_map = self._build_alias_map(model)
        include_ids = self._select_ids_by_view(model, "solution")

        internal = [c for c in model.containers if c.id in include_ids]
        external = [e for e in model.external_systems if e.id in include_ids]

        lines: list[str] = [
            "@startuml",
            "title ArchiMate (Container)",
            "!include <archimate/Archimate>",
            "!theme archimate-standard from <archimate/themes>",
            "skinparam backgroundColor #FFFFFF",
            "skinparam shadowing false",
            "skinparam defaultFontName Arial",
            "skinparam defaultFontSize 11",
            "skinparam linetype ortho",
            "skinparam ArrowColor #374151",
            "skinparam ArrowThickness 2",
            "skinparam ArrowFontColor #334155",
            "skinparam PackageBorderColor #6B7280",
            "skinparam PackageFontColor #1F2937",
            "skinparam PackageBackgroundColor #FFFFFF",
            "skinparam RectangleBorderColor #5B6B7A",
            "skinparam RectangleFontColor #0F172A",
            "skinparam ComponentBorderColor #5B6B7A",
            "skinparam ComponentFontColor #0F172A",
            "skinparam DatabaseBorderColor #5B6B7A",
            "skinparam DatabaseFontColor #0F172A",
            "skinparam ranksep 230",
            "skinparam nodesep 190",
            "skinparam packagePadding 90",
            "skinparam ArrowFontSize 10",
            "",
        ]

        # Split into internal domains and force column layout via hidden constraints.
        kind_key = self.profile.diagram.kind_tag_key
        left_kinds = {"read", "rules"}
        mid_kinds = {"process"}
        right_kinds = {"async"}

        internal_apps = [c for c in internal if c.type == ElementType.CONTAINER]
        internal_data = [c for c in internal if c.type == ElementType.DATABASE]
        internal_queue = [c for c in internal if c.type == ElementType.QUEUE]

        left_apps = [
            c for c in internal_apps
            if (get_tag_value(c.tags, kind_key) or "").strip().lower() in left_kinds
        ]
        mid_apps = [
            c for c in internal_apps
            if (get_tag_value(c.tags, kind_key) or "").strip().lower() in mid_kinds
        ]
        right_apps = [
            c for c in internal_apps
            if (get_tag_value(c.tags, kind_key) or "").strip().lower() in right_kinds
        ]
        other_apps = [
            c for c in internal_apps
            if c not in left_apps and c not in mid_apps and c not in right_apps
        ]
        left_apps.extend(sorted(other_apps, key=lambda c: c.id))

        def sort_by_preference(items: list, preferred_ids: list[str]) -> list:
            rank = {item_id: idx for idx, item_id in enumerate(preferred_ids)}
            fallback = len(preferred_ids)
            return sorted(items, key=lambda item: (rank.get(item.id, fallback), item.id))

        # Externals: left (actors/sources) vs right (products).
        left_ext = []
        right_ext = []
        for ext in sorted(external, key=lambda e: e.id):
            kind = (get_tag_value(ext.tags, kind_key) or "").strip().lower()
            (right_ext if kind == "product" else left_ext).append(ext)

        ordered_left_ext = sort_by_preference(
            left_ext,
            ["dwh-legacy", "dwh-impulse", "cpp-portal", "elm-system"],
        )
        ordered_read = sort_by_preference(
            left_apps,
            ["registry-read-api", "registry-projection", "catalog-projection", "precalc-hosted-executors"],
        )
        ordered_process = sort_by_preference(
            mid_apps,
            [
                "ingestion-service",
                "canonical-pipeline",
                "case-service",
                "precalc-orchestrator",
                "precalc-policy-runner",
                "renewal-scheduler",
            ],
        )
        ordered_async = sort_by_preference(
            right_apps + internal_queue,
            [
                "renewal-requests-topic",
                "renewal-results-topic",
                "precalc-requests-topic",
                "precalc-results-topic",
            ],
        )
        ordered_data = sort_by_preference(
            internal_data,
            [
                "canonical-store",
                "case-store",
                "eligibility-rules-store",
                "catalog-store",
                "registry-store",
                "precalc-capability-registry",
                "precalc-policy-registry",
                "precalc-store",
                "raw-staging-store",
                "data-quarantine",
            ],
        )
        ordered_right_ext = sort_by_preference(right_ext, ["impulse-products"])

        ext_left_pkg = "ext_left_pkg"
        hub_pkg = "renewal_hub_pkg"
        read_pkg = "read_rules_pkg"
        process_pkg = "process_pkg"
        async_pkg = "async_pkg"
        data_pkg = "data_pkg"
        ext_right_pkg = "ext_right_pkg"

        lines.append(f'package "External (Actors & Sources)" as {ext_left_pkg} {{')
        for ext in ordered_left_ext:
            macro = self._archimate_macro_for(ext.id, ext.tags, element_type=ext.type)
            alias = alias_map.get(ext.id, _alias(ext.id))
            lines.append(f'  {macro}({alias}, "{_escape(ext.name)}")')
        lines.append("}")
        lines.append("")

        lines.append(f'package "{_escape(model.system.name)}" as {hub_pkg} {{')
        lines.append(f'  package "Read + Rules" as {read_pkg} {{')
        for container in ordered_read:
            macro = self._archimate_macro_for(container.id, container.tags, element_type=container.type)
            alias = alias_map.get(container.id, _alias(container.id))
            lines.append(f'    {macro}({alias}, "{_escape(container.name)}")')
        lines.append("  }")
        lines.append("")

        lines.append(f'  package "Process (SoT)" as {process_pkg} {{')
        for container in ordered_process:
            macro = self._archimate_macro_for(container.id, container.tags, element_type=container.type)
            alias = alias_map.get(container.id, _alias(container.id))
            lines.append(f'    {macro}({alias}, "{_escape(container.name)}")')
        lines.append("  }")
        lines.append("")

        lines.append(f'  package "Async" as {async_pkg} {{')
        for container in ordered_async:
            macro = self._archimate_macro_for(container.id, container.tags, element_type=container.type)
            alias = alias_map.get(container.id, _alias(container.id))
            lines.append(f'    {macro}({alias}, "{_escape(container.name)}")')
        lines.append("  }")
        lines.append("")

        if internal_data:
            lines.append(f'  package "Data" as {data_pkg} {{')
            for container in ordered_data:
                macro = self._archimate_macro_for(container.id, container.tags, element_type=container.type)
                alias = alias_map.get(container.id, _alias(container.id))
                lines.append(f'    {macro}({alias}, "{_escape(container.name)}")')
            lines.append("  }")

        lines.append("}")
        lines.append("")

        lines.append(f'package "External (Products)" as {ext_right_pkg} {{')
        for ext in ordered_right_ext:
            macro = self._archimate_macro_for(ext.id, ext.tags, element_type=ext.type)
            alias = alias_map.get(ext.id, _alias(ext.id))
            lines.append(f'  {macro}({alias}, "{_escape(ext.name)}")')
        lines.append("}")
        lines.append("")

        # Layout hints (columns):
        # - keep explicit left->right anchor order to avoid vertical "drift",
        # - stack each column top-to-bottom to reduce random packing/crossings.
        def aliases(items: list) -> list[str]:
            return [alias_map.get(item.id, _alias(item.id)) for item in items]

        left_ext_aliases = aliases(ordered_left_ext)
        prod_aliases = aliases(ordered_right_ext)

        # Package-level anchors: compact, near-square arrangement without
        # over-constraining GraphViz (which hurts routing quality).
        if ordered_read:
            lines.append(f"{ext_left_pkg} -right[hidden]-> {read_pkg}")
        else:
            lines.append(f"{ext_left_pkg} -right[hidden]-> {hub_pkg}")
        if ordered_read and ordered_process:
            lines.append(f"{read_pkg} -right[hidden]-> {process_pkg}")
        if ordered_process and ordered_right_ext:
            lines.append(f"{process_pkg} -right[hidden]-> {ext_right_pkg}")
        elif ordered_read and ordered_right_ext:
            lines.append(f"{read_pkg} -right[hidden]-> {ext_right_pkg}")
        if ordered_process and ordered_async:
            lines.append(f"{process_pkg} -down[hidden]-> {async_pkg}")
        elif ordered_read and ordered_async:
            lines.append(f"{read_pkg} -down[hidden]-> {async_pkg}")
        if internal_data and ordered_read:
            lines.append(f"{read_pkg} -down[hidden]-> {data_pkg}")
        elif internal_data and ordered_process:
            lines.append(f"{process_pkg} -down[hidden]-> {data_pkg}")

        # Keep external actors stacked in a predictable order.
        for src, dst in zip(left_ext_aliases, left_ext_aliases[1:]):
            lines.append(f"{src} -down[hidden]-> {dst}")
        for src, dst in zip(prod_aliases, prod_aliases[1:]):
            lines.append(f"{src} -down[hidden]-> {dst}")
        lines.append("")

        for rel in model.relationships:
            if rel.from_id not in include_ids or rel.to_id not in include_ids:
                continue
            src = alias_map.get(rel.from_id, _alias(rel.from_id))
            dst = alias_map.get(rel.to_id, _alias(rel.to_id))
            macro = self._archimate_rel_macro(rel.protocol, rel.patterns)
            # Hide relation labels in this dense view to avoid overlaps and broken lines.
            label = " "
            lines.append(f'{macro}({src}, {dst}, "{_escape(label)}")')

        lines.extend(["", "@enduml", ""])
        return "\n".join(lines)

    def _archimate_macro_for(self, element_id: str, tags: list[str], element_type: ElementType) -> str:
        """Map IR kinds/types into PlantUML ArchiMate element macros."""
        kind_key = self.profile.diagram.kind_tag_key
        kind = (get_tag_value(tags, kind_key) or "").strip().lower()

        if kind == "client":
            return "Business_Actor"
        if kind == "product":
            return "Application_Component"
        if kind in {"read", "process", "rules", "async"}:
            # Treat infra (broker/adapter) as application components for MVP readability.
            return "Application_Component"

        if element_type == ElementType.DATABASE or kind == "data":
            return "Application_DataObject"
        if element_type == ElementType.QUEUE:
            return "Technology_Service"

        return "Application_Component"

    def _archimate_rel_macro(self, protocol: str | None, patterns: list[str] | None) -> str:
        proto = (protocol or "").strip().lower()
        pats = {p.strip().lower() for p in (patterns or [])}
        if "async" in proto or "async" in pats:
            return "Rel_Flow"
        if proto in {"read", "write"} or "read" in pats or "write" in pats:
            return "Rel_Access"
        return "Rel_Triggering"

    def _render_deployment(self, model: IRModel) -> str:
        alias_map = self._build_alias_map(model)
        internal_ids = {container.id for container in model.containers}
        external_names = {ext.id: ext.name for ext in model.external_systems}

        lines: list[str] = [
            "@startuml",
            "title Deployment View",
            "left to right direction",
            *_plantuml_theme_lines(self.profile),
            "",
        ]

        grouped: dict[str, list[str]] = defaultdict(list)
        for container in model.containers:
            platform = "Unspecified" if container.deployment is None else (
                container.deployment.platform or "Unspecified"
            )
            grouped[platform].append(container.id)

        artifact_aliases: dict[str, str] = {}
        for platform, ids in grouped.items():
            node_id = _alias(f"platform_{platform}")
            lines.append(f'node "{_escape(platform)}" as {node_id} {{')
            for container_id in ids:
                container = next(c for c in model.containers if c.id == container_id)
                artifact_alias = f"{alias_map[container_id]}_artifact"
                artifact_aliases[container_id] = artifact_alias
                lines.append(f'  artifact "{_escape(container.name)}" as {artifact_alias}')
            lines.append("}")
            lines.append("")

        declared_externals: set[str] = set()
        for relationship in model.relationships:
            source = self._deployment_ref(
                relationship.from_id,
                internal_ids,
                artifact_aliases,
                alias_map,
            )
            target = self._deployment_ref(
                relationship.to_id,
                internal_ids,
                artifact_aliases,
                alias_map,
            )

            self._declare_external_if_needed(
                lines,
                relationship.from_id,
                internal_ids,
                declared_externals,
                alias_map,
                external_names,
            )
            self._declare_external_if_needed(
                lines,
                relationship.to_id,
                internal_ids,
                declared_externals,
                alias_map,
                external_names,
            )

            lines.append(f"{source} --> {target}")

        lines.extend(["", "@enduml", ""])
        return "\n".join(lines)

    def _declare_external_if_needed(
        self,
        lines: list[str],
        element_id: str,
        internal_ids: set[str],
        declared_externals: set[str],
        alias_map: dict[str, str],
        external_names: dict[str, str],
    ) -> None:
        if element_id in internal_ids:
            return

        alias = alias_map.get(element_id, _alias(element_id))
        if alias in declared_externals:
            return

        display_name = external_names.get(element_id, element_id)
        lines.append(f'rectangle "{_escape(display_name)}" as {alias}')
        declared_externals.add(alias)

    def _deployment_ref(
        self,
        element_id: str,
        internal_ids: set[str],
        artifact_aliases: dict[str, str],
        alias_map: dict[str, str],
    ) -> str:
        if element_id in internal_ids:
            return artifact_aliases[element_id]
        return alias_map.get(element_id, _alias(element_id))

    def _build_alias_map(self, model: IRModel) -> dict[str, str]:
        ids: list[str] = sorted(container.id for container in model.containers)
        ids.extend(sorted(ext.id for ext in model.external_systems))

        alias_map: dict[str, str] = {}
        used: set[str] = set()

        for raw_id in ids:
            candidate = _alias(raw_id)
            alias = candidate
            suffix = 1
            while alias in used:
                suffix += 1
                alias = f"{candidate}_{suffix}"
            alias_map[raw_id] = alias
            used.add(alias)

        return alias_map

    def _container_keyword(self, element_type: ElementType) -> str:
        mapping = {
            ElementType.CONTAINER: "component",
            ElementType.DATABASE: "database",
            ElementType.QUEUE: "queue",
            ElementType.CACHE: "component",
            ElementType.COMPONENT: "component",
        }
        return mapping[element_type]

    def _element_kind_map(self, model: IRModel) -> dict[str, str | None]:
        kind_key = self.profile.diagram.kind_tag_key
        kinds: dict[str, str | None] = {}
        for container in model.containers:
            kinds[container.id] = get_tag_value(container.tags, kind_key)
        for ext in model.external_systems:
            kinds[ext.id] = get_tag_value(ext.tags, kind_key)
        return kinds

    def _select_ids_by_view(self, model: IRModel, view_name: str) -> set[str]:
        spec = self.profile.diagram.views.get(view_name)
        if spec is None:
            # Fallback: include everything.
            ids = {container.id for container in model.containers}
            ids.update(ext.id for ext in model.external_systems)
            return ids

        kind_key = self.profile.diagram.kind_tag_key
        include_kinds = set(spec.include_kinds)
        exclude_kinds = set(spec.exclude_kinds)
        include_external = spec.include_external
        include_tags = {tag.strip().lower() for tag in spec.include_tags}
        exclude_tags = {tag.strip().lower() for tag in spec.exclude_tags}

        selected: set[str] = set()

        def include_element(element_id: str, tags: list[str]) -> None:
            kind = get_tag_value(tags, kind_key)
            if kind in exclude_kinds:
                return
            if any(has_tag(tags, tag) for tag in exclude_tags):
                return
            if any(has_tag(tags, tag) for tag in include_tags):
                selected.add(element_id)
                return
            if is_external(tags) and include_external:
                selected.add(element_id)
                return
            if kind in include_kinds:
                selected.add(element_id)

        for container in model.containers:
            include_element(container.id, container.tags)
        for ext in model.external_systems:
            include_element(ext.id, ext.tags)

        return selected


def _escape_markdown(value: str) -> str:
    return value.replace("|", "\\|")
