"""ArchiMate Open Exchange XML generator."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Iterable
import xml.etree.ElementTree as ET

from archpipe.generators.base import BaseGenerator
from archpipe.models.ir_schema import ElementType, IRModel
from archpipe.models.profile import DEFAULT_PROFILE, NotationProfile
from archpipe.models.tags import get_tag_value, has_tag, is_external


NS = "http://www.opengroup.org/xsd/archimate/3.0/"
XSI_NS = "http://www.w3.org/2001/XMLSchema-instance"
XML_NS = "http://www.w3.org/XML/1998/namespace"
SCHEMA_LOCATION = (
    "http://www.opengroup.org/xsd/archimate/3.0/ "
    "http://www.opengroup.org/xsd/archimate/3.0/archimate3_Diagram.xsd"
)
ARCHIMATE_RELEASE = "3.2"

ET.register_namespace("", NS)
ET.register_namespace("xsi", XSI_NS)


@dataclass(slots=True)
class ElementMeta:
    """Metadata for an exported ArchiMate element."""

    source_id: str
    xml_id: str
    name: str
    xsi_type: str
    layer: str
    kind: str


@dataclass(slots=True)
class RelationshipMeta:
    """Metadata for an exported ArchiMate relationship."""

    xml_id: str
    source_xml_id: str
    target_xml_id: str
    source_id: str
    target_id: str
    protocol: str


class ArchimateGenerator(BaseGenerator):
    """Generate Open Exchange XML model."""

    name = "archimate"

    def __init__(
        self,
        profile: NotationProfile | None = None,
        view_pack: str = "full",
        reproducible: bool = False,
    ) -> None:
        self.profile = profile or DEFAULT_PROFILE
        self.view_pack = view_pack
        self.reproducible = reproducible

    def generate(self, model: IRModel, output_dir: Path, force: bool = False) -> list[Path]:
        archimate_dir = output_dir / "archimate"
        model_path = archimate_dir / "model.xml"
        readme_path = archimate_dir / "README.md"
        viewpoints_path = archimate_dir / "viewpoints.md"

        xml_content = self._render_xml(model)
        readme_content = self._render_readme(model_path)

        self._write_file(model_path, xml_content, force)
        self._write_file(readme_path, readme_content, force)

        generated = [model_path, readme_path]
        if self.profile.archimate.include_viewpoints_file:
            self._write_file(viewpoints_path, self._render_viewpoints(model), force)
            generated.append(viewpoints_path)

        return generated

    def _render_xml(self, model: IRModel) -> str:
        root = ET.Element(
            f"{{{NS}}}model",
            {
                f"{{{XSI_NS}}}schemaLocation": SCHEMA_LOCATION,
                "identifier": "id-model-1",
            },
        )

        name = ET.SubElement(root, f"{{{NS}}}name")
        name.text = model.metadata.title

        if model.metadata.description:
            doc = ET.SubElement(root, f"{{{NS}}}documentation")
            doc.text = model.metadata.description

        self._add_properties(root, {"archimate-release": ARCHIMATE_RELEASE})

        elements_parent = ET.SubElement(root, f"{{{NS}}}elements")
        relationships_parent = ET.SubElement(root, f"{{{NS}}}relationships")

        element_map = self._emit_elements(model, elements_parent)
        relationship_meta = self._emit_relationships(model, element_map, relationships_parent)

        if self.profile.archimate.include_organizations:
            self._add_organizations(root, element_map, relationship_meta)

        self._add_property_definitions(root)
        self._add_views(root, model, element_map, relationship_meta)

        xml = ET.tostring(root, encoding="unicode")
        return '<?xml version="1.0" encoding="UTF-8"?>\n' + xml + "\n"

    def _emit_elements(self, model: IRModel, parent: ET.Element) -> dict[str, ElementMeta]:
        element_map: dict[str, ElementMeta] = {}
        counter = 1

        system_xml_id = "id-system"
        kind_key = self.profile.diagram.kind_tag_key
        self._add_element(
            parent,
            system_xml_id,
            "ApplicationComponent",
            model.system.name,
            model.system.description,
            self._element_properties("Application", model.metadata.tags, "system"),
        )
        element_map["__system__"] = ElementMeta(
            source_id="__system__",
            xml_id=system_xml_id,
            name=model.system.name,
            xsi_type="ApplicationComponent",
            layer="Application",
            kind="system",
        )

        for container in sorted(model.containers, key=lambda item: item.id):
            xml_id = f"id-el-{counter}"
            counter += 1
            xsi_type = self._map_element_type(container.type)
            layer = self._infer_layer(container.type)
            kind = get_tag_value(container.tags, kind_key) or container.type.value
            self._add_element(
                parent,
                xml_id,
                xsi_type,
                container.name,
                container.description,
                self._element_properties(layer, container.tags, kind),
            )
            element_map[container.id] = ElementMeta(
                source_id=container.id,
                xml_id=xml_id,
                name=container.name,
                xsi_type=xsi_type,
                layer=layer,
                kind=kind,
            )

        for ext in sorted(model.external_systems, key=lambda item: item.id):
            xml_id = f"id-ext-{counter}"
            counter += 1
            kind = get_tag_value(ext.tags, kind_key) or "external"
            self._add_element(
                parent,
                xml_id,
                "ApplicationComponent",
                ext.name,
                ext.description or "External system",
                self._element_properties("External", ext.tags, kind),
            )
            element_map[ext.id] = ElementMeta(
                source_id=ext.id,
                xml_id=xml_id,
                name=ext.name,
                xsi_type="ApplicationComponent",
                layer="External",
                kind=kind,
            )

        return element_map

    def _emit_relationships(
        self,
        model: IRModel,
        element_map: dict[str, ElementMeta],
        parent: ET.Element,
    ) -> list[RelationshipMeta]:
        rel_meta: list[RelationshipMeta] = []
        counter = 1

        for rel in sorted(
            model.relationships,
            key=lambda item: (item.from_id, item.to_id, item.description, item.protocol or ""),
        ):
            source = element_map.get(rel.from_id)
            target = element_map.get(rel.to_id)
            if source is None or target is None:
                continue

            rel_id = f"id-rel-{counter}"
            counter += 1
            full_description = rel.description
            display_name = self._short_relationship_label(full_description, rel.protocol or "")
            rel_type = self._map_relationship_type(
                rel.protocol or "",
                rel.description,
                source.xsi_type,
                target.xsi_type,
            )
            self._add_relationship(
                parent,
                rel_id,
                rel_type,
                source.xml_id,
                target.xml_id,
                display_name,
                full_description,
                {
                    "protocol": rel.protocol or "",
                    "relation-kind": "relationship",
                },
            )
            rel_meta.append(
                RelationshipMeta(
                    xml_id=rel_id,
                    source_xml_id=source.xml_id,
                    target_xml_id=target.xml_id,
                    source_id=rel.from_id,
                    target_id=rel.to_id,
                    protocol=rel.protocol or "",
                ),
            )

        for integration in sorted(
            model.integrations,
            key=lambda item: (item.from_id, item.to_id, item.description or "", item.protocol or ""),
        ):
            source = element_map.get(integration.from_id)
            target = element_map.get(integration.to_id)
            if source is None or target is None:
                continue

            rel_id = f"id-rel-{counter}"
            counter += 1
            full_description = integration.description or "Integration"
            display_name = self._short_relationship_label(full_description, integration.protocol or "")
            self._add_relationship(
                parent,
                rel_id,
                "Flow",
                source.xml_id,
                target.xml_id,
                display_name,
                full_description,
                {
                    "protocol": integration.protocol or "",
                    "relation-kind": "integration",
                },
            )
            rel_meta.append(
                RelationshipMeta(
                    xml_id=rel_id,
                    source_xml_id=source.xml_id,
                    target_xml_id=target.xml_id,
                    source_id=integration.from_id,
                    target_id=integration.to_id,
                    protocol=integration.protocol or "",
                ),
            )

        return rel_meta

    def _add_views(
        self,
        root: ET.Element,
        model: IRModel,
        element_map: dict[str, ElementMeta],
        relationships: list[RelationshipMeta],
    ) -> None:
        views = ET.SubElement(root, f"{{{NS}}}views")
        diagrams = ET.SubElement(views, f"{{{NS}}}diagrams")

        view_pack = self.view_pack
        if view_pack not in {"draft", "review", "full"}:
            view_pack = "full"

        view_defs: list[tuple[str, str, str]] = [
            ("context", "id-view-context", "System Context"),
            ("solution", "id-view-solution", "Solution Container"),
            ("data_async", "id-view-data-async", "Data and Async Integration"),
        ]
        if view_pack in {"review", "full"}:
            view_defs.append(("operations", "id-view-operations", "Operations and Compliance"))

        for view_name, view_id, title in view_defs:
            include_ids = self._select_ids_by_view(model, view_name)
            if not include_ids:
                continue
            self._add_view(
                diagrams,
                view_name=view_name,
                view_id=view_id,
                title=title,
                include_ids=include_ids,
                element_map=element_map,
                relationships=relationships,
            )

    def _add_view(
        self,
        parent: ET.Element,
        view_name: str,
        view_id: str,
        title: str,
        include_ids: list[str],
        element_map: dict[str, ElementMeta],
        relationships: list[RelationshipMeta],
    ) -> None:
        view = ET.SubElement(
            parent,
            f"{{{NS}}}view",
            {
                "identifier": view_id,
                f"{{{XSI_NS}}}type": "Diagram",
            },
        )
        name = ET.SubElement(view, f"{{{NS}}}name")
        name.text = title

        node_lookup: dict[str, str] = {}
        node_layout: dict[str, tuple[int, int, int, int]] = {}
        include_set = set(include_ids)
        positions = self._layout_positions(view_name, include_ids, element_map)
        for idx, source_id in enumerate(include_ids, start=1):
            meta = element_map.get(source_id)
            if meta is None:
                continue

            node_id = f"{view_id}-node-{idx}"
            x, y = positions.get(source_id, (80, 80))
            width, height = self._node_size(meta.xsi_type)

            ET.SubElement(
                view,
                f"{{{NS}}}node",
                {
                    "identifier": node_id,
                    f"{{{XSI_NS}}}type": "Element",
                    "elementRef": meta.xml_id,
                    "x": str(x),
                    "y": str(y),
                    "w": str(width),
                    "h": str(height),
                },
            )
            node_lookup[meta.xml_id] = node_id
            node_layout[source_id] = (x, y, width, height)

        rels = self._relationships_for_view(relationships, include_set)
        fan_in = self._fan_in_slots(rels)
        async_offsets = self._async_pair_offsets(rels)
        connection_index = 1
        for rel in rels:
            src_node = node_lookup.get(rel.source_xml_id)
            dst_node = node_lookup.get(rel.target_xml_id)
            if src_node is None or dst_node is None:
                continue

            connection = ET.SubElement(
                view,
                f"{{{NS}}}connection",
                {
                    "identifier": f"{view_id}-conn-{connection_index}",
                    f"{{{XSI_NS}}}type": "Relationship",
                    "relationshipRef": rel.xml_id,
                    "source": src_node,
                    "target": dst_node,
                },
            )
            routed = self._add_connection_routing(connection, rel, node_layout, fan_in)
            if not routed:
                self._add_async_pair_routing(connection, rel, node_layout, async_offsets)
            connection_index += 1

    def _relationships_for_view(
        self,
        relationships: list[RelationshipMeta],
        include_ids: set[str],
    ) -> list[RelationshipMeta]:
        return sorted(
            (
                rel
                for rel in relationships
                if rel.source_id in include_ids and rel.target_id in include_ids
            ),
            key=lambda rel: (rel.source_id, rel.target_id, rel.protocol, rel.xml_id),
        )

    def _node_size(self, xsi_type: str) -> tuple[int, int]:
        if xsi_type == "DataObject":
            return 280, 120
        if xsi_type in {"TechnologyService", "ApplicationService"}:
            return 250, 100
        return 280, 120

    def _fan_in_slots(self, relationships: list[RelationshipMeta]) -> dict[str, tuple[int, int]]:
        """Compute fan-in slots for targets with multiple inbound links.

        Slotting is used to attach distinct targetAttachment points and avoid
        visually merging all inbound edges into a single line.
        """
        by_target: dict[str, list[RelationshipMeta]] = {}
        for rel in relationships:
            by_target.setdefault(rel.target_id, []).append(rel)

        slots: dict[str, tuple[int, int]] = {}
        for _, inbound in by_target.items():
            if len(inbound) < 2:
                continue
            inbound.sort(key=lambda rel: (rel.source_id, rel.xml_id))
            total = len(inbound)
            for idx, rel in enumerate(inbound):
                slots[rel.xml_id] = (idx, total)
        return slots

    def _add_connection_routing(
        self,
        connection: ET.Element,
        rel: RelationshipMeta,
        node_layout: dict[str, tuple[int, int, int, int]],
        fan_in_slots: dict[str, tuple[int, int]],
    ) -> bool:
        """Attach bendpoints/attachments for dense fan-in targets to avoid edge overlap."""
        slot = fan_in_slots.get(rel.xml_id)
        if slot is None:
            return False
        source_box = node_layout.get(rel.source_id)
        target_box = node_layout.get(rel.target_id)
        if source_box is None or target_box is None:
            return False

        sx, sy, sw, sh = source_box
        tx, ty, tw, th = target_box
        slot_idx, slot_total = slot
        slot_total = max(slot_total, 1)

        slot_step = max(22, th // (slot_total + 1))
        target_y = ty + min(th - 16, 10 + (slot_idx + 1) * slot_step)

        left_to_right = sx <= tx
        source_y = sy + sh // 2
        if left_to_right:
            target_x = tx
            # Route through a vertical bus before entering registry slots.
            bus_x = max(sx + sw + 80, target_x - (260 - min(slot_idx * 28, 112)))
        else:
            target_x = tx + tw
            bus_x = min(sx - 80, target_x + (260 - min(slot_idx * 28, 112)))

        ET.SubElement(
            connection,
            f"{{{NS}}}bendpoint",
            {"x": str(bus_x), "y": str(source_y)},
        )
        ET.SubElement(
            connection,
            f"{{{NS}}}bendpoint",
            {"x": str(bus_x), "y": str(target_y)},
        )
        approach_x = target_x - 34 if left_to_right else target_x + 34
        ET.SubElement(
            connection,
            f"{{{NS}}}bendpoint",
            {"x": str(approach_x), "y": str(target_y)},
        )
        ET.SubElement(
            connection,
            f"{{{NS}}}targetAttachment",
            {"x": str(target_x), "y": str(target_y)},
        )
        return True

    def _add_async_pair_routing(
        self,
        connection: ET.Element,
        rel: RelationshipMeta,
        node_layout: dict[str, tuple[int, int, int, int]],
        async_offsets: dict[tuple[str, str], int],
    ) -> None:
        offset = async_offsets.get((rel.source_id, rel.target_id))
        if offset is None:
            return
        source_box = node_layout.get(rel.source_id)
        target_box = node_layout.get(rel.target_id)
        if source_box is None or target_box is None:
            return

        sx, sy, sw, sh = source_box
        tx, ty, tw, th = target_box
        source_y = sy + sh // 2 + offset
        target_y = ty + th // 2 + offset

        horizontal_overlap = max(sx, tx) < min(sx + sw, tx + tw)
        if horizontal_overlap:
            # Vertical stack: route along side lanes (left/right) to avoid
            # self-loop artifacts and overlapping labels near the node edges.
            lane_side = -1 if offset < 0 else 1
            source_y_mid = sy + sh // 2
            target_y_mid = ty + th // 2
            if lane_side < 0:
                source_x = sx
                target_x = tx
                lane_x = min(source_x, target_x) - 140
            else:
                source_x = sx + sw
                target_x = tx + tw
                lane_x = max(source_x, target_x) + 120
            lane_x += 20 if offset >= 0 else -20
            ET.SubElement(
                connection,
                f"{{{NS}}}sourceAttachment",
                {"x": str(source_x), "y": str(source_y_mid)},
            )
            ET.SubElement(
                connection,
                f"{{{NS}}}bendpoint",
                {"x": str(lane_x), "y": str(source_y_mid)},
            )
            ET.SubElement(
                connection,
                f"{{{NS}}}bendpoint",
                {"x": str(lane_x), "y": str(target_y_mid)},
            )
            ET.SubElement(
                connection,
                f"{{{NS}}}targetAttachment",
                {"x": str(target_x), "y": str(target_y_mid)},
            )
            return

        left_to_right = sx <= tx
        source_x = sx + sw if left_to_right else sx
        target_x = tx if left_to_right else tx + tw
        mid_x = (source_x + target_x) // 2

        ET.SubElement(
            connection,
            f"{{{NS}}}sourceAttachment",
            {"x": str(source_x), "y": str(source_y)},
        )
        ET.SubElement(
            connection,
            f"{{{NS}}}bendpoint",
            {"x": str(mid_x), "y": str(source_y)},
        )
        ET.SubElement(
            connection,
            f"{{{NS}}}bendpoint",
            {"x": str(mid_x), "y": str(target_y)},
        )
        ET.SubElement(
            connection,
            f"{{{NS}}}targetAttachment",
            {"x": str(target_x), "y": str(target_y)},
        )

    def _async_pair_offsets(self, relationships: list[RelationshipMeta]) -> dict[tuple[str, str], int]:
        """Create offsets for bidirectional async edges to keep both lines readable."""
        async_pairs: dict[tuple[str, str], set[tuple[str, str]]] = {}
        for rel in relationships:
            if "async" not in rel.protocol.lower():
                continue
            a, b = rel.source_id, rel.target_id
            key = tuple(sorted((a, b)))
            async_pairs.setdefault(key, set()).add((a, b))

        offsets: dict[tuple[str, str], int] = {}
        for key, directions in async_pairs.items():
            if len(directions) < 2:
                continue
            a, b = key
            offsets[(a, b)] = -24
            offsets[(b, a)] = 24
        return offsets

    def _select_ids_by_view(self, model: IRModel, view_name: str) -> list[str]:
        spec = self.profile.diagram.views.get(view_name)
        if spec is None:
            ids = [container.id for container in model.containers]
            ids.extend(ext.id for ext in model.external_systems)
            return sorted(set(ids))

        kind_key = self.profile.diagram.kind_tag_key
        include_kinds = set(spec.include_kinds)
        exclude_kinds = set(spec.exclude_kinds)
        include_external = spec.include_external
        include_tags = {tag.strip().lower() for tag in spec.include_tags}
        exclude_tags = {tag.strip().lower() for tag in spec.exclude_tags}

        selected: set[str] = set()

        def include_element(element_id: str, tags: list[str], external_hint: bool) -> None:
            kind = get_tag_value(tags, kind_key)
            if kind in exclude_kinds:
                return
            if any(has_tag(tags, tag) for tag in exclude_tags):
                return
            if any(has_tag(tags, tag) for tag in include_tags):
                selected.add(element_id)
                return
            if (external_hint or is_external(tags)) and include_external:
                selected.add(element_id)
                return
            if kind in include_kinds:
                selected.add(element_id)

        for container in sorted(model.containers, key=lambda item: item.id):
            include_element(container.id, container.tags, external_hint=False)
        for ext in sorted(model.external_systems, key=lambda item: item.id):
            include_element(ext.id, ext.tags, external_hint=True)

        return sorted(selected)

    def _layout_positions(
        self,
        view_name: str,
        include_ids: list[str],
        element_map: dict[str, ElementMeta],
    ) -> dict[str, tuple[int, int]]:
        """Deterministic layout with kind-based columns and external/top row separation."""
        spec = self.profile.diagram.views.get(view_name)
        kind_order = list(spec.include_kinds) if spec is not None else []
        kind_to_col = {kind: idx for idx, kind in enumerate(kind_order)}

        groups: dict[tuple[int, int], list[str]] = {}
        for element_id in include_ids:
            meta = element_map.get(element_id)
            if meta is None:
                continue
            col = kind_to_col.get(meta.kind, len(kind_to_col))
            row = 0 if meta.layer == "External" else 1
            groups.setdefault((row, col), []).append(element_id)

        positions: dict[str, tuple[int, int]] = {}
        col_width = 420
        row_start = {0: 60, 1: 260}
        gap_y = 160
        x0 = 80
        for (row, col), ids in sorted(groups.items(), key=lambda item: (item[0][0], item[0][1])):
            y = row_start.get(row, 80)
            for element_id in sorted(ids):
                positions[element_id] = (x0 + col * col_width, y)
                y += gap_y
        return positions

    def _render_readme(self, model_path: Path) -> str:
        return "\n".join(
            [
                "# ArchiMate Import",
                "",
                "1. Open Archi and create a new model.",
                "2. Use File -> Import -> Open Exchange Format.",
                f"3. Select `{model_path.name}`.",
                (
                    "4. Open generated views: System Context, Solution Container, "
                    "Data and Async Integration, Operations and Compliance."
                ),
                "5. Optional: use `viewpoints.md` as checklist for additional custom views.",
                "",
            ],
        )

    def _render_viewpoints(self, model: IRModel) -> str:
        viewpoints = self._build_viewpoints(model)
        lines: list[str] = [
            "# Viewpoints",
            "",
            "Use these viewpoints as a guide when arranging diagrams in Archi.",
            "",
        ]

        for title, ids in viewpoints.items():
            lines.append(f"## {title}")
            lines.append("")
            for element_id in ids:
                lines.append(f"- `{element_id}`")
            lines.append("")

        return "\n".join(lines)

    def _build_viewpoints(self, model: IRModel) -> dict[str, list[str]]:
        viewpoints: dict[str, list[str]] = {}
        for view_name, title in [
            ("context", "System Context"),
            ("solution", "Solution Container"),
            ("data_async", "Data and Async Integration"),
            ("operations", "Operations and Compliance"),
        ]:
            ids = self._select_ids_by_view(model, view_name)
            if not ids:
                continue
            viewpoints[title] = ids
        return viewpoints

    def _infer_layer(self, element_type: ElementType) -> str:
        if element_type in {ElementType.DATABASE, ElementType.CACHE, ElementType.QUEUE}:
            return "Technology"
        return "Application"

    def _add_property_definitions(self, root: ET.Element) -> None:
        prop_defs = ET.SubElement(root, f"{{{NS}}}propertyDefinitions")
        self._add_property_definition(prop_defs, "prop-layer", "layer")
        self._add_property_definition(prop_defs, "prop-tags", "tags")
        self._add_property_definition(prop_defs, "prop-kind", "kind")
        self._add_property_definition(prop_defs, "prop-protocol", "protocol")
        self._add_property_definition(prop_defs, "prop-rel-kind", "relation-kind")
        self._add_property_definition(prop_defs, "prop-archimate-release", "archimate-release")

    def _add_property_definition(self, parent: ET.Element, identifier: str, name: str) -> None:
        prop = ET.SubElement(
            parent,
            f"{{{NS}}}propertyDefinition",
            {"identifier": identifier, "type": "string"},
        )
        prop_name = ET.SubElement(prop, f"{{{NS}}}name")
        prop_name.text = name

    def _element_properties(self, layer: str, tags: Iterable[str], kind: str) -> dict[str, str]:
        payload: dict[str, str] = {"kind": kind}
        if self.profile.archimate.include_layer_properties:
            payload["layer"] = layer
        if self.profile.archimate.include_tag_properties and tags:
            payload["tags"] = ",".join(tags)
        return payload

    def _add_organizations(
        self,
        root: ET.Element,
        element_map: dict[str, ElementMeta],
        relationships: list[RelationshipMeta],
    ) -> None:
        organizations = ET.SubElement(root, f"{{{NS}}}organizations")

        app_item = self._org_item(organizations, "Application Layer")
        tech_item = self._org_item(organizations, "Technology Layer")
        ext_item = self._org_item(organizations, "External Systems")
        rel_item = self._org_item(organizations, "Relationships")

        for meta in element_map.values():
            if meta.source_id == "__system__":
                continue
            bucket = app_item
            if meta.layer == "Technology":
                bucket = tech_item
            elif meta.layer == "External":
                bucket = ext_item
            ET.SubElement(bucket, f"{{{NS}}}item", {"identifierRef": meta.xml_id})

        for rel in relationships:
            ET.SubElement(rel_item, f"{{{NS}}}item", {"identifierRef": rel.xml_id})

    def _org_item(self, parent: ET.Element, title: str) -> ET.Element:
        item = ET.SubElement(parent, f"{{{NS}}}item")
        label = ET.SubElement(item, f"{{{NS}}}label", {f"{{{XML_NS}}}lang": "en"})
        label.text = title
        return item

    def _map_element_type(self, element_type: ElementType) -> str:
        mapping = {
            ElementType.CONTAINER: "ApplicationComponent",
            ElementType.DATABASE: "TechnologyService",
            ElementType.QUEUE: "ApplicationInterface",
            ElementType.CACHE: "TechnologyService",
            ElementType.COMPONENT: "ApplicationComponent",
            ElementType.DATA_OBJECT: "DataObject",
        }
        return mapping[element_type]

    def _map_relationship_type(
        self,
        protocol: str,
        description: str,
        source_type: str,
        target_type: str,
    ) -> str:
        protocol_norm = protocol.lower()
        description_norm = description.lower()

        flow_tokens = (
            "async",
            "event",
            "publish",
            "consume",
            "batch",
            "file",
            "otlp",
            "metric",
            "project",
            "projection",
            "upsert",
        )
        access_tokens = ("read", "write", "sql", "query", "crud")

        if any(token in protocol_norm or token in description_norm for token in flow_tokens):
            return "Flow"

        if "tbd" in protocol_norm or "dr" in protocol_norm or "tbd" in description_norm:
            return "Flow"

        if target_type == "DataObject" and any(
            token in protocol_norm or token in description_norm for token in access_tokens
        ):
            return "Access"

        if source_type == "DataObject" and target_type != "DataObject":
            if "project" in description_norm or "projection" in description_norm or "upsert" in description_norm:
                return "Flow"
            if any(token in protocol_norm or token in description_norm for token in access_tokens):
                return "Access"

        # IR relationships are directed as consumer -> provider in most HLDs.
        return "Serving"

    def _add_element(
        self,
        parent: ET.Element,
        identifier: str,
        xsi_type: str,
        name: str,
        documentation: str,
        properties: dict[str, str],
    ) -> None:
        element = ET.SubElement(
            parent,
            f"{{{NS}}}element",
            {
                "identifier": identifier,
                f"{{{XSI_NS}}}type": xsi_type,
            },
        )
        element_name = ET.SubElement(element, f"{{{NS}}}name")
        element_name.text = name
        element_doc = ET.SubElement(element, f"{{{NS}}}documentation")
        element_doc.text = documentation
        self._add_properties(element, properties)

    def _add_relationship(
        self,
        parent: ET.Element,
        identifier: str,
        xsi_type: str,
        source: str,
        target: str,
        name: str,
        documentation: str,
        properties: dict[str, str],
    ) -> None:
        relationship = ET.SubElement(
            parent,
            f"{{{NS}}}relationship",
            {
                "identifier": identifier,
                f"{{{XSI_NS}}}type": xsi_type,
                "source": source,
                "target": target,
            },
        )
        rel_name = ET.SubElement(relationship, f"{{{NS}}}name")
        rel_name.text = name
        rel_doc = ET.SubElement(relationship, f"{{{NS}}}documentation")
        rel_doc.text = documentation
        self._add_properties(relationship, properties)

    def _short_relationship_label(self, value: str, protocol: str = "") -> str:
        source = f"{protocol} {value}".lower()
        # Generic, domain-agnostic labels for common async naming patterns.
        if ".requests" in source or " requests" in source:
            if "publish" in source or "публику" in source:
                return "Publish requests"
            if "consume" in source or "потребля" in source:
                return "Consume requests"
            return "Requests"
        if ".results" in source or " results" in source:
            if "publish" in source or "публику" in source:
                return "Publish results"
            if "consume" in source or "потребля" in source:
                return "Consume results"
            return "Results"
        rules = (
            ("чтение/запись", "ReadWrite"),
            ("read/write", "ReadWrite"),
            ("publish", "Publish"),
            ("публику", "Publish"),
            ("consume", "Consume"),
            ("потребля", "Consume"),
            ("batch", "Batch"),
            ("дельт", "Batch"),
            ("project", "Project"),
            ("проекц", "Project"),
            ("upsert", "Upsert"),
            ("write", "Write"),
            ("запис", "Write"),
            ("crud", "Update"),
            ("update", "Update"),
            ("read", "Read"),
            ("чтени", "Read"),
            ("query", "Read"),
            ("audit", "Audit"),
            ("аудит", "Audit"),
            ("metric", "Metrics"),
            ("метрик", "Metrics"),
            ("export", "Export"),
            ("выгруз", "Export"),
            ("start", "Start"),
            ("запуск", "Start"),
            ("rule", "Rules"),
            ("правил", "Rules"),
            ("https", "API"),
            ("http", "API"),
            ("sql", "SQL"),
            ("async", "Async"),
        )
        for token, label in rules:
            if token in source:
                return label
        return "Flow"

    def _add_properties(self, parent: ET.Element, properties: dict[str, str]) -> None:
        cleaned = {k: v for k, v in properties.items() if v}
        if not cleaned:
            return

        props = ET.SubElement(parent, f"{{{NS}}}properties")
        for key, value in cleaned.items():
            property_ref = _property_ref(key)
            prop = ET.SubElement(props, f"{{{NS}}}property", {"propertyDefinitionRef": property_ref})
            prop_value = ET.SubElement(prop, f"{{{NS}}}value")
            prop_value.text = value


def _property_ref(key: str) -> str:
    mapping = {
        "layer": "prop-layer",
        "tags": "prop-tags",
        "kind": "prop-kind",
        "protocol": "prop-protocol",
        "relation-kind": "prop-rel-kind",
        "archimate-release": "prop-archimate-release",
    }
    return mapping[key]
