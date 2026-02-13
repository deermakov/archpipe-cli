# Contributing

## Setup

```bash
python3 -m pip install -e ".[dev]"
```

## Quality Gates

```bash
black src tests
ruff check src tests
mypy src/archpipe
pytest
```

## Coding Standards

- Python 3.11+
- Type hints everywhere
- Google-style docstrings
- Keep functions under 100 lines
- Prefer deterministic transformations over heuristic logic

## Tests

- Add unit tests for parser, validator, generators
- Add fixture-based integration checks for CLI
- Keep fixtures readable and realistic
