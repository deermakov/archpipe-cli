from __future__ import annotations

from pathlib import Path

from archpipe.parser.hld_parser import load_ir_from_hld
from archpipe.parser.ir_validator import IRValidator


FIXTURE = Path(__file__).parent / "fixtures" / "example-hld.md"


def test_validator_accepts_valid_fixture() -> None:
    data, block = load_ir_from_hld(FIXTURE)
    validator = IRValidator()
    model, report = validator.validate(FIXTURE, data, block.start_line)

    assert model is not None
    assert not report.errors
    assert report.metrics["containers"] == 2
    assert report.metrics["relationships"] == 1


def test_validator_detects_missing_reference() -> None:
    data, block = load_ir_from_hld(FIXTURE)
    data["relationships"][0]["to"] = "missing-db"

    validator = IRValidator()
    model, report = validator.validate(FIXTURE, data, block.start_line)

    assert model is not None
    assert any(issue.code == "E006" for issue in report.errors)


def test_validator_detects_duplicate_ids() -> None:
    data, block = load_ir_from_hld(FIXTURE)
    data["containers"].append(
        {
            "id": "webapp",
            "name": "Duplicate",
            "technology": "Python",
            "description": "Duplicate",
            "type": "container",
        },
    )

    validator = IRValidator()
    model, report = validator.validate(FIXTURE, data, block.start_line)

    assert model is not None
    assert any(issue.code == "E004" for issue in report.errors)
