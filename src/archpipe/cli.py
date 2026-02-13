"""archpipe-cli entry point."""

from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
import time
from typing import Iterable, Literal

import click
import yaml

from archpipe import __version__ as ARCHPIPE_VERSION
from archpipe.generators.archimate_generator import ArchimateGenerator
from archpipe.generators.base import GeneratorError
from archpipe.generators.c4_generator import C4Generator
from archpipe.generators.drawio_generator import DrawIOGenerator
from archpipe.generators.plantuml_generator import PlantUMLGenerator
from archpipe.linting import run_lint_checks
from archpipe.models.ir_schema import IRModel
from archpipe.models.profile import NotationProfile, ProfileError, load_profile
from archpipe.models.validation import ValidationIssue, ValidationReport
from archpipe.parser.draft_ir import generate_draft_ir, render_ir_block
from archpipe.parser.hld_parser import (
    HLDParserError,
    IRBlock,
    IRBlockNotFoundError,
    IRYAMLError,
    load_ir_from_hld,
    write_ir_template,
)
from archpipe.parser.ir_validator import IRValidator
from archpipe.renderers import render_artifact_images
from archpipe.reports import (
    build_report_json,
    build_review_markdown,
    build_validation_markdown,
)


DEFAULT_OUTPUT_DIR = Path("./output")
AUTO_OUTPUT_DIR_TOKEN = Path("auto")
ViewPack = Literal["draft", "review", "full"]
NotationMode = Literal["default", "standard"]


@dataclass(slots=True)
class PipelineResult:
    """Validated pipeline result."""

    model: IRModel | None
    report: ValidationReport
    block: IRBlock
    draft_warnings: list[str]


@dataclass(slots=True)
class GenerationResult:
    hld_file: Path
    output_dir: Path
    status: Literal["success", "failed"]
    report_paths: list[Path]
    generated_files: list[Path]


@click.group(context_settings={"help_option_names": ["-h", "--help"]})
@click.version_option(ARCHPIPE_VERSION, "--version", "-V")
def main() -> None:
    """Generate architecture artifacts from HLD + IR."""


@main.command("validate")
@click.argument("hld_file", type=click.Path(exists=True, path_type=Path))
@click.option("--strict", is_flag=True, help="Fail on warnings.")
@click.option(
    "--output",
    "output_format",
    type=click.Choice(["text", "json"]),
    default="text",
    show_default=True,
)
@click.option("--draft", is_flag=True, help="Allow best-effort draft mode if IR is missing.")
def validate_cmd(
    hld_file: Path,
    strict: bool,
    output_format: str,
    draft: bool,
) -> None:
    """Validate HLD and IR without generating artifacts."""
    pipeline = _run_validation_pipeline(hld_file, draft=draft)

    if output_format == "json":
        payload = pipeline.report.to_dict()
        payload["draft_warnings"] = pipeline.draft_warnings
        click.echo(json.dumps(payload, indent=2, ensure_ascii=False))
    else:
        _print_validation_text(pipeline.report, pipeline.model, pipeline.draft_warnings)

    should_fail = pipeline.report.has_errors() or (strict and bool(pipeline.report.warnings))
    raise click.exceptions.Exit(1 if should_fail else 0)


@main.command("lint")
@click.argument("hld_file", type=click.Path(exists=True, path_type=Path))
@click.option("--strict", is_flag=True, help="Fail on lint warnings.")
@click.option(
    "--output",
    "output_format",
    type=click.Choice(["text", "json"]),
    default="text",
    show_default=True,
)
@click.option("--draft", is_flag=True, help="Allow best-effort draft mode if IR is missing.")
@click.option(
    "--profile",
    "profile_ref",
    default="default",
    show_default=True,
    help="Notation profile: 'default' or path to YAML file.",
)
@click.option(
    "--view-pack",
    type=click.Choice(["draft", "review", "full"]),
    default="full",
    show_default=True,
    help="Which diagram pack readability limits should apply to during lint.",
)
def lint_cmd(
    hld_file: Path,
    strict: bool,
    output_format: str,
    draft: bool,
    profile_ref: str,
    view_pack: ViewPack,
) -> None:
    """Run architecture lint checks on top of schema validation."""
    profile = _load_profile_or_fail(profile_ref)
    pipeline = _run_validation_pipeline(hld_file, draft=draft)
    lint_issues = (
        run_lint_checks(
            hld_file,
            pipeline.model,
            pipeline.block.start_line,
            profile=profile,
            view_pack=view_pack,
        )
        if pipeline.model is not None
        else []
    )

    if output_format == "json":
        payload = pipeline.report.to_dict()
        payload["draft_warnings"] = pipeline.draft_warnings
        payload["lint"] = [issue.to_dict() for issue in lint_issues]
        click.echo(json.dumps(payload, indent=2, ensure_ascii=False))
    else:
        _print_validation_text(pipeline.report, pipeline.model, pipeline.draft_warnings)
        _print_lint_text(lint_issues)

    lint_has_errors = any(issue.level.value == "error" for issue in lint_issues)
    lint_has_warnings = any(issue.level.value == "warning" for issue in lint_issues)

    has_validation_errors = pipeline.report.has_errors() or pipeline.model is None
    should_fail = has_validation_errors or lint_has_errors or (strict and lint_has_warnings)
    raise click.exceptions.Exit(1 if should_fail else 0)


