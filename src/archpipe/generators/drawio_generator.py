"""draw.io (mxGraph) generator."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
import xml.etree.ElementTree as ET

from archpipe.generators.base import BaseGenerator
from archpipe.models.ir_schema import ElementType, IRModel
from archpipe.models.profile import DEFAULT_PROFILE, NotationProfile
from archpipe.models.tags import get_tag_value, has_tag, is_external


@dataclass(slots=True)
class DrawNode:
    """Element placed on draw.io canvas."""

    id: str
    name: str
    technology: str
    kind: str
    element_type: ElementType
    external: bool = False
    tags: list[str] = field(default_factory=list)


@dataclass(slots=True)
class DrawEdge:
    """Relationship placed on draw.io canvas."""

    from_id: str
    to_id: str
    label: str
    async_flow: bool = False


@dataclass(slots=True)
class DrawPage:
    """Single draw.io page definition."""

    page_id: str
    name: str
    nodes: list[DrawNode]
    edges: list[DrawEdge]
    kind_order: list[str]
    notation: str = "default"


class DrawIOGenerator(BaseGenerator):
    """Generate editable draw.io file with multiple pages."""

    name = "drawio"

    def __init__(
        self,
        profile: NotationProfile | None = None,
        view_pack: str = "full",
        reproducible: bool = False,
        notation_mode: str = "default",
    ) -> None:
        self.profile = profile or DEFAULT_PROFILE
        self.view_pack = view_pack
        self.reproducible = reproducible
        self.notation_mode = notation_mode

    def generate(self, model: IRModel, output_dir: Path, force: bool = False) -> list[Path]:
        drawio_dir = output_dir / "diagrams" / "drawio"
        drawio_path = drawio_dir / "architecture.drawio"

        self._write_file(drawio_path, self._render_drawio(model), force)
        return [drawio_path]

    def _render_drawio(self, model: IRModel) -> str:
        modified = (
            "1970-01-01T00:00:00Z"
            if self.reproducible
            else datetime.now(timezone.utc).replace(microsecond=0).isoformat()
        )
        root = ET.Element(
            "mxfile",
            {
                "host": "app.diagrams.net",
                "modified": modified,
                "agent": "archpipe-cli",
                "version": "24.7.17",
                "type": "device",
            },
        )

        for page in self._build_pages(model):
            diagram = ET.SubElement(root, "diagram", {"id": page.page_id, "name": page.name})
            diagram.append(self._build_page_graph(page))

        ET.indent(root, space="  ")
        xml = ET.tostring(root, encoding="unicode")
        return '<?xml version="1.0" encoding="UTF-8"?>\n' + xml + "\n"

    def _build_pages(self, model: IRModel) -> list[DrawPage]:
        nodes = self._collect_nodes(model)
        edges = self._collect_edges(model)

        available_views = self.profile.diagram.views
        view_pack = self.view_pack
        if view_pack not in {"draft", "review", "full"}:
            view_pack = "full"

        # draw.io always stays editable. View-pack controls how many pages we include.
        page_keys: list[str]
        if view_pack == "draft":
            page_keys = ["context", "solution"]
        else:
            page_keys = ["context", "solution", "data_async", "flow_process", "flow_ingestion", "operations"]

        pages: list[DrawPage] = []
        if self.notation_mode == "standard":
            pages.extend(self._build_c4_pages(model, nodes, edges))
        for key in page_keys:
            spec = available_views.get(key)
            if spec is None:
                continue
            page_nodes = self._select_nodes(nodes, spec)
            page_edges = self._filter_edges(edges, page_nodes)
            pages.append(
                DrawPage(
                    page_id=f"drawio-{key.replace('_', '-')}",
                    name=_page_title(key),
                    nodes=page_nodes,
                    edges=page_edges,
                    kind_order=list(spec.include_kinds),
                ),
            )
        return pages

    def _collect_nodes(self, model: IRModel) -> list[DrawNode]:
        nodes: list[DrawNode] = []
        kind_key = self.profile.diagram.kind_tag_key
        for container in sorted(model.containers, key=lambda item: item.id):
            kind = get_tag_value(container.tags, kind_key) or "other"
            external = is_external(container.tags)
            nodes.append(
                DrawNode(
                    id=container.id,
                    name=container.name,
                    technology=container.technology,
                    kind=kind,
                    element_type=container.type,
                    external=external,
                    tags=list(container.tags),
                ),
            )
        for external in sorted(model.external_systems, key=lambda item: item.id):
            kind = get_tag_value(external.tags, kind_key) or "other"
            nodes.append(
                DrawNode(
                    id=external.id,
                    name=external.name,
                    technology=external.technology or "External System",
                    kind=kind,
                    element_type=external.type,
                    external=True,
                    tags=list(external.tags),
                ),
            )
        return nodes

    def _collect_edges(self, model: IRModel) -> list[DrawEdge]:
        edges: list[DrawEdge] = []
        for rel in sorted(
            model.relationships,
            key=lambda item: (item.from_id, item.to_id, item.description, item.protocol or ""),
        ):
            label = _edge_label(rel.description, rel.protocol)
            async_flow = (rel.protocol or "").strip().lower() == "async" or any(
                pattern.strip().lower() == "async" for pattern in rel.patterns
            )
            edges.append(
                DrawEdge(
                    from_id=rel.from_id,
                    to_id=rel.to_id,
                    label=label,
                    async_flow=async_flow,
                ),
            )
        for rel in sorted(
            model.integrations,
            key=lambda item: (item.from_id, item.to_id, item.description or "", item.protocol or ""),
        ):
            label = _edge_label(rel.description or "Integration", rel.protocol)
            edges.append(
                DrawEdge(
                    from_id=rel.from_id,
                    to_id=rel.to_id,
                    label=label,
                    async_flow=(rel.protocol or "").strip().lower() == "async",
                ),
            )
        return edges

    def _filter_edges(self, edges: list[DrawEdge], nodes: list[DrawNode]) -> list[DrawEdge]:
        known_ids = {node.id for node in nodes}
        return [edge for edge in edges if edge.from_id in known_ids and edge.to_id in known_ids]

    def _select_nodes(self, nodes: list[DrawNode], spec: object) -> list[DrawNode]:
        # ViewSpec is defined in profile.py. We keep this loosely typed to avoid import cycles.
        include_kinds = set(getattr(spec, "include_kinds", []))
        exclude_kinds = set(getattr(spec, "exclude_kinds", []))
        include_tags = {tag.strip().lower() for tag in getattr(spec, "include_tags", [])}
        exclude_tags = {tag.strip().lower() for tag in getattr(spec, "exclude_tags", [])}
        include_external = bool(getattr(spec, "include_external", True))

        selected: list[DrawNode] = []
        for node in nodes:
            if node.kind in exclude_kinds:
                continue
            if any(has_tag(node.tags, tag) for tag in exclude_tags):
                continue
            if any(has_tag(node.tags, tag) for tag in include_tags):
                selected.append(node)
                continue
            if node.external and include_external:
                selected.append(node)
                continue
            if node.kind in include_kinds:
                selected.append(node)
                continue

        # Stable order for deterministic layouts.
        kind_order = {kind: idx for idx, kind in enumerate(getattr(spec, "include_kinds", []))}
        return sorted(
            selected,
            key=lambda item: (
                kind_order.get(item.kind, 999),
                item.external,
                item.name.lower(),
                item.id,
            ),
        )

    def _build_page_graph(self, page: DrawPage) -> ET.Element:
        graph = ET.Element(
            "mxGraphModel",
            {
                "dx": "1684",
                "dy": "962",
                "grid": "1",
                "gridSize": "10",
                "guides": "1",
                "tooltips": "1",
                "connect": "1",
                "arrows": "1",
                "fold": "1",
                "page": "1",
                "pageScale": "1",
                "pageWidth": "2200",
                "pageHeight": "1400",
                "math": "0",
                "shadow": "0",
            },
        )
        root = ET.SubElement(graph, "root")
        ET.SubElement(root, "mxCell", {"id": "0"})
        ET.SubElement(root, "mxCell", {"id": "1", "parent": "0"})

        node_positions = self._layout_nodes(page.nodes, page.kind_order, page.notation)
        cell_map: dict[str, str] = {}

        if page.notation == "c4-container":
            # Boundary rectangle behind internal nodes. We keep it a normal vertex to avoid group semantics.
            boundary_id = "b0"
            boundary = ET.SubElement(
                root,
                "mxCell",
                {
                    "id": boundary_id,
                    "value": "Граница системы",
                    "style": (
                        "rounded=0;whiteSpace=wrap;html=1;dashed=1;"
                        "strokeColor=#0F172A;fontColor=#0F172A;fillColor=none;"
                        "fontSize=14;align=left;verticalAlign=top;spacingLeft=12;spacingTop=10;"
                    ),
                    "vertex": "1",
                    "parent": "1",
                },
            )
            ET.SubElement(
                boundary,
                "mxGeometry",
                {
                    "x": "320",
                    "y": "40",
                    "width": "1520",
                    "height": "1280",
                    "as": "geometry",
                },
            )

        for idx, node in enumerate(page.nodes, start=1):
            x, y = node_positions[node.id]
            cell_id = f"v{idx}"
            cell_map[node.id] = cell_id
            width, height = 250, 95
            if page.notation.startswith("c4"):
                width, height = (420, 180) if node.id == "__c4_system__" else (320, 125)
            cell = ET.SubElement(
                root,
                "mxCell",
                {
                    "id": cell_id,
                    "value": _vertex_text(node, page.notation),
                    "style": _vertex_style(node, self.profile, page.notation),
                    "vertex": "1",
                    "parent": "1",
                },
            )
            ET.SubElement(
                cell,
                "mxGeometry",
                {
                    "x": str(x),
                    "y": str(y),
                    "width": str(width),
                    "height": str(height),
                    "as": "geometry",
                },
            )

        for idx, edge in enumerate(page.edges, start=1):
            if edge.from_id not in cell_map or edge.to_id not in cell_map:
                continue
            cell = ET.SubElement(
                root,
                "mxCell",
                {
                    "id": f"e{idx}",
                    "value": edge.label,
                    "style": _edge_style(edge),
                    "edge": "1",
                    "parent": "1",
                    "source": cell_map[edge.from_id],
                    "target": cell_map[edge.to_id],
                },
            )
            ET.SubElement(cell, "mxGeometry", {"relative": "1", "as": "geometry"})

        return graph

    def _layout_nodes(
        self,
        nodes: list[DrawNode],
        kind_order: list[str],
        notation: str,
    ) -> dict[str, tuple[int, int]]:
        # C4 pages use a dedicated layout so the result stays readable.
        if notation == "c4-context":
            return _layout_c4_context(nodes)
        if notation == "c4-container":
            return _layout_c4_container(nodes)

        columns = {kind: idx for idx, kind in enumerate(kind_order)}
        col_nodes: dict[int, list[DrawNode]] = {}
        for node in nodes:
            col = columns.get(node.kind, len(columns))
            col_nodes.setdefault(col, []).append(node)

        positions: dict[str, tuple[int, int]] = {}
        for col in sorted(col_nodes):
            y = 60
            ordered = sorted(col_nodes[col], key=lambda item: (item.kind, item.name.lower()))
            for node in ordered:
                positions[node.id] = (60 + col * 320, y)
                y += 130
        return positions

    def _build_c4_pages(
        self,
        model: IRModel,
        nodes: list[DrawNode],
        edges: list[DrawEdge],
    ) -> list[DrawPage]:
        """Add C4-style pages (new notation) for Draw.io without changing the IR model."""
        pages: list[DrawPage] = []

        # C4 Context: show one synthetic node for the subsystem + external systems.
        c4_system = DrawNode(
            id="__c4_system__",
            name=model.system.name,
            technology="System",
            kind="system",
            element_type=ElementType.CONTAINER,
            external=False,
            tags=[],
        )
        external_nodes = [n for n in nodes if n.external]
        context_nodes = [c4_system] + sorted(external_nodes, key=lambda n: (n.kind, n.name.lower(), n.id))

        internal_ids = {c.id for c in model.containers}
        ext_ids = {n.id for n in external_nodes}
        context_edges: list[DrawEdge] = []
        # Collapse any external<->internal relationship into external<->system.
        for rel in edges:
            if rel.from_id in ext_ids and rel.to_id in internal_ids:
                context_edges.append(DrawEdge(from_id=rel.from_id, to_id=c4_system.id, label=rel.label, async_flow=rel.async_flow))
            elif rel.from_id in internal_ids and rel.to_id in ext_ids:
                context_edges.append(DrawEdge(from_id=c4_system.id, to_id=rel.to_id, label=rel.label, async_flow=rel.async_flow))

        pages.append(
            DrawPage(
                page_id="drawio-c4-context",
                name="C4 Context",
                nodes=context_nodes,
                edges=self._filter_edges(context_edges, context_nodes),
                kind_order=["system", "client", "data", "product"],
                notation="c4-context",
            ),
        )

        # C4 Container: internal containers inside boundary + external systems around.
        internal_nodes = [n for n in nodes if not n.external and n.id in internal_ids]
        container_nodes = sorted(
            internal_nodes + external_nodes,
            key=lambda n: (n.external, n.kind, n.name.lower(), n.id),
        )
        container_edges = self._filter_edges(edges, container_nodes)
        pages.append(
            DrawPage(
                page_id="drawio-c4-container",
                name="C4 Container",
                nodes=container_nodes,
                edges=container_edges,
                kind_order=["client", "data", "product", "read", "process", "rules", "async", "other"],
                notation="c4-container",
            ),
        )
        return pages


def _page_title(key: str) -> str:
    mapping = {
        "context": "Context",
        "solution": "Solution Container",
        "data_async": "Data + Async",
        "flow_process": "Process Flow",
        # Backward-compatible alias.
        "flow_renewal": "Process Flow",
        "flow_ingestion": "Ingestion Flow",
        "operations": "Operations",
    }
    return mapping.get(key, key.replace("_", " ").title())


def _vertex_text(node: DrawNode, notation: str) -> str:
    if notation.startswith("c4"):
        # Draw.io supports HTML labels when html=1 in style.
        if node.id == "__c4_system__":
            return (
                f"<div style='font-size:16px'><b>{node.name}</b></div>"
                "<div style='color:#475569'>System</div>"
            )

        type_label = "External System" if node.external else "Container"
        if node.external and node.kind == "client":
            type_label = "Person"
        elif node.element_type == ElementType.DATABASE:
            type_label = "Database"
        elif node.element_type == ElementType.QUEUE:
            type_label = "Queue"

        tech = node.technology.strip() if node.technology else "TBD"
        return (
            f"<div style='color:#475569;font-size:12px'>{type_label}</div>"
            f"<div style='font-size:15px'><b>{node.name}</b></div>"
            f"<div style='color:#475569;font-size:12px'>{tech}</div>"
        )

    suffix = " (external)" if node.external else ""
    tech = node.technology.strip() if node.technology else "TBD"
    return f"{node.name}{suffix}\\n[{tech}]"


def _edge_label(description: str, protocol: str | None) -> str:
    text = " ".join(description.split())
    if protocol:
        proto = protocol.strip()
        if proto and proto.lower() not in text.lower():
            text = f"{text}\\n[{proto}]"
    if len(text) > 90:
        return text[:87].rstrip() + "..."
    return text


def _vertex_style(node: DrawNode, profile: NotationProfile, notation: str) -> str:
    if notation.startswith("c4"):
        if node.id == "__c4_system__":
            return (
                "rounded=1;whiteSpace=wrap;html=1;"
                "fillColor=#DBEAFE;strokeColor=#1E3A8A;fontColor=#0F172A;"
                "fontSize=14;align=left;spacingLeft=12;spacingTop=10;"
            )

        if node.external and node.kind == "client":
            return (
                "rounded=1;whiteSpace=wrap;html=1;"
                "fillColor=#FEF3C7;strokeColor=#92400E;fontColor=#111827;"
                "fontSize=13;align=left;spacingLeft=12;spacingTop=8;"
            )

        if node.element_type == ElementType.DATABASE:
            return (
                "shape=cylinder;whiteSpace=wrap;html=1;"
                "fillColor=#F1F5F9;strokeColor=#0F172A;fontColor=#0F172A;"
                "fontSize=13;align=left;spacingLeft=12;spacingTop=8;"
            )

        if node.element_type == ElementType.QUEUE:
            return (
                "rounded=1;whiteSpace=wrap;html=1;"
                "fillColor=#ECFDF5;strokeColor=#065F46;fontColor=#0F172A;"
                "fontSize=13;align=left;spacingLeft=12;spacingTop=8;"
            )

        if node.external:
            return (
                "rounded=1;whiteSpace=wrap;html=1;dashed=1;"
                "fillColor=#F8FAFC;strokeColor=#0F172A;fontColor=#0F172A;"
                "fontSize=13;align=left;spacingLeft=12;spacingTop=8;"
            )

        return (
            "rounded=1;whiteSpace=wrap;html=1;"
            "fillColor=#E0F2FE;strokeColor=#0F172A;fontColor=#0F172A;"
            "fontSize=13;align=left;spacingLeft=12;spacingTop=8;"
        )

    fill = profile.diagram.kind_fill_colors.get(node.kind, "#DAE8FC")
    if node.element_type == ElementType.DATABASE:
        return (
            "shape=cylinder;whiteSpace=wrap;html=1;"
            f"fillColor={fill};strokeColor=#6C8EBF;fontSize=12;"
        )
    if node.element_type == ElementType.QUEUE:
        return (
            "rounded=1;whiteSpace=wrap;html=1;"
            "fillColor=#D5E8D4;strokeColor=#82B366;fontSize=12;"
        )
    if node.external:
        return (
            "rounded=1;whiteSpace=wrap;html=1;dashed=1;"
            "fillColor=#F5F5F5;strokeColor=#666666;fontSize=12;"
        )
    return (
        "rounded=1;whiteSpace=wrap;html=1;"
        f"fillColor={fill};strokeColor=#6C8EBF;fontSize=12;"
    )


def _layout_c4_context(nodes: list[DrawNode]) -> dict[str, tuple[int, int]]:
    system = next((n for n in nodes if n.id == "__c4_system__"), None)
    externals = [n for n in nodes if n.id != "__c4_system__"]

    left = [n for n in externals if n.kind in {"client", "data"} or n.element_type == ElementType.DATABASE]
    right = [n for n in externals if n.kind == "product"]
    other = [n for n in externals if n not in left and n not in right]
    left.extend(other)

    positions: dict[str, tuple[int, int]] = {}
    if system is not None:
        positions[system.id] = (760, 420)

    y = 120
    for node in sorted(left, key=lambda n: (n.kind, n.name.lower(), n.id)):
        positions[node.id] = (60, y)
        y += 190

    y = 120
    for node in sorted(right, key=lambda n: (n.kind, n.name.lower(), n.id)):
        positions[node.id] = (1720, y)
        y += 190

    return positions


def _layout_c4_container(nodes: list[DrawNode]) -> dict[str, tuple[int, int]]:
    internal = [n for n in nodes if not n.external]
    externals = [n for n in nodes if n.external]

    left = [n for n in externals if n.kind in {"client", "data"} or n.element_type == ElementType.DATABASE]
    right = [n for n in externals if n.kind == "product"]
    other = [n for n in externals if n not in left and n not in right]
    left.extend(other)

    positions: dict[str, tuple[int, int]] = {}

    # Place internal containers within the boundary rectangle area (no compression).
    #
    # Target layout:
    # - left: read + rules (closest to UI and source vitrines)
    # - center: process (SoT)
    # - right: async (adapter + broker)
    # - data stores: below their "owner" service column
    col_x = {
        "left": 420,
        "center": 900,
        "right": 1380,
    }
    y_top = 140
    y_gap = 230

    def col_for(node: DrawNode) -> str:
        if node.element_type == ElementType.DATABASE:
            return "center"
        if node.kind in {"read", "rules"}:
            return "left"
        if node.kind == "process":
            return "center"
        if node.kind == "async" or node.element_type == ElementType.QUEUE:
            return "right"
        return "center"

    services = [n for n in internal if n.element_type in {ElementType.CONTAINER, ElementType.QUEUE}]
    stores = [n for n in internal if n.element_type == ElementType.DATABASE]

    left_services = [n for n in services if col_for(n) == "left"]
    center_services = [n for n in services if col_for(n) == "center"]
    right_services = [n for n in services if col_for(n) == "right"]

    # Stack vertically within each column.
    for idx, node in enumerate(sorted(left_services, key=lambda n: (n.kind, n.name.lower(), n.id))):
        positions[node.id] = (col_x["left"], y_top + idx * y_gap)
    for idx, node in enumerate(sorted(center_services, key=lambda n: (n.kind, n.name.lower(), n.id))):
        positions[node.id] = (col_x["center"], y_top + idx * y_gap)
    for idx, node in enumerate(sorted(right_services, key=lambda n: (n.kind, n.name.lower(), n.id))):
        positions[node.id] = (col_x["right"], y_top + idx * y_gap)

    # Put stores below the closest matching service by id prefix heuristic.
    def owner_x(db: DrawNode) -> int:
        dbid = db.id.lower()
        if "registry" in dbid:
            return col_x["left"]
        if "rules" in dbid:
            return col_x["left"]
        if "case" in dbid:
            return col_x["center"]
        return col_x["center"]

    y_db = 820
    for idx, db in enumerate(sorted(stores, key=lambda n: (n.name.lower(), n.id))):
        positions[db.id] = (owner_x(db), y_db + idx * 190)

    y = 120
    for node in sorted(left, key=lambda n: (n.kind, n.name.lower(), n.id)):
        positions[node.id] = (60, y)
        y += 200

    y = 120
    for node in sorted(right, key=lambda n: (n.kind, n.name.lower(), n.id)):
        positions[node.id] = (1900, y)
        y += 200

    return positions


def _edge_style(edge: DrawEdge) -> str:
    dashed = "1" if edge.async_flow else "0"
    return (
        "edgeStyle=orthogonalEdgeStyle;rounded=0;orthogonalLoop=1;jettySize=auto;"
        "html=1;endArrow=block;endFill=1;strokeColor=#4A5568;"
        f"dashed={dashed};fontSize=11;"
    )
