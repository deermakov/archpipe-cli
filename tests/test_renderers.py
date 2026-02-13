from __future__ import annotations

from pathlib import Path

from archpipe.renderers import render_artifact_images
from archpipe.renderers import _tune_c4_plantuml_sources


def test_render_images_without_sources(tmp_path: Path) -> None:
    result = render_artifact_images(
        output_dir=tmp_path,
        output_format="all",
        image_format="png",
        force=False,
    )

    assert any("workspace.dsl not found" in warning for warning in result.warnings)
    assert any("No PlantUML sources found" in warning for warning in result.warnings)


def test_render_images_without_renderers(monkeypatch, tmp_path: Path) -> None:
    puml_dir = tmp_path / "diagrams" / "plantuml"
    puml_dir.mkdir(parents=True)
    (puml_dir / "sample.puml").write_text("@startuml\nA->B\n@enduml\n", encoding="utf-8")

    monkeypatch.setattr("archpipe.renderers.shutil.which", lambda _: None)

    result = render_artifact_images(
        output_dir=tmp_path,
        output_format="plantuml",
        image_format="png",
        force=False,
    )

    assert not result.files
    assert any("renderer is unavailable" in warning for warning in result.warnings)


def test_tune_c4_plantuml_sources_adjusts_layout(tmp_path: Path) -> None:
    c4_dir = tmp_path / "diagrams" / "c4"
    c4_dir.mkdir(parents=True)
    source = c4_dir / "structurizr-Container-001.puml"
    source.write_text(
        "\n".join(
            [
                "@startuml",
                "left to right direction",
                "skinparam ranksep 60",
                "skinparam nodesep 30",
                "@enduml",
                "",
            ],
        ),
        encoding="utf-8",
    )

    warnings = _tune_c4_plantuml_sources(c4_dir)
    tuned = source.read_text(encoding="utf-8")

    assert warnings == []
    assert "skinparam linetype ortho" in tuned
    assert "skinparam ArrowFontSize 9" in tuned
    assert "left to right direction" in tuned
    assert "skinparam ranksep 120" in tuned
    assert "skinparam nodesep 80" in tuned
