# Architecture

## High-Level Flow

1. Parse HLD markdown and extract `archpipe-model` fenced YAML.
2. Validate schema and semantics against Pydantic IR models.
3. Generate selected artifacts.
4. Persist validation/build reports.

## Modules

- `src/archpipe/cli.py`: command entry point and orchestration
- `src/archpipe/parser/hld_parser.py`: IR extraction and YAML parsing
- `src/archpipe/parser/ir_validator.py`: schema + semantic + quality checks
- `src/archpipe/parser/draft_ir.py`: best-effort IR inference
- `src/archpipe/models/ir_schema.py`: Pydantic schema (IR contract)
- `src/archpipe/generators/*.py`: output generators
- `src/archpipe/renderers.py`: diagram image rendering (local tools or Docker fallback)
- `src/archpipe/reports.py`: markdown/json report builders

## Validation Levels

- CRITICAL syntax: missing block, invalid YAML
- CRITICAL schema: missing required fields, invalid enum values
- ERROR semantic: unknown references, duplicate IDs
- WARNING quality: missing protocols/deployment/NFR attributes

## Generator Contracts

All generators implement `BaseGenerator.generate(model, output_dir, force)` and return list of generated file paths.

## Draft Mode

If `--draft` is enabled and IR block is missing, the parser infers a minimal model from text and marks output as `DRAFT - NOT GUARANTEED`.

## Extensibility

- New export format: add generator module + register in `cli.py`
- New IR element type: extend enum in `ir_schema.py` and map in generators
- New validator: add to `IRValidator` pipeline
