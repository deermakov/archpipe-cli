# Quickstart (RU)

Цель: за 3–5 минут развернуть генератор и получить схемы/отчёт из HLD-файла.

## 1) Установка (разово)

Требования: Docker Desktop (и `docker compose`).

```bash
./archpipe setup
```

Проверка:

```bash
./archpipe --help
./archpipe version
```

## 2) Проверить HLD (валидатор + линт)

```bash
./archpipe validate inbox/example-hld.md
./archpipe lint inbox/example-hld.md --strict
```

Если IR-блок отсутствует, `validate` завершится ошибкой и создаст шаблон `<file>.template` (его можно использовать как основу).

## 3) Сгенерировать артефакты

Рекомендуемый режим (все форматы, авто-вывод в отдельную папку):

```bash
./archpipe generate inbox/example-hld.md --format all --output-dir auto --notation standard --view-pack review --force
```

Если нужен draw.io (editable схема), включите явным флагом:

```bash
./archpipe generate inbox/example-hld.md --format all --with-drawio --output-dir auto --notation standard --view-pack review --force
```

Если нужны исходники PlantUML (`.puml`), включите явным флагом:

```bash
./archpipe generate inbox/example-hld.md --format all --keep-plantuml-sources --output-dir auto --notation standard --view-pack review --force
```

Если нужно только исходники без превью:

```bash
./archpipe generate inbox/example-hld.md --format all --output-dir auto --notation standard --view-pack review --no-render-images --force
```

## 4) Где искать результаты

`--output-dir auto` создаёт папку по “slug” входного файла, например:

- `output/inbox/example-hld/`

Внутри:

- `diagrams/drawio/architecture.drawio` (только при `--with-drawio` или `--format drawio`)
- `diagrams/plantuml/*.puml`
- `reports/review-report.md`
- `reports/validation.md`

## 5) Пачка файлов (batch)

```bash
./archpipe generate inbox --format all --output-dir auto --notation standard --view-pack review --force
```

## 6) Watch (автоперегенерация)

```bash
./archpipe watch inbox --format all --output-dir auto --notation standard
```
