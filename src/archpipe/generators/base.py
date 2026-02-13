"""Base interfaces for artifact generators."""

from __future__ import annotations

from abc import ABC, abstractmethod
from pathlib import Path

from archpipe.models.ir_schema import IRModel


class GeneratorError(Exception):
    """Generic generation error."""


class BaseGenerator(ABC):
    """Base generator contract."""

    name: str

    @abstractmethod
    def generate(self, model: IRModel, output_dir: Path, force: bool = False) -> list[Path]:
        """Generate artifacts and return file paths."""

    @staticmethod
    def _write_file(path: Path, content: str, force: bool) -> None:
        if path.exists() and not force:
            raise GeneratorError(
                f"File already exists: {path}. Use --force to overwrite.",
            )
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
