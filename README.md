# archpipe-cli

`archpipe-cli` генерирует архитектурные артефакты из HLD (Markdown) на основе встроенного IR-блока `archpipe-model`.
Цель: быстро получать схемы и отчёты для обсуждения/ревью без ручной отрисовки.

## Быстрый старт (для коллег)

Требования: установлен Docker Desktop (включая `docker compose`).

1) Разовая установка/проверка окружения:

```bash
./archpipe setup
```

2) Сгенерировать артефакты из одного HLD-файла:

```bash
./archpipe generate inbox/your-hld.ir.md --format all --output-dir auto --notation standard --force
```

3) Где искать результаты:

- `output/<file-slug>/diagrams/plantuml/*.png|*.svg` (превью диаграмм)
- `output/<file-slug>/diagrams/plantuml/*.puml` (исходники PlantUML только при `--keep-plantuml-sources`)
- `output/<file-slug>/diagrams/drawio/architecture.drawio` (только при `--with-drawio` или `--format drawio`)
- `output/<file-slug>/reports/review-report.md` (сводный отчёт для ревью)

## Что считается входом

HLD должен содержать IR-блок:

````markdown
## Architecture Model (IR)

```archpipe-model
version: "1.0"
...
```
````

Подробнее про IR:
- `IR_GUIDE.md`

## Основные команды

Все команды запускаются через обёртку `./archpipe` (она использует Docker, локальный Python не нужен):

```bash
./archpipe --help
./archpipe validate inbox/your-hld.ir.md
./archpipe lint inbox/your-hld.ir.md --strict
./archpipe generate inbox/your-hld.ir.md --format all --output-dir auto --notation standard --force
./archpipe watch inbox --format all --output-dir auto --notation standard
```

Подробности про IR и требования к модели: `IR_GUIDE.md`.

## Отчёт ArchiMate (headless)

Если нужен HTML/PNG отчёт из `archimate/model.xml` (без установки Archi на ноутбук), используйте контейнер `archi-export`:

```bash
./scripts/archi-report-docker /work/output/<slug>/archimate/model.xml /work/output/<slug>/archimate/html-report
```

## Поддержка и Troubleshooting

- Docker не запущен/недоступен: запустите Docker Desktop, проверьте `docker info` и `docker compose version`, затем повторите `./archpipe setup`.
- `docker compose` не найден: обновите Docker Desktop (нужен Compose v2).
- Не найден IR-блок `archpipe-model`: выполните `./archpipe validate <file.md>` (создаст `<file>.template`) или `./archpipe draft-ir <file.md>` (черновик IR). Справочник: `IR_GUIDE.md`.
- `lint`/`validate` ругаются на ID/теги/ссылки: начните с `./archpipe lint <file.md> --strict`, проверьте уникальность `id`, существование всех `relationships.from/to`, наличие `kind:*` в `tags`.
- “Файлы уже существуют” в `output/`: используйте `--output-dir auto` и/или добавьте `--force`, если перезапись ожидаема.
- Генерация медленная или не нужны картинки: добавьте `--no-render-images`. Для `png` и `svg` используйте `--image-format both`.
- Нет `diagrams/drawio/architecture.drawio`: draw.io по умолчанию не пишется для `--format all`. Добавьте `--with-drawio` или используйте `--format drawio`.
- Нет `.puml` в `diagrams/plantuml/`: исходники PlantUML по умолчанию не сохраняются. Добавьте `--keep-plantuml-sources`.
- Проблемы с отчётом ArchiMate (headless): отчёт строится через контейнер `archi-export`. На Apple Silicon возможно выполнение через эмуляцию из-за `platform: linux/amd64` (это ожидаемо).