@main.command("generate")
@click.argument(
    "hld_file",
    type=click.Path(exists=True, path_type=Path, dir_okay=True, file_okay=True),
)
@click.option(
    "--format",
    "output_format",
    type=click.Choice(["c4", "plantuml", "archimate", "drawio", "all"]),
    default="all",
    show_default=True,
)
@click.option(
    "--output-dir",
    type=click.Path(path_type=Path),
    default=DEFAULT_OUTPUT_DIR,
    show_default=True,
    help="Output directory. Use 'auto' to isolate artifacts per HLD file.",
)
@click.option("--validate-only", is_flag=True, help="Only run validation.")
@click.option(
    "--lint/--no-lint",
    "run_lint",
    default=True,
    show_default=True,
    help="Run lint quality gates after schema validation.",
)
@click.option("--force", is_flag=True, help="Overwrite existing files.")
@click.option("--draft", is_flag=True, help="Use draft mode when IR block is missing.")
@click.option(
    "--render-images/--no-render-images",
    default=True,
    show_default=True,
    help="Render diagram images from generated sources.",
)
@click.option(
    "--image-format",
    type=click.Choice(["png", "svg", "both"]),
    default="png",
    show_default=True,
    help="Rendered image format for diagram previews.",
)
@click.option(
    "--view-pack",
    type=click.Choice(["draft", "review", "full"]),
    default="full",
    show_default=True,
    help="Diagram pack density (draft=compact, full=all views).",
)
@click.option(
    "--profile",
    "profile_ref",
    default="default",
    show_default=True,
    help="Notation profile: 'default' or path to YAML file.",
)
@click.option(
    "--reproducible",
    is_flag=True,
    help="Make outputs deterministic (removes timestamps and stabilizes ordering).",
)
@click.option(
    "--notation",
    "notation_mode",
    type=click.Choice(["default", "standard"]),
    default="default",
    show_default=True,
    help="Diagram notation mode: default (current) or standard (PlantUML=ArchiMate, draw.io=C4).",
)
@click.option(
    "--with-drawio",
    is_flag=True,
    help="Write draw.io artifact (diagrams/drawio). By default draw.io is omitted for --format all.",
)
@click.option(
    "--keep-plantuml-sources",
    is_flag=True,
    help="Keep PlantUML sources (.puml, relations-legend.md). By default only rendered images are kept.",
)
def generate_cmd(
    hld_file: Path,
    output_format: str,
    output_dir: Path,
    validate_only: bool,
    run_lint: bool,
    force: bool,
    draft: bool,
    render_images: bool,
    image_format: str,
    view_pack: ViewPack,
    profile_ref: str,
    reproducible: bool,
    notation_mode: NotationMode,
    with_drawio: bool,
    keep_plantuml_sources: bool,
) -> None:
    """Validate and generate architecture artifacts."""
    profile = _load_profile_or_fail(profile_ref)
    if hld_file.is_dir():
        # Prefer IR-ready files to avoid generating templates for prose-only docs.
        md_files = sorted(hld_file.rglob("*.ir.md"))
        if not md_files:
            md_files = sorted(hld_file.rglob("*.md"))
        if not md_files:
            raise click.ClickException(f"No markdown files found under: {hld_file}")

        click.echo(f"Found {len(md_files)} file(s) under: {hld_file}")
        successes: list[GenerationResult] = []
        failures: list[GenerationResult] = []

        for file_path in _iter_with_progress(md_files, label="Generating"):
            try:
                res = _generate_one(
                    hld_file=file_path,
                    output_dir=output_dir,
                    output_format=output_format,
                    validate_only=validate_only,
                    run_lint=run_lint,
                    force=force,
                    draft=draft,
                    render_images=render_images,
                    image_format=image_format,
                    view_pack=view_pack,
                    profile=profile,
                    reproducible=reproducible,
                    notation_mode=notation_mode,
                    with_drawio=with_drawio,
                    keep_plantuml_sources=keep_plantuml_sources,
                    batch_root=hld_file,
                )
            except click.ClickException as exc:
                # Keep batch runs resilient: report and continue.
                resolved = _resolve_batch_output_dir(output_dir, file_path, batch_root=hld_file)
                click.echo(f"FAILED: {file_path} ({exc.message})")
                res = GenerationResult(
                    hld_file=file_path,
                    output_dir=resolved,
                    status="failed",
                    report_paths=[],
                    generated_files=[],
                )

            if res.status == "success":
                successes.append(res)
            else:
                failures.append(res)

        click.echo("")
        click.echo("Batch summary:")
        click.echo(f"  Success: {len(successes)}")
        click.echo(f"  Failed:  {len(failures)}")
        if successes:
            click.echo("  Output (examples):")
            for item in successes[:3]:
                click.echo(f"    - {item.output_dir}")
        if failures:
            click.echo("  Failed files (first 10):")
            for item in failures[:10]:
                click.echo(f"    - {item.hld_file}")
                if item.report_paths:
                    click.echo(f"      reports: {', '.join(str(p) for p in item.report_paths)}")

        raise click.exceptions.Exit(1 if failures else 0)

    result = _generate_one(
        hld_file=hld_file,
        output_dir=output_dir,
        output_format=output_format,
        validate_only=validate_only,
        run_lint=run_lint,
        force=force,
        draft=draft,
        render_images=render_images,
        image_format=image_format,
        view_pack=view_pack,
        profile=profile,
        reproducible=reproducible,
        notation_mode=notation_mode,
        with_drawio=with_drawio,
        keep_plantuml_sources=keep_plantuml_sources,
        batch_root=None,
    )

    raise click.exceptions.Exit(0 if result.status == "success" else 1)


