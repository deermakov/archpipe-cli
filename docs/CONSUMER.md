# archpipe-cli: кратко для потребителей (RU)

## 1) Разово подготовить окружение

```bash
./archpipe setup
```

## 2) Сгенерировать схемы и отчёты

Один файл:

```bash
./archpipe generate inbox/your-hld.ir.md --format all --output-dir auto --notation standard --force
```

Папка (batch):

```bash
./archpipe generate inbox --format all --output-dir auto --notation standard --force
```

## 3) Где искать результаты

- `output/<slug>/diagrams/plantuml/*.png|*.svg`
- `output/<slug>/diagrams/plantuml/*.puml` (только при `--keep-plantuml-sources`)
- `output/<slug>/diagrams/drawio/architecture.drawio` (только при `--with-drawio` или `--format drawio`)
- `output/<slug>/reports/review-report.md`

## 4) Полезное

- Быстрее без картинок: `--no-render-images`
- Проверить IR и подсказки: `./archpipe validate <file>` и `./archpipe lint <file> --strict`
