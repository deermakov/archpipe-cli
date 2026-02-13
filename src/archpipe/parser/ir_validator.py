"""Validation pipeline for parsed IR models."""

from __future__ import annotations

from collections import Counter, defaultdict
from pathlib import Path

from pydantic import ValidationError

from archpipe.models.ir_schema import ElementType, IRModel
from archpipe.models.validation import (
    ValidationIssue,
    ValidationLevel,
    ValidationLocation,
    ValidationReport,
)


SUPPORTED_IR_VERSIONS = {"1.0"}


class IRValidator:
    """Validate IR schema and semantics."""

    def validate(
        self,
        hld_path: Path,
        ir_data: dict,
        block_start_line: int,
    ) -> tuple[IRModel | None, ValidationReport]:
        """Run schema and semantic validation."""
        report = ValidationReport(hld_file=str(hld_path))

        model = self._validate_schema(hld_path, ir_data, block_start_line, report)
        if model is None:
            return None, report

        self._validate_semantics(hld_path, model, block_start_line, report)
        self._validate_quality(hld_path, model, block_start_line, report)
        report.metrics = self._build_metrics(model)

        return model, report

    def _validate_schema(
        self,
        hld_path: Path,
        ir_data: dict,
        block_start_line: int,
        report: ValidationReport,
    ) -> IRModel | None:
        version = ir_data.get("version")
        if version not in SUPPORTED_IR_VERSIONS:
            report.add_issue(
                ValidationIssue(
                    level=ValidationLevel.ERROR,
                    code="E002",
                    message=(
                        f"Unsupported IR version '{version}'. "
                        f"Supported versions: {sorted(SUPPORTED_IR_VERSIONS)}"
                    ),
                    location=ValidationLocation(
                        file=str(hld_path),
                        line=block_start_line,
                        block="archpipe-model",
                    ),
                    suggestion="Set version to '1.0' or upgrade validator.",
                ),
            )
            return None

        try:
            return IRModel.model_validate(ir_data)
        except ValidationError as exc:
            for error in exc.errors():
                location = ".".join(str(part) for part in error.get("loc", ()))
                report.add_issue(
                    ValidationIssue(
                        level=ValidationLevel.ERROR,
                        code="E003",
                        message=f"Schema validation failed: {location}: {error['msg']}",
                        location=ValidationLocation(
                            file=str(hld_path),
                            line=block_start_line,
                            block="archpipe-model",
                        ),
                        suggestion="Fix fields according to IR schema.",
                    ),
                )
            return None

    def _validate_semantics(
        self,
        hld_path: Path,
        model: IRModel,
        block_start_line: int,
        report: ValidationReport,
    ) -> None:
        ids = [container.id for container in model.containers]
        ids.extend(component.id for c in model.containers for component in c.components)
        ids.extend(system.id for system in model.external_systems)

        duplicates = [item for item, count in Counter(ids).items() if count > 1]
        for duplicate in duplicates:
            report.add_issue(
                ValidationIssue(
                    level=ValidationLevel.ERROR,
                    code="E004",
                    message=f"Duplicate element ID detected: '{duplicate}'.",
                    location=ValidationLocation(
                        file=str(hld_path),
                        line=block_start_line,
                        block="archpipe-model",
                    ),
                    suggestion="Ensure all IDs are unique.",
                ),
            )

        known_ids = model.all_known_ids()
        for relationship in model.relationships:
            if relationship.from_id not in known_ids:
                report.add_issue(
                    ValidationIssue(
                        level=ValidationLevel.ERROR,
                        code="E005",
                        message=(
                            f"Relationship source '{relationship.from_id}' "
                            "is not defined."
                        ),
                        location=ValidationLocation(
                            file=str(hld_path),
                            line=block_start_line,
                            block="archpipe-model",
                        ),
                        suggestion="Add the missing element or fix relationship source.",
                    ),
                )
            if relationship.to_id not in known_ids:
                report.add_issue(
                    ValidationIssue(
                        level=ValidationLevel.ERROR,
                        code="E006",
                        message=(
                            f"Relationship target '{relationship.to_id}' is not defined."
                        ),
                        location=ValidationLocation(
                            file=str(hld_path),
                            line=block_start_line,
                            block="archpipe-model",
                        ),
                        suggestion="Add the missing element or fix relationship target.",
                    ),
                )

        for integration in model.integrations:
            if integration.from_id not in known_ids:
                report.add_issue(
                    ValidationIssue(
                        level=ValidationLevel.ERROR,
                        code="E007",
                        message=(
                            f"Integration source '{integration.from_id}' "
                            "is not defined."
                        ),
                        location=ValidationLocation(
                            file=str(hld_path),
                            line=block_start_line,
                            block="archpipe-model",
                        ),
                        suggestion="Add missing source element.",
                    ),
                )
            if integration.to_id not in known_ids:
                report.add_issue(
                    ValidationIssue(
                        level=ValidationLevel.ERROR,
                        code="E008",
                        message=f"Integration target '{integration.to_id}' is not defined.",
                        location=ValidationLocation(
                            file=str(hld_path),
                            line=block_start_line,
                            block="archpipe-model",
                        ),
                        suggestion="Add missing target element.",
                    ),
                )

        self._validate_cycles(hld_path, model, block_start_line, report)

    def _validate_cycles(
        self,
        hld_path: Path,
        model: IRModel,
        block_start_line: int,
        report: ValidationReport,
    ) -> None:
        # Keep iteration deterministic: sets make cycle-path warnings unstable, which breaks
        # reproducible generation and makes review reports noisy.
        container_ids = [container.id for container in model.containers]
        container_id_set = set(container_ids)

        # Preserve relationship order while deduplicating edges.
        graph: dict[str, list[str]] = defaultdict(list)
        seen_edges: dict[str, set[str]] = defaultdict(set)
        for relationship in model.relationships:
            if relationship.from_id in container_id_set and relationship.to_id in container_id_set:
                if relationship.to_id not in seen_edges[relationship.from_id]:
                    graph[relationship.from_id].append(relationship.to_id)
                    seen_edges[relationship.from_id].add(relationship.to_id)

        visited: set[str] = set()
        stack: list[str] = []
        in_stack: set[str] = set()

        def dfs(node: str) -> bool:
            visited.add(node)
            stack.append(node)
            in_stack.add(node)

            for neighbor in graph.get(node, []):
                if neighbor not in visited and dfs(neighbor):
                    return True
                if neighbor in in_stack:
                    cycle_start = stack.index(neighbor)
                    cycle = " -> ".join(stack[cycle_start:] + [neighbor])
                    report.add_issue(
                        ValidationIssue(
                            level=ValidationLevel.WARNING,
                            code="W003",
                            message=f"Potential circular dependency detected: {cycle}",
                            location=ValidationLocation(
                                file=str(hld_path),
                                line=block_start_line,
                                block="archpipe-model",
                            ),
                            suggestion=(
                                "Consider async messaging or boundary changes to "
                                "remove cycle."
                            ),
                        ),
                    )
                    return True

            stack.pop()
            in_stack.remove(node)
            return False

        for node in container_ids:
            if node not in visited and dfs(node):
                break

    def _validate_quality(
        self,
        hld_path: Path,
        model: IRModel,
        block_start_line: int,
        report: ValidationReport,
    ) -> None:
        for container in model.containers:
            if container.type == ElementType.CONTAINER and not container.deployment:
                report.add_issue(
                    ValidationIssue(
                        level=ValidationLevel.WARNING,
                        code="W001",
                        message=(
                            f"Container '{container.id}' has no deployment configuration."
                        ),
                        location=ValidationLocation(
                            file=str(hld_path),
                            line=block_start_line,
                            block="archpipe-model",
                        ),
                        suggestion=(
                            "Add deployment.platform/scaling for production readiness."
                        ),
                    ),
                )

        for relationship in model.relationships:
            if not relationship.protocol:
                report.add_issue(
                    ValidationIssue(
                        level=ValidationLevel.WARNING,
                        code="W002",
                        message=(
                            "Relationship "
                            f"'{relationship.from_id} -> {relationship.to_id}' "
                            "has no protocol specified."
                        ),
                        location=ValidationLocation(
                            file=str(hld_path),
                            line=block_start_line,
                            block="archpipe-model",
                        ),
                        suggestion="Specify protocol (HTTP, gRPC, SQL, etc.).",
                    ),
                )

        if not model.quality_attributes:
            report.add_issue(
                ValidationIssue(
                    level=ValidationLevel.WARNING,
                    code="W004",
                    message="No quality attributes defined in IR.",
                    location=ValidationLocation(
                        file=str(hld_path),
                        line=block_start_line,
                        block="archpipe-model",
                    ),
                    suggestion="Add availability, latency, throughput, etc.",
                ),
            )

    def _build_metrics(self, model: IRModel) -> dict[str, int]:
        deployment_count = sum(1 for c in model.containers if c.deployment is not None)
        component_count = sum(len(c.components) for c in model.containers)
        return {
            "containers": len(model.containers),
            "components": component_count,
            "relationships": len(model.relationships),
            "external_systems": len(model.external_systems),
            "integrations": len(model.integrations),
            "deployment_environments": len(model.deployment_environments),
            "quality_attributes": len(model.quality_attributes),
            "containers_with_deployment": deployment_count,
        }