@main.command("draft-ir")
@click.argument("hld_file", type=click.Path(exists=True, path_type=Path))
@click.option("--append", is_flag=True, help="Append IR block to existing file.")
@click.option(
    "--llm-provider",
    type=click.Choice(["openai", "anthropic"]),
    default="openai",
    show_default=True,
)
def draft_ir_cmd(hld_file: Path, append: bool, llm_provider: str) -> None:
    """Generate best-effort IR block from free-form HLD text."""
    source = hld_file.read_text(encoding="utf-8")
    draft = generate_draft_ir(source)

    block = render_ir_block(draft.ir_data)
    todo_section = _render_todo_section(draft.todo)

    if append:
        target_path = hld_file
        content = source.rstrip() + "\n\n" + block + todo_section
    else:
        target_path = hld_file.with_name(f"{hld_file.name}.draft.md")
        content = source.rstrip() + "\n\n" + block + todo_section

    target_path.write_text(content, encoding="utf-8")

    click.echo(f"Provider hint: {llm_provider} (heuristic mode used locally)")
    click.echo(f"Draft IR saved: {target_path}")
    for warning in draft.warnings:
        click.echo(f"WARNING: {warning}")


@main.command("init")
@click.option(
    "--template",
    "template_type",
    type=click.Choice(["microservices", "monolith", "event-driven", "layered", "minimal"]),
    default="microservices",
    show_default=True,
)
def init_cmd(template_type: str) -> None:
    """Create starter HLD template files in current directory."""
    current_dir = Path.cwd()
    target_hld = current_dir / "hld-template.md"
    target_readme = current_dir / "README.md"

    if target_hld.exists() or target_readme.exists():
        raise click.ClickException(
            "Target files already exist (hld-template.md or README.md). "
            "Use an empty folder or rename existing files.",
        )

    template_dir = Path(__file__).resolve().parent / "templates"
    hld_template = (template_dir / "hld_template.md").read_text(encoding="utf-8")
    hld_template = hld_template.replace("{{TEMPLATE_TYPE}}", template_type)
    ir_template = (template_dir / "ir_template.yaml").read_text(encoding="utf-8")
    hld_content = hld_template.replace("{{IR_TEMPLATE}}", ir_template.rstrip())

    readme_content = _render_init_readme(template_type)

    target_hld.write_text(hld_content, encoding="utf-8")
    target_readme.write_text(readme_content, encoding="utf-8")

    click.echo(f"Created: {target_hld}")
    click.echo(f"Created: {target_readme}")


