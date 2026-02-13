# Programmatic API

## Parse IR

```python
from pathlib import Path
from archpipe.parser.hld_parser import load_ir_from_hld

ir_data, block = load_ir_from_hld(Path("my-hld.md"))
```

## Validate IR

```python
from archpipe.parser.ir_validator import IRValidator

validator = IRValidator()
model, report = validator.validate(Path("my-hld.md"), ir_data, block.start_line)
```

## Generate Artifacts

```python
from pathlib import Path
from archpipe.generators.c4_generator import C4Generator

generator = C4Generator()
paths = generator.generate(model, Path("output"), force=True)
```

## Draft IR

```python
from archpipe.parser.draft_ir import generate_draft_ir, render_ir_block

result = generate_draft_ir(markdown_text)
ir_block = render_ir_block(result.ir_data)
```
