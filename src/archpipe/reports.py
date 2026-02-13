"""Report generation helpers."""

from __future__ import annotations

from collections import Counter
from datetime import datetime, timezone
import os
from pathlib import Path
from typing import Any

from archpipe.models.ir_schema import IRModel
from archpipe.models.validation import ValidationIssue, ValidationReport


def build_validation_markdown(
    hld_file: Path,
    report: ValidationReport,
    model: IRModel | None,
    generated_files: list[Path],
    status: str,
    lint_issues: list[ValidationIssue] | None = None,
    reproducible: bool = False,
) -> str:
    """Build markdown validation/build report."""
    now = "1970-01-01 00:00:00" if reproducible else datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    lines = [
        "# Validation Report",
        "",
        f"**HLD File:** `{hld_file.name}`",
        f"**Date:** {now}",
        f"**Status:** {status}",
        "",
        "## Summary",
        "",
        f"- **Containers:** {report.metrics.get('containers', 0)}",
        f"- **Relationships:** {report.metrics.get('relationships', 0)}",
        f"- **External Systems:** {report.metrics.get('external_systems', 0)}",
        f"- **Quality Attributes:** {report.metrics.get('quality_attributes', 0)}",
        f"- **Errors:** {len(report.errors)}",
        f"- **Warnings:** {len(report.warnings)}",
        "",
    ]

    if report.errors:
        lines.extend(["## Errors", ""])
        for issue in report.errors:
            line_info = f"Line {issue.location.line}" if issue.location.line else "Unknown line"
            lines.append(f"- ❌ **{issue.code}** - {issue.message} ({line_info})")
        lines.append("")

    if report.warnings:
        lines.extend(["## Warnings", ""])
        for issue in report.warnings:
            line_info = f"Line {issue.location.line}" if issue.location.line else "Unknown line"
            lines.append(f"- ⚠️ **{issue.code}** - {issue.message} ({line_info})")
        lines.append("")

    lint_issues = lint_issues or []
    if lint_issues:
        lint_errors = [issue for issue in lint_issues if issue.level.value == "error"]
        lint_warnings = [issue for issue in lint_issues if issue.level.value == "warning"]
        lines.extend(["## Lint", ""])
        lines.append(f"- **Lint Errors:** {len(lint_errors)}")
        lines.append(f"- **Lint Warnings:** {len(lint_warnings)}")
        lines.append("")
        for issue in lint_issues:
            line_info = f"Line {issue.location.line}" if issue.location.line else "Unknown line"
            prefix = "❌" if issue.level.value == "error" else "⚠️"
            lines.append(f"- {prefix} **{issue.code}** - {issue.message} ({line_info})")
        lines.append("")

    lines.extend(["## Statistics", ""])

    if model:
        tech_counter = Counter(container.technology for container in model.containers)
        lines.append("### Technology Stack")
        if tech_counter:
            for tech, count in tech_counter.items():
                lines.append(f"- {tech}: {count}")
        else:
            lines.append("- Not available")
        lines.append("")

        platform_counter = Counter(
            container.deployment.platform if container.deployment else "Not specified"
            for container in model.containers
        )
        lines.append("### Deployment Platforms")
        for platform, count in platform_counter.items():
            lines.append(f"- {platform}: {count}")
        lines.append("")

    lines.extend(["## Generated Artifacts", ""])
    if generated_files:
        for artifact in generated_files:
            lines.append(f"- ✅ `{artifact.as_posix()}`")
    else:
        lines.append("- No artifacts generated")

    lines.append("")
    return "\n".join(lines)


def build_report_json(
    hld_file: Path,
    report: ValidationReport,
    model: IRModel | None,
    generated_files: list[Path],
    status: str,
    duration_ms: int,
    lint_issues: list[ValidationIssue] | None = None,
    reproducible: bool = False,
) -> dict[str, Any]:
    """Build machine-readable build report."""
    lint_issues = lint_issues or []
    warnings = [
        {
            "code": issue.code,
            "message": issue.message,
            "line": issue.location.line,
        }
        for issue in report.warnings
    ]

    errors = [
        {
            "code": issue.code,
            "message": issue.message,
            "line": issue.location.line,
        }
        for issue in report.errors
    ]

    lint_errors = [issue.to_dict() for issue in lint_issues if issue.level.value == "error"]
    lint_warnings = [issue.to_dict() for issue in lint_issues if issue.level.value == "warning"]

    timestamp = (
        "1970-01-01T00:00:00Z"
        if reproducible
        else datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    )

    return {
        "timestamp": timestamp,
        "hld_file": hld_file.as_posix(),
        "ir_version": model.version if model else None,
        "status": status,
        "metrics": report.metrics,
        "validation": {
            "errors": errors,
            "warnings": warnings,
        },
        "lint": {
            "errors": lint_errors,
            "warnings": lint_warnings,
        },
        "generated_files": [path.as_posix() for path in generated_files],
        "duration_ms": duration_ms,
    }


def build_review_markdown(
    hld_file: Path,
    report: ValidationReport,
    generated_files: list[Path],
    output_dir: Path,
) -> str:
    """Build review-oriented report with image previews and legend."""
    lines: list[str] = [
        "# Review Report",
        "",
        f"**HLD File:** `{hld_file.name}`",
        f"**Errors:** {len(report.errors)}",
        f"**Warnings:** {len(report.warnings)}",
        "",
        "## Model Snapshot",
        "",
        f"- Containers: {report.metrics.get('containers', 0)}",
        f"- Relationships: {report.metrics.get('relationships', 0)}",
        f"- External Systems: {report.metrics.get('external_systems', 0)}",
        f"- Integrations: {report.metrics.get('integrations', 0)}",
        "",
    ]

    if report.errors:
        lines.extend(["## Validation Errors", ""])
        for issue in report.errors:
            lines.append(f"- `{issue.code}` {issue.message}")
        lines.append("")

    if report.warnings:
        lines.extend(["## Validation Warnings", ""])
        for issue in report.warnings:
            lines.append(f"- `{issue.code}` {issue.message}")
        lines.append("")

    lines.extend(["## Diagram Previews", ""])
    output_dir_abs = output_dir.resolve()
    images = _collect_review_images(output_dir, generated_files)
    if not images:
        lines.append("No rendered images found. Run `archpipe generate ... --render-images`.")
        lines.append("")
    else:
        for image in images:
            title = image.stem.replace("-", " ").replace("_", " ").title()
            rel_path = Path(os.path.relpath(image.resolve(), output_dir_abs)).as_posix()
            lines.append(f"### {title}")
            lines.append("")
            lines.append(f"![{title}](../{rel_path})")
            lines.append("")

    legend_path = output_dir / "diagrams" / "plantuml" / "relations-legend.md"
    if legend_path.exists():
        lines.extend(["## Relations Legend", ""])
        legend_lines = legend_path.read_text(encoding="utf-8").splitlines()
        lines.extend(legend_lines)
        lines.append("")

    return "\n".join(lines)


def _collect_review_images(output_dir: Path, generated_files: list[Path]) -> list[Path]:
    image_ext = {".png", ".svg"}
    from_generated = [path for path in generated_files if path.suffix.lower() in image_ext and path.exists()]
    if from_generated:
        return sorted(from_generated)

    fallback = sorted((output_dir / "diagrams").rglob("*.png"))
    return [path for path in fallback if path.exists()]
