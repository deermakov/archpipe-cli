from __future__ import annotations

from pathlib import Path

import pytest

from archpipe.parser.hld_parser import IRBlockNotFoundError, IRYAMLError, load_ir_from_hld


FIXTURE = Path(__file__).parent / "fixtures" / "example-hld.md"


def test_load_ir_from_hld_parses_fixture() -> None:
    data, block = load_ir_from_hld(FIXTURE)
    assert data["version"] == "1.0"
    assert data["system"]["name"] == "Web App"
    assert block.start_line > 0


def test_missing_block_raises(tmp_path: Path) -> None:
    file_path = tmp_path / "missing.md"
    file_path.write_text("# No IR\n", encoding="utf-8")

    with pytest.raises(IRBlockNotFoundError):
        load_ir_from_hld(file_path)


def test_invalid_yaml_raises(tmp_path: Path) -> None:
    file_path = tmp_path / "invalid.md"
    file_path.write_text(
        "# Invalid\n\n```archpipe-model\nversion: \"1.0\"\nmetadata: [\n```\n",
        encoding="utf-8",
    )

    with pytest.raises(IRYAMLError):
        load_ir_from_hld(file_path)
