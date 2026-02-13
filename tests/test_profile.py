from __future__ import annotations

from pathlib import Path

from archpipe.models.profile import DEFAULT_PROFILE, load_profile


def test_load_default_profile() -> None:
    profile = load_profile("default")
    assert profile.name == DEFAULT_PROFILE.name


def test_load_profile_from_yaml(tmp_path: Path) -> None:
    profile_path = tmp_path / "profile.yaml"
    profile_path.write_text(
        "\n".join(
            [
                "name: custom",
                "plantuml:",
                "  dpi: 220",
                "c4:",
                "  auto_layout: tb",
            ],
        ),
        encoding="utf-8",
    )

    profile = load_profile(str(profile_path))

    assert profile.name == "custom"
    assert profile.plantuml.dpi == 220
    assert profile.c4.auto_layout == "tb"
