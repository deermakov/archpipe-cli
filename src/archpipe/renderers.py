"""Image rendering helpers for generated diagram artifacts."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
import shutil
import subprocess

PLANTUML_LIMIT_SIZE = "16384"


@dataclass(slots=True)
class RenderResult:
    """Image rendering summary."""

    files: list[Path] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


def render_artifact_images(
    output_dir: Path,
    output_format: str,
    image_format: str,
    force: bool,
    source_files: list[Path] | None = None,
) -> RenderResult:
    """Render PNG/SVG images from generated diagram sources."""
    result = RenderResult()

    if output_format in {"all", "c4"}:
        c4_result = _export_c4_to_plantuml(output_dir)
        result.files.extend(c4_result.files)
        result.warnings.extend(c4_result.warnings)

    if output_format not in {"all", "c4", "plantuml"}:
        return result

    puml_files = _resolve_puml_sources(output_dir, output_format, source_files)
    if not puml_files:
        result.warnings.append("No PlantUML sources found for image rendering.")
        return result

    targets = _resolve_target_formats(image_format)
    for fmt in targets:
        batch = _render_puml_batch(puml_files, fmt, force)
        result.files.extend(batch.files)
        result.warnings.extend(batch.warnings)

    return result


def _resolve_puml_sources(
    output_dir: Path,
    output_format: str,
    source_files: list[Path] | None,
) -> list[Path]:
    if source_files is None:
        return sorted((output_dir / "diagrams").rglob("*.puml"))

    selected: list[Path] = []
    source_set = {path.resolve() for path in source_files if path.suffix.lower() == ".puml"}

    if output_format in {"all", "plantuml"}:
        selected.extend(sorted(source_set))

    if output_format in {"all", "c4"}:
        selected.extend(sorted((output_dir / "diagrams" / "c4").glob("*.puml")))

    deduplicated: list[Path] = []
    seen: set[Path] = set()
    for item in selected:
        resolved = item.resolve()
        if resolved in seen:
            continue
        seen.add(resolved)
        deduplicated.append(item)

    return deduplicated


def _export_c4_to_plantuml(output_dir: Path) -> RenderResult:
    result = RenderResult()
    c4_dir = output_dir / "diagrams" / "c4"
    workspace = c4_dir / "workspace.dsl"

    if not workspace.exists():
        result.warnings.append("C4 workspace.dsl not found; skipping C4 image export.")
        return result

    cmd, cwd = _structurizr_export_command(c4_dir)
    if cmd is None:
        result.warnings.append(
            "Structurizr CLI not available; skipping C4 image export.",
        )
        return result

    completed = subprocess.run(
        cmd,
        cwd=cwd,
        capture_output=True,
        text=True,
        check=False,
    )
    if completed.returncode != 0:
        error_text = (completed.stderr or completed.stdout).strip().splitlines()
        details = error_text[-1] if error_text else "unknown export error"
        result.warnings.append(f"C4 export failed: {details}")
        return result

    result.warnings.extend(_tune_c4_plantuml_sources(c4_dir))
    return result


def _tune_c4_plantuml_sources(c4_dir: Path) -> list[str]:
    """Post-process Structurizr PlantUML output for better readability."""
    warnings: list[str] = []

    for source in sorted(c4_dir.glob("structurizr-*.puml")):
        try:
            text = source.read_text(encoding="utf-8")
        except OSError as exc:
            warnings.append(f"Failed to read C4 source {source.name}: {exc}")
            continue

        original = text
        # Keep all C4 exports in horizontal layout (left-to-right).
        if "top to bottom direction" in text:
            text = text.replace("top to bottom direction", "left to right direction", 1)

        if "skinparam linetype ortho" not in text:
            direction_line = "left to right direction"
            text = text.replace(
                direction_line,
                f"{direction_line}\nskinparam linetype ortho\nskinparam ArrowFontSize 9",
                1,
            )

        text = text.replace("skinparam ranksep 60", "skinparam ranksep 120")
        text = text.replace("skinparam nodesep 30", "skinparam nodesep 80")
        text = text.replace("skinparam nodesep 20", "skinparam nodesep 80")

        if text == original:
            continue

        try:
            source.write_text(text, encoding="utf-8")
        except OSError as exc:
            warnings.append(f"Failed to tune C4 source {source.name}: {exc}")

    return warnings


def _structurizr_export_command(c4_dir: Path) -> tuple[list[str] | None, Path]:
    local = shutil.which("structurizr") or shutil.which("structurizr.sh")
    if local:
        return [local, "export", "-w", "workspace.dsl", "-f", "plantuml", "-o", "."], c4_dir

    docker_bin = shutil.which("docker")
    if not docker_bin:
        return None, c4_dir

    return [
        docker_bin,
        "run",
        "--rm",
        "-v",
        f"{c4_dir}:/work",
        "-w",
        "/work",
        "structurizr/cli",
        "export",
        "-w",
        "workspace.dsl",
        "-f",
        "plantuml",
        "-o",
        ".",
    ], c4_dir


def _resolve_target_formats(image_format: str) -> list[str]:
    if image_format == "both":
        return ["png", "svg"]
    return [image_format]


def _render_puml_batch(sources: list[Path], fmt: str, force: bool) -> RenderResult:
    """Render a list of PlantUML sources with a single invocation per directory."""
    result = RenderResult()

    by_dir: dict[Path, list[Path]] = {}
    for source in sources:
        target = source.with_suffix(f".{fmt}")
        if target.exists() and not force:
            result.warnings.append(f"Skip render (exists): {target}")
            continue
        by_dir.setdefault(source.parent, []).append(source)

    for directory, dir_sources in sorted(by_dir.items(), key=lambda item: item[0].as_posix()):
        cmd, cwd = _plantuml_render_command_batch(directory, fmt, dir_sources)
        if cmd is None:
            for source in dir_sources:
                result.warnings.append(f"PlantUML renderer is unavailable for {source}.")
            continue

        completed = subprocess.run(
            cmd,
            cwd=cwd,
            capture_output=True,
            text=True,
            check=False,
        )
        if completed.returncode != 0:
            error_text = (completed.stderr or completed.stdout).strip().splitlines()
            details = error_text[-1] if error_text else "unknown render error"
            result.warnings.append(f"Render failed in {directory.name} ({fmt}): {details}")
            continue

        for source in dir_sources:
            target = source.with_suffix(f".{fmt}")
            if target.exists():
                result.files.append(target)
            else:
                result.warnings.append(f"Render command succeeded but output is missing: {target}")

    return result


def _plantuml_render_command_batch(
    directory: Path,
    fmt: str,
    sources: list[Path],
) -> tuple[list[str] | None, Path]:
    source_names = [source.name for source in sorted(sources, key=lambda item: item.name)]

    local = shutil.which("plantuml")
    if local:
        return [
            local,
            f"-DPLANTUML_LIMIT_SIZE={PLANTUML_LIMIT_SIZE}",
            f"-t{fmt}",
            *source_names,
        ], directory

    docker_bin = shutil.which("docker")
    if not docker_bin:
        return None, directory

    return [
        docker_bin,
        "run",
        "--rm",
        "-e",
        f"JAVA_TOOL_OPTIONS=-DPLANTUML_LIMIT_SIZE={PLANTUML_LIMIT_SIZE}",
        "-v",
        f"{directory}:/work",
        "-w",
        "/work",
        "plantuml/plantuml",
        f"-t{fmt}",
        *source_names,
    ], directory