@main.command("watch")
@click.argument("directory", type=click.Path(exists=True, file_okay=False, path_type=Path))
@click.option(
    "--format",
    "output_format",
    type=click.Choice(["c4", "plantuml", "archimate", "drawio", "all"]),
    default="all",
    show_default=True,
)
@click.option(
    "--output-dir",
    type=click.Path(path_type=Path),
    default=DEFAULT_OUTPUT_DIR,
    show_default=True,
    help="Output directory. Use 'auto' to isolate artifacts per HLD file.",
)
@click.option(
    "--lint/--no-lint",
    "run_lint",
    default=True,
    show_default=True,
    help="Run lint quality gates after schema validation.",
)
@click.option("--force", is_flag=True, help="Overwrite existing generated files.")
@click.option(
    "--render-images/--no-render-images",
    default=True,
    show_default=True,
    help="Render diagram images after generation.",
)
@click.option(
    "--image-format",
    type=click.Choice(["png", "svg", "both"]),
    default="png",
    show_default=True,
    help="Rendered image format for watch mode.",
)
@click.option(
    "--view-pack",
    type=click.Choice(["draft", "review", "full"]),
    default="full",
    show_default=True,
    help="Diagram pack density (draft=compact, full=all views).",
)
@click.option(
    "--profile",
    "profile_ref",
    default="default",
    show_default=True,
    help="Notation profile: 'default' or path to YAML file.",
)
@click.option(
    "--reproducible",
    is_flag=True,
    help="Make outputs deterministic (removes timestamps and stabilizes ordering).",
)
@click.option(
    "--notation",
    "notation_mode",
    type=click.Choice(["default", "standard"]),
    default="default",
    show_default=True,
    help="Diagram notation mode: default (current) or standard (PlantUML=ArchiMate, draw.io=C4).",
)
@click.option(
    "--with-drawio",
    is_flag=True,
    help="Write draw.io artifact (diagrams/drawio). By default draw.io is omitted for --format all.",
)
@click.option(
    "--keep-plantuml-sources",
    is_flag=True,
    help="Keep PlantUML sources (.puml, relations-legend.md). By default only rendered images are kept.",
)
def watch_cmd(
    directory: Path,
    output_format: str,
    output_dir: Path,
    run_lint: bool,
    force: bool,
    render_images: bool,
    image_format: str,
    view_pack: ViewPack,
    profile_ref: str,
    reproducible: bool,
    notation_mode: NotationMode,
    with_drawio: bool,
    keep_plantuml_sources: bool,
) -> None:
    """Watch a directory and auto-generate artifacts on markdown changes."""
    profile = _load_profile_or_fail(profile_ref)
    try:
        from watchdog.events import FileSystemEvent, FileSystemEventHandler
        from watchdog.observers import Observer
    except ImportError as exc:
        raise click.ClickException(
            "watchdog is required for watch mode. Install dependencies first.",
        ) from exc

    class HLDHandler(FileSystemEventHandler):
        def __init__(self) -> None:
            self._last: dict[str, float] = {}

        def on_created(self, event: FileSystemEvent) -> None:
            self._handle(event)

        def on_modified(self, event: FileSystemEvent) -> None:
            self._handle(event)

        def _handle(self, event: FileSystemEvent) -> None:
            if event.is_directory:
                return
            path = Path(event.src_path)
            if path.suffix.lower() != ".md":
                return

            now = time.time()
            last = self._last.get(str(path), 0.0)
            if now - last < 0.8:
                return
            self._last[str(path)] = now

            click.echo(f"Detected change: {path}")
            _generate_single_file(
                path,
                output_dir,
                output_format,
                run_lint,
                force,
                render_images,
                image_format,
                view_pack,
                profile,
                reproducible,
                notation_mode,
                with_drawio=with_drawio,
                keep_plantuml_sources=keep_plantuml_sources,
                watch_root=directory,
            )

    observer = Observer()
    handler = HLDHandler()
    observer.schedule(handler, str(directory), recursive=True)
    observer.start()

    click.echo(f"Watching directory: {directory}")
    if output_dir == AUTO_OUTPUT_DIR_TOKEN:
        click.echo("Auto output enabled: artifacts will be written under output/<hld-relative-path>/")
    click.echo("Press Ctrl+C to stop")

    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        observer.stop()
        observer.join()


def _run_validation_pipeline(hld_file: Path, draft: bool) -> PipelineResult:
    ir_data, block, draft_warnings = _load_ir_data(hld_file, draft=draft)
    validator = IRValidator()
    model, report = validator.validate(hld_file, ir_data, block.start_line)

    return PipelineResult(
        model=model,
        report=report,
        block=block,
        draft_warnings=draft_warnings,
    )


