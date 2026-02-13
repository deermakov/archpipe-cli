from __future__ import annotations

from pathlib import Path

from click.testing import CliRunner

from archpipe.cli import main


FIXTURE = Path(__file__).parent / "fixtures" / "example-hld.md"


def test_validate_command_success() -> None:
    runner = CliRunner()
    result = runner.invoke(main, ["validate", str(FIXTURE)])

    assert result.exit_code == 0
    assert "Model statistics" in result.output


def test_generate_command_creates_outputs(tmp_path: Path) -> None:
    runner = CliRunner()
    result = runner.invoke(
        main,
        [
            "generate",
            str(FIXTURE),
            "--format",
            "all",
            "--output-dir",
            str(tmp_path),
        ],
    )

    assert result.exit_code == 0
    assert (tmp_path / "diagrams" / "c4" / "workspace.dsl").exists()
    # By default PlantUML sources are not kept; only rendered images are expected.
    assert (tmp_path / "diagrams" / "plantuml" / "components.png").exists()
    assert not (tmp_path / "diagrams" / "plantuml" / "components.puml").exists()
    # By default draw.io is omitted for --format all (opt-in via --with-drawio).
    assert not (tmp_path / "diagrams" / "drawio" / "architecture.drawio").exists()
    assert (tmp_path / "archimate" / "model.xml").exists()
    assert (tmp_path / "reports" / "validation.md").exists()
    assert (tmp_path / "reports" / "review-report.md").exists()


def test_generate_all_cleans_stale_drawio_and_plantuml_sources(tmp_path: Path) -> None:
    # Arrange: create stale artifacts in output dir.
    (tmp_path / "diagrams" / "drawio").mkdir(parents=True)
    (tmp_path / "diagrams" / "drawio" / "architecture.drawio").write_text("stale", encoding="utf-8")
    (tmp_path / "diagrams" / "plantuml").mkdir(parents=True)
    (tmp_path / "diagrams" / "plantuml" / "components.puml").write_text("@startuml", encoding="utf-8")

    runner = CliRunner()
    result = runner.invoke(
        main,
        [
            "generate",
            str(FIXTURE),
            "--format",
            "all",
            "--output-dir",
            str(tmp_path),
            "--notation",
            "standard",
            "--force",
        ],
    )

    assert result.exit_code == 0
    assert not (tmp_path / "diagrams" / "drawio" / "architecture.drawio").exists()
    assert not (tmp_path / "diagrams" / "plantuml" / "components.puml").exists()


def test_generate_with_draft_view_pack_limits_files(tmp_path: Path) -> None:
    runner = CliRunner()
    result = runner.invoke(
        main,
        [
            "generate",
            str(FIXTURE),
            "--format",
            "plantuml",
            "--output-dir",
            str(tmp_path),
            "--view-pack",
            "draft",
            "--no-render-images",
            "--keep-plantuml-sources",
        ],
    )

    assert result.exit_code == 0
    assert (tmp_path / "diagrams" / "plantuml" / "components.puml").exists()
    assert (tmp_path / "diagrams" / "plantuml" / "flow-process.puml").exists()
    assert not (tmp_path / "diagrams" / "plantuml" / "components-full.puml").exists()


def test_generate_reproducible_stabilizes_reports(tmp_path: Path) -> None:
    runner = CliRunner()
    result = runner.invoke(
        main,
        [
            "generate",
            str(FIXTURE),
            "--format",
            "drawio",
            "--output-dir",
            str(tmp_path),
            "--no-render-images",
            "--reproducible",
            "--force",
        ],
    )

    assert result.exit_code == 0
    report = (tmp_path / "reports" / "build-report.json").read_text(encoding="utf-8")
    assert '"timestamp": "1970-01-01T00:00:00Z"' in report
    assert '"reproducible": true' in report


def test_generate_with_standard_notation_adds_archimate_and_c4(tmp_path: Path) -> None:
    runner = CliRunner()
    result = runner.invoke(
        main,
        [
            "generate",
            str(FIXTURE),
            "--format",
            "all",
            "--output-dir",
            str(tmp_path),
            "--no-render-images",
            "--notation",
            "standard",
            "--with-drawio",
            "--keep-plantuml-sources",
        ],
    )

    assert result.exit_code == 0

    archimate_puml = tmp_path / "diagrams" / "plantuml" / "archimate-context.puml"
    assert archimate_puml.exists()
    assert "!include <archimate/Archimate>" in archimate_puml.read_text(encoding="utf-8")

    drawio = tmp_path / "diagrams" / "drawio" / "architecture.drawio"
    text = drawio.read_text(encoding="utf-8")
    assert 'name="C4 Context"' in text
    assert 'name="C4 Container"' in text


def test_generate_directory_processes_multiple_files(tmp_path: Path) -> None:
    # Arrange a small directory with two HLD files.
    root = tmp_path / "hlds"
    root.mkdir(parents=True)
    (root / "a.md").write_text(FIXTURE.read_text(encoding="utf-8"), encoding="utf-8")
    (root / "b.md").write_text(FIXTURE.read_text(encoding="utf-8"), encoding="utf-8")

    runner = CliRunner()
    result = runner.invoke(
        main,
        [
            "generate",
            str(root),
            "--format",
            "drawio",
            "--output-dir",
            str(tmp_path / "out"),
            "--no-render-images",
            "--reproducible",
            "--force",
        ],
    )

    assert result.exit_code == 0
    # Output is isolated per file under the provided output directory.
    assert (tmp_path / "out" / "a" / "diagrams" / "drawio" / "architecture.drawio").exists()
    assert (tmp_path / "out" / "b" / "diagrams" / "drawio" / "architecture.drawio").exists()


def test_lint_command_success() -> None:
    runner = CliRunner()
    result = runner.invoke(main, ["lint", str(FIXTURE)])

    assert result.exit_code == 0
    assert "Lint checks: no findings" in result.output


def test_validate_missing_ir_generates_template(tmp_path: Path) -> None:
    hld = tmp_path / "missing-ir.md"
    hld.write_text("# Missing IR\n", encoding="utf-8")

    runner = CliRunner()
    result = runner.invoke(main, ["validate", str(hld)])

    assert result.exit_code != 0
    assert "No archpipe-model block found" in result.output
    assert (tmp_path / "missing-ir.md.template").exists()
