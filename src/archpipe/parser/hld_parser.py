"""Parse HLD markdown and extract the archpipe-model block."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import re
from typing import Any

import yaml
from yaml import YAMLError


class HLDParserError(Exception):
    """Base parser exception."""


class IRBlockNotFoundError(HLDParserError):
    """Raised when no archpipe-model code fence is found."""


class IRYAMLError(HLDParserError):
    """Raised when the IR YAML content is invalid."""

    def __init__(self, message: str, line: int | None = None) -> None:
        super().__init__(message)
        self.line = line


@dataclass(slots=True)
class IRBlock:
    """Extracted IR block metadata."""

    raw_yaml: str
    start_line: int
    end_line: int


_IR_BLOCK_PATTERN = re.compile(r"```archpipe-model\s*\n(.*?)\n```", re.DOTALL)


def extract_ir_block(markdown: str) -> IRBlock:
    """Extract the first archpipe-model fenced block from markdown text."""
    match = _IR_BLOCK_PATTERN.search(markdown)
    if not match:
        raise IRBlockNotFoundError(
            "No archpipe-model block found in HLD file.",
        )

    prefix = markdown[: match.start()]
    start_line = prefix.count("\n") + 1
    raw_yaml = match.group(1)
    block_lines = match.group(0).count("\n") + 1
    end_line = start_line + block_lines - 1

    return IRBlock(raw_yaml=raw_yaml, start_line=start_line, end_line=end_line)


def parse_ir_yaml(ir_block: IRBlock) -> dict[str, Any]:
    """Parse YAML content from extracted IR block."""
    try:
        parsed = yaml.safe_load(ir_block.raw_yaml)
    except YAMLError as exc:
        line = None
        if hasattr(exc, "problem_mark") and exc.problem_mark:
            line = ir_block.start_line + 1 + exc.problem_mark.line
        raise IRYAMLError(str(exc), line=line) from exc

    if parsed is None:
        raise IRYAMLError("IR block is empty.", line=ir_block.start_line + 1)

    if not isinstance(parsed, dict):
        raise IRYAMLError(
            "IR block must be a YAML mapping at top-level.",
            line=ir_block.start_line + 1,
        )

    return parsed


def load_ir_from_hld(hld_path: Path) -> tuple[dict[str, Any], IRBlock]:
    """Load and parse IR block from HLD file."""
    markdown = hld_path.read_text(encoding="utf-8")
    block = extract_ir_block(markdown)
    parsed = parse_ir_yaml(block)
    return parsed, block


def write_ir_template(target_path: Path, title: str = "Your System") -> Path:
    """Write an IR template file next to target HLD."""
    template_path = (
        Path(__file__).resolve().parent.parent / "templates" / "ir_template.yaml"
    )
    template = template_path.read_text(encoding="utf-8")
    rendered = template.replace("{{TITLE}}", title)

    output_path = target_path.with_suffix(target_path.suffix + ".template")
    output_path.write_text(rendered, encoding="utf-8")
    return output_path