def _load_ir_data(hld_file: Path, draft: bool) -> tuple[dict, IRBlock, list[str]]:
    try:
        ir_data, block = load_ir_from_hld(hld_file)
        return ir_data, block, []
    except IRBlockNotFoundError as exc:
        if not draft:
            template_path = write_ir_template(hld_file, title=hld_file.stem.replace("-", " ").title())
            message = "\n".join(
                [
                    "No archpipe-model block found in HLD file.",
                    "",
                    "Add an IR block:",
                    "```archpipe-model",
                    "version: \"1.0\"",
                    "metadata:",
                    "  title: \"Your System\"",
                    "...",
                    "```",
                    "",
                    f"Template generated: {template_path}",
                    "Run `archpipe init` or `archpipe draft-ir <file>` for guidance.",
                ],
            )
            raise click.ClickException(message) from exc

        markdown = hld_file.read_text(encoding="utf-8")
        draft_result = generate_draft_ir(markdown)
        block = IRBlock(raw_yaml=yaml.safe_dump(draft_result.ir_data), start_line=1, end_line=1)
        return draft_result.ir_data, block, draft_result.warnings
    except IRYAMLError as exc:
        line_info = f"Line {exc.line}: " if exc.line else ""
        raise click.ClickException(
            f"Invalid YAML syntax in archpipe-model block. {line_info}{exc}",
        ) from exc
    except HLDParserError as exc:
        raise click.ClickException(str(exc)) from exc


def _run_generators(
    model: IRModel,
    output_dir: Path,
    output_format: str,
    force: bool,
    view_pack: ViewPack,
    profile: NotationProfile,
    reproducible: bool,
    notation_mode: NotationMode,
    with_drawio: bool,
    keep_plantuml_sources: bool,
    render_images: bool,
) -> list[Path]:
    output_dir.mkdir(parents=True, exist_ok=True)

    registry = {
        "c4": C4Generator(profile=profile),
        "plantuml": PlantUMLGenerator(profile=profile, view_pack=view_pack, notation_mode=notation_mode),
        "archimate": ArchimateGenerator(profile=profile, view_pack=view_pack, reproducible=reproducible),
        "drawio": DrawIOGenerator(
            profile=profile,
            view_pack=view_pack,
            reproducible=reproducible,
            notation_mode=notation_mode,
        ),
    }

    if output_format == "all":
        keys: list[str] = ["c4", "archimate"]
        if render_images or keep_plantuml_sources:
            keys.append("plantuml")
        if with_drawio:
            keys.append("drawio")
        selected = [registry[key] for key in keys]
    elif output_format == "plantuml":
        if not (render_images or keep_plantuml_sources):
            raise click.ClickException(
                "PlantUML output would be empty. Enable --render-images or pass --keep-plantuml-sources.",
            )
        selected = [registry["plantuml"]]
    else:
        # For explicit formats, keep behavior unchanged (e.g. --format drawio always writes draw.io).
        selected = [registry[output_format]]

    generated_files: list[Path] = []
    for generator in selected:
        try:
            generated_files.extend(generator.generate(model, output_dir, force=force))
        except GeneratorError as exc:
            raise click.ClickException(str(exc)) from exc

    return generated_files


def _prune_plantuml_sources(output_dir: Path, generated_files: list[Path]) -> list[Path]:
    """Return PlantUML source files that should be removed from output."""
    pruned: list[Path] = []
    plantuml_dir = output_dir / "diagrams" / "plantuml"
    for path in generated_files:
        if not path.exists():
            continue
        if not str(path).startswith(str(plantuml_dir)):
            continue
        if path.suffix == ".puml" or path.name == "relations-legend.md":
            pruned.append(path)
    return pruned


def _cleanup_drawio_artifacts(output_dir: Path) -> None:
    """Remove draw.io outputs (diagrams/drawio) if present."""
    drawio_dir = output_dir / "diagrams" / "drawio"
    if not drawio_dir.exists():
        return
    for path in sorted(drawio_dir.rglob("*"), reverse=True):
        try:
            if path.is_file() or path.is_symlink():
                path.unlink(missing_ok=True)
            elif path.is_dir():
                path.rmdir()
        except OSError:
            # Best-effort cleanup; never fail generation because of cleanup.
            pass
    try:
        drawio_dir.rmdir()
    except OSError:
        pass


def _cleanup_plantuml_sources(output_dir: Path) -> None:
    """Remove PlantUML sources from diagrams/plantuml if present."""
    plantuml_dir = output_dir / "diagrams" / "plantuml"
    if not plantuml_dir.exists():
        return
    candidates = list(plantuml_dir.glob("*.puml")) + [plantuml_dir / "relations-legend.md"]
    for path in candidates:
        try:
            path.unlink(missing_ok=True)
        except OSError:
            pass


