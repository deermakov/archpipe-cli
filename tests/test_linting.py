from __future__ import annotations

from pathlib import Path

from archpipe.linting import run_lint_checks
from archpipe.models.ir_schema import IRModel
from archpipe.models.profile import DEFAULT_PROFILE, DiagramSettings, NotationProfile, ViewSpec
from archpipe.parser.hld_parser import load_ir_from_hld


FIXTURE = Path(__file__).parent / "fixtures" / "example-hld.md"


def _load_model() -> tuple[IRModel, int]:
    data, block = load_ir_from_hld(FIXTURE)
    return IRModel.model_validate(data), block.start_line


def test_lint_fails_when_kind_tag_missing() -> None:
    model, start_line = _load_model()
    model.containers[0].tags = []

    issues = run_lint_checks(FIXTURE, model, start_line, profile=DEFAULT_PROFILE, view_pack="draft")
    assert any(issue.code == "L100" and issue.level.value == "error" for issue in issues)


def test_lint_fails_when_sot_missing() -> None:
    model, start_line = _load_model()
    model.containers[0].tags = ["kind:process"]

    issues = run_lint_checks(FIXTURE, model, start_line, profile=DEFAULT_PROFILE, view_pack="draft")
    assert any(issue.code == "L200" and issue.level.value == "error" for issue in issues)


def test_lint_fails_for_pii_over_async() -> None:
    model, start_line = _load_model()
    model.relationships[0].protocol = "Async"
    model.relationships[0].patterns = ["async", "pii"]

    issues = run_lint_checks(FIXTURE, model, start_line, profile=DEFAULT_PROFILE, view_pack="draft")
    assert any(issue.code == "L202" and issue.level.value == "error" for issue in issues)


def test_lint_fails_for_non_batch_legacy_link() -> None:
    model, start_line = _load_model()
    # Mark DB as legacy to exercise the gate.
    model.containers[1].tags = ["kind:data", "legacy"]
    model.relationships[0].protocol = "HTTPS"

    issues = run_lint_checks(FIXTURE, model, start_line, profile=DEFAULT_PROFILE, view_pack="draft")
    assert any(issue.code == "L203" and issue.level.value == "error" for issue in issues)


def test_lint_fails_when_read_model_writes() -> None:
    model, start_line = _load_model()
    model.containers[0].tags = ["kind:read", "role:sot-status"]
    model.relationships[0].patterns = ["write"]

    issues = run_lint_checks(FIXTURE, model, start_line, profile=DEFAULT_PROFILE, view_pack="draft")
    assert any(issue.code == "L204" and issue.level.value == "error" for issue in issues)


def test_lint_fails_when_view_exceeds_limits() -> None:
    model, start_line = _load_model()
    tiny_profile = NotationProfile(
        name="tiny",
        diagram=DiagramSettings(
            require_kind_tags=True,
            kind_tag_key="kind",
            kind_fill_colors=DEFAULT_PROFILE.diagram.kind_fill_colors,
            views={
                "context": ViewSpec(
                    include_kinds=["process", "data"],
                    include_external=True,
                    max_nodes=1,
                    max_edges=10,
                ),
            },
        ),
    )

    issues = run_lint_checks(FIXTURE, model, start_line, profile=tiny_profile, view_pack="draft")
    assert any(issue.code == "L300" and issue.level.value == "error" for issue in issues)

