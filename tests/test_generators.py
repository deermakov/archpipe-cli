from __future__ import annotations

from pathlib import Path

from archpipe.generators.archimate_generator import ArchimateGenerator
from archpipe.generators.c4_generator import C4Generator
from archpipe.generators.drawio_generator import DrawIOGenerator
from archpipe.generators.plantuml_generator import PlantUMLGenerator
from archpipe.models.ir_schema import IRModel
from archpipe.parser.hld_parser import load_ir_from_hld


FIXTURE = Path(__file__).parent / "fixtures" / "example-hld.md"


def _load_model() -> IRModel:
    data, _ = load_ir_from_hld(FIXTURE)
    return IRModel.model_validate(data)


def test_c4_generator_creates_workspace(tmp_path: Path) -> None:
    model = _load_model()
    generator = C4Generator()

    paths = generator.generate(model, tmp_path, force=False)
    workspace = tmp_path / "diagrams" / "c4" / "workspace.dsl"

    assert workspace in paths
    assert "workspace" in workspace.read_text(encoding="utf-8")


def test_plantuml_generator_creates_files(tmp_path: Path) -> None:
    model = _load_model()
    generator = PlantUMLGenerator()

    paths = generator.generate(model, tmp_path, force=False)

    assert len(paths) == 8
    assert (tmp_path / "diagrams" / "plantuml" / "components.puml").exists()
    assert (tmp_path / "diagrams" / "plantuml" / "components-full.puml").exists()
    assert (tmp_path / "diagrams" / "plantuml" / "full-system.puml").exists()
    assert (tmp_path / "diagrams" / "plantuml" / "data-stores.puml").exists()
    assert (tmp_path / "diagrams" / "plantuml" / "deployment.puml").exists()
    assert (tmp_path / "diagrams" / "plantuml" / "flow-process.puml").exists()
    assert (tmp_path / "diagrams" / "plantuml" / "flow-ingestion.puml").exists()
    assert (tmp_path / "diagrams" / "plantuml" / "relations-legend.md").exists()


def test_plantuml_generator_standard_notation_adds_archimate_views(tmp_path: Path) -> None:
    model = _load_model()
    generator = PlantUMLGenerator(notation_mode="standard")

    paths = generator.generate(model, tmp_path, force=False)

    assert (tmp_path / "diagrams" / "plantuml" / "archimate-context.puml").exists()
    assert (tmp_path / "diagrams" / "plantuml" / "archimate-container.puml").exists()
    assert any(path.name == "archimate-context.puml" for path in paths)


def test_archimate_generator_creates_xml(tmp_path: Path) -> None:
    model = _load_model()
    generator = ArchimateGenerator()

    paths = generator.generate(model, tmp_path, force=False)
    xml_path = tmp_path / "archimate" / "model.xml"
    viewpoints_path = tmp_path / "archimate" / "viewpoints.md"

    assert xml_path in paths
    xml_text = xml_path.read_text(encoding="utf-8")
    assert "<model" in xml_text
    assert "<views>" in xml_text
    assert "System Context" in xml_text
    assert viewpoints_path in paths
    assert "Viewpoints" in viewpoints_path.read_text(encoding="utf-8")


def test_drawio_generator_creates_multi_page_file(tmp_path: Path) -> None:
    model = _load_model()
    generator = DrawIOGenerator()

    paths = generator.generate(model, tmp_path, force=False)
    drawio_path = tmp_path / "diagrams" / "drawio" / "architecture.drawio"

    assert drawio_path in paths
    text = drawio_path.read_text(encoding="utf-8")
    assert "<mxfile" in text
    assert 'name="Context"' in text
    assert 'name="Solution Container"' in text
    assert 'name="Data + Async"' in text


def test_drawio_generator_standard_notation_adds_c4_pages(tmp_path: Path) -> None:
    model = _load_model()
    generator = DrawIOGenerator(notation_mode="standard")

    generator.generate(model, tmp_path, force=False)
    drawio_path = tmp_path / "diagrams" / "drawio" / "architecture.drawio"
    text = drawio_path.read_text(encoding="utf-8")
    assert 'name="C4 Context"' in text
    assert 'name="C4 Container"' in text


def test_drawio_generator_reproducible_is_byte_stable(tmp_path: Path) -> None:
    model = _load_model()
    generator = DrawIOGenerator(reproducible=True)

    out1 = tmp_path / "run1"
    out2 = tmp_path / "run2"
    generator.generate(model, out1, force=True)
    generator.generate(model, out2, force=True)

    p1 = out1 / "diagrams" / "drawio" / "architecture.drawio"
    p2 = out2 / "diagrams" / "drawio" / "architecture.drawio"
    assert p1.read_bytes() == p2.read_bytes()