def _write_reports(
    output_dir: Path,
    hld_file: Path,
    report: ValidationReport,
    model: IRModel | None,
    generated_files: list[Path],
    status: str,
    duration_ms: int,
    view_pack: ViewPack,
    profile_name: str,
    force: bool,
    lint_issues: list[ValidationIssue],
    reproducible: bool,
) -> list[Path]:
    reports_dir = output_dir / "reports"
    reports_dir.mkdir(parents=True, exist_ok=True)

    generated_files = sorted(generated_files, key=lambda path: path.as_posix())

    markdown = build_validation_markdown(
        hld_file=hld_file,
        report=report,
        model=model,
        generated_files=generated_files,
        status="✅ SUCCESS" if status == "success" else "❌ FAILED",
        lint_issues=lint_issues,
        reproducible=reproducible,
    )

    report_json = build_report_json(
        hld_file=hld_file,
        report=report,
        model=model,
        generated_files=generated_files,
        status=status,
        duration_ms=duration_ms,
        lint_issues=lint_issues,
        reproducible=reproducible,
    )
    report_json["view_pack"] = view_pack
    report_json["profile"] = profile_name
    report_json["archpipe_cli_version"] = ARCHPIPE_VERSION
    report_json["reproducible"] = reproducible

    validation_path = reports_dir / "validation.md"
    build_json_path = reports_dir / "build-report.json"
    review_path = reports_dir / "review-report.md"

    if not force and (validation_path.exists() or build_json_path.exists() or review_path.exists()):
        raise click.ClickException(
            "Report files already exist. Use --force or remove previous reports.",
        )

    review_markdown = build_review_markdown(
        hld_file=hld_file,
        report=report,
        generated_files=generated_files,
        output_dir=output_dir,
    )

    validation_path.write_text(markdown, encoding="utf-8")
    build_json_path.write_text(
        json.dumps(report_json, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    review_path.write_text(review_markdown, encoding="utf-8")

    return [validation_path, build_json_path, review_path]


def _print_validation_text(
    report: ValidationReport,
    model: IRModel | None,
    draft_warnings: Iterable[str],
) -> None:
    for warning in draft_warnings:
        click.echo(f"DRAFT WARNING: {warning}")

    for issue in report.issues:
        prefix = "ERROR" if issue.level.value == "error" else "WARNING"
        line = issue.location.line if issue.location.line is not None else "?"
        file_part = f"{Path(issue.location.file).name}:" if issue.location.file else ""
        click.echo(f"{prefix} {issue.code} ({file_part}{line}): {issue.message}")
        if getattr(issue, "suggestion", None):
            click.echo(f"  hint: {issue.suggestion}")

    if model:
        click.echo("\nModel statistics:")
        click.echo(f"  Containers: {report.metrics.get('containers', 0)}")
        click.echo(f"  Relationships: {report.metrics.get('relationships', 0)}")
        click.echo(f"  External systems: {report.metrics.get('external_systems', 0)}")
        click.echo(f"  Quality attributes: {report.metrics.get('quality_attributes', 0)}")


def _print_lint_text(issues: Iterable) -> None:
    issues = list(issues)
    if not issues:
        click.echo("\nLint checks: no findings")
        return

    click.echo("\nLint findings:")
    for issue in issues:
        line = issue.location.line if issue.location.line is not None else "?"
        file_part = f"{Path(issue.location.file).name}:" if issue.location.file else ""
        level = issue.level.value.upper() if getattr(issue, "level", None) else "LINT"
        click.echo(f"{level} {issue.code} ({file_part}{line}): {issue.message}")
        if getattr(issue, "suggestion", None):
            click.echo(f"  hint: {issue.suggestion}")


def _load_profile_or_fail(profile_ref: str) -> NotationProfile:
    try:
        return load_profile(profile_ref)
    except ProfileError as exc:
        raise click.ClickException(str(exc)) from exc


def _render_todo_section(items: list[str]) -> str:
    lines = ["", "## Draft TODO", ""]
    lines.extend(f"- [ ] {item}" for item in items)
    lines.append("")
    return "\n".join(lines)


def _render_init_readme(template_type: str) -> str:
    return "\n".join(
        [
            "# HLD Template Workspace",
            "",
            f"Initialized with `{template_type}` template.",
            "",
            "## Next Steps",
            "",
            "1. Fill `hld-template.md` sections with your architecture details.",
            "2. Keep the `archpipe-model` block as source of truth.",
            "3. Validate: `archpipe validate hld-template.md`.",
            "4. Generate artifacts: `archpipe generate hld-template.md --format all`.",
            "",
        ],
    )


def _resolve_output_dir(
    output_dir: Path,
    hld_file: Path,
    watch_root: Path | None = None,
) -> Path:
    if output_dir != AUTO_OUTPUT_DIR_TOKEN:
        return output_dir

    auto_subdir = _auto_output_subdir(hld_file, watch_root=watch_root)
    return DEFAULT_OUTPUT_DIR / auto_subdir


def _resolve_batch_output_dir(
    output_dir: Path,
    hld_file: Path,
    batch_root: Path,
) -> Path:
    """Always isolate outputs per file when running in batch mode."""
    if output_dir == AUTO_OUTPUT_DIR_TOKEN:
        return _resolve_output_dir(output_dir, hld_file, watch_root=batch_root)
    return output_dir / _auto_output_subdir(hld_file, watch_root=batch_root)


def _auto_output_subdir(hld_file: Path, watch_root: Path | None = None) -> Path:
    hld_abs = hld_file.resolve()
    relative: Path | None = None

    if watch_root is not None:
        watch_root_abs = watch_root.resolve()
        if hld_abs.is_relative_to(watch_root_abs):
            relative = hld_abs.relative_to(watch_root_abs)

    if relative is None:
        cwd_abs = Path.cwd().resolve()
        if hld_abs.is_relative_to(cwd_abs):
            relative = hld_abs.relative_to(cwd_abs)
        else:
            relative = Path(hld_file.name)

    relative_no_suffix = relative.with_suffix("")
    parts = relative_no_suffix.parts or (hld_file.stem,)
    sanitized_parts = [part for part in (_sanitize_slug_part(item) for item in parts) if part]

    if not sanitized_parts:
        sanitized_parts = ["hld"]

    return Path(*sanitized_parts)


def _sanitize_slug_part(value: str) -> str:
    chars: list[str] = []
    for char in value.lower():
        if char.isalnum() or char in {"-", "_", "."}:
            chars.append(char)
        else:
            chars.append("-")

    slug = "".join(chars).strip("-_.")
    while "--" in slug:
        slug = slug.replace("--", "-")
    while "__" in slug:
        slug = slug.replace("__", "_")

    return slug


def _generate_one(
    hld_file: Path,
    output_dir: Path,
    output_format: str,
    validate_only: bool,
    run_lint: bool,
    force: bool,
    draft: bool,
    render_images: bool,
    image_format: str,
    view_pack: ViewPack,
    profile: NotationProfile,
    reproducible: bool,
    notation_mode: NotationMode,
    with_drawio: bool,
    keep_plantuml_sources: bool,
    batch_root: Path | None,
) -> GenerationResult:
    started = time.perf_counter()
    resolved_output_dir = (
        _resolve_batch_output_dir(output_dir, hld_file, batch_root=batch_root)
        if batch_root is not None
        else _resolve_output_dir(output_dir, hld_file)
    )
    # Avoid per-file noise in batch runs; show auto-dir only for single-file mode.
    if output_dir == AUTO_OUTPUT_DIR_TOKEN and batch_root is None:
        click.echo(f"Auto output dir: {resolved_output_dir}")

    pipeline = _run_validation_pipeline(hld_file, draft=draft)
    _print_validation_text(pipeline.report, pipeline.model, pipeline.draft_warnings)

    if pipeline.report.has_errors() or pipeline.model is None:
        report_paths = _write_reports(
            resolved_output_dir,
            hld_file,
            pipeline.report,
            pipeline.model,
            [],
            "failed",
            0 if reproducible else _duration_ms(started),
            view_pack=view_pack,
            profile_name=profile.name,
            force=True,
            lint_issues=[],
            reproducible=reproducible,
        )
        return GenerationResult(
            hld_file=hld_file,
            output_dir=resolved_output_dir,
            status="failed",
            report_paths=report_paths,
            generated_files=[],
        )

    model = pipeline.model
    lint_issues = (
        run_lint_checks(
            hld_file,
            model,
            pipeline.block.start_line,
            profile=profile,
            view_pack=view_pack,
        )
        if run_lint
        else []
    )
    if run_lint:
        _print_lint_text(lint_issues)

    lint_has_errors = any(issue.level.value == "error" for issue in lint_issues)
    if lint_has_errors:
        report_paths = _write_reports(
            resolved_output_dir,
            hld_file,
            pipeline.report,
            model,
            [],
            "failed",
            0 if reproducible else _duration_ms(started),
            view_pack=view_pack,
            profile_name=profile.name,
            force=True,
            lint_issues=lint_issues,
            reproducible=reproducible,
        )
        click.echo(f"FAILED: {hld_file}")
        click.echo(f"  reports: {', '.join(str(path) for path in report_paths)}")
        return GenerationResult(
            hld_file=hld_file,
            output_dir=resolved_output_dir,
            status="failed",
            report_paths=report_paths,
            generated_files=[],
        )

    if validate_only:
        report_paths = _write_reports(
            resolved_output_dir,
            hld_file,
            pipeline.report,
            model,
            [],
            "success",
            0 if reproducible else _duration_ms(started),
            view_pack=view_pack,
            profile_name=profile.name,
            force=True,
            lint_issues=lint_issues,
            reproducible=reproducible,
        )
        click.echo(f"Validated: {hld_file} -> {resolved_output_dir}")
        return GenerationResult(
            hld_file=hld_file,
            output_dir=resolved_output_dir,
            status="success",
            report_paths=report_paths,
            generated_files=[],
        )

    generated_files = _run_generators(
        model=model,
        output_dir=resolved_output_dir,
        output_format=output_format,
        force=force,
        view_pack=view_pack,
        profile=profile,
        reproducible=reproducible,
        notation_mode=notation_mode,
        with_drawio=with_drawio,
        keep_plantuml_sources=keep_plantuml_sources,
        render_images=render_images,
    )

    if render_images:
        render_result = render_artifact_images(
            output_dir=resolved_output_dir,
            output_format=output_format,
            image_format=image_format,
            force=force,
            source_files=generated_files,
        )
        for warning in render_result.warnings:
            click.echo(f"RENDER WARNING: {warning}")
        for image in render_result.files:
            click.echo(f"Rendered: {image}")
        generated_files.extend(render_result.files)

    # Enforce "no extra artifacts by default" even on subsequent runs with existing output dirs.
    if output_format != "drawio" and not with_drawio:
        _cleanup_drawio_artifacts(resolved_output_dir)

    if not keep_plantuml_sources:
        _cleanup_plantuml_sources(resolved_output_dir)
        pruned = _prune_plantuml_sources(resolved_output_dir, generated_files)
        if pruned:
            generated_files = [p for p in generated_files if p not in pruned]

    report_paths = _write_reports(
        resolved_output_dir,
        hld_file,
        pipeline.report,
        model,
        generated_files,
        "success",
        0 if reproducible else _duration_ms(started),
        view_pack=view_pack,
        profile_name=profile.name,
        force=True,
        lint_issues=lint_issues,
        reproducible=reproducible,
    )

    click.echo(f"SUCCESS: {hld_file} -> {resolved_output_dir}")
    return GenerationResult(
        hld_file=hld_file,
        output_dir=resolved_output_dir,
        status="success",
        report_paths=report_paths,
        generated_files=generated_files,
    )


def _generate_single_file(
    hld_file: Path,
    output_dir: Path,
    output_format: str,
    run_lint: bool,
    force: bool,
    render_images: bool,
    image_format: str,
    view_pack: ViewPack,
    profile: NotationProfile,
    reproducible: bool,
    notation_mode: NotationMode,
    with_drawio: bool,
    keep_plantuml_sources: bool,
    watch_root: Path | None = None,
) -> None:
    try:
        res = _generate_one(
            hld_file=hld_file,
            output_dir=output_dir,
            output_format=output_format,
            validate_only=False,
            run_lint=run_lint,
            force=force,
            draft=False,
            render_images=render_images,
            image_format=image_format,
            view_pack=view_pack,
            profile=profile,
            reproducible=reproducible,
            notation_mode=notation_mode,
            with_drawio=with_drawio,
            keep_plantuml_sources=keep_plantuml_sources,
            batch_root=watch_root,
        )
        if res.status == "success":
            click.echo(f"Generated {len(res.generated_files)} artifact(s) for {hld_file.name}")
    except click.ClickException as exc:
        click.echo(f"Generation failed for {hld_file.name}: {exc.message}")


def _iter_with_progress(items: list[Path], label: str) -> Iterable[Path]:
    """Best-effort progress display (rich if available, else plain)."""
    try:
        from rich.progress import BarColumn, Progress, SpinnerColumn, TextColumn, TimeElapsedColumn
    except Exception:
        for idx, item in enumerate(items, start=1):
            click.echo(f"[{idx}/{len(items)}] {label}: {item}")
            yield item
        return

    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        BarColumn(),
        TextColumn("{task.completed}/{task.total}"),
        TimeElapsedColumn(),
        transient=True,
    ) as progress:
        task = progress.add_task(label, total=len(items))
        for item in items:
            progress.update(task, advance=1, description=f"{label}: {item.name}")
            yield item


def _duration_ms(started: float) -> int:
    return int((time.perf_counter() - started) * 1000)


if __name__ == "__main__":
    main()
