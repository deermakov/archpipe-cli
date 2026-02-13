# MANUAL

## 0) Цель и принципы

Цель: из HLD (Markdown) получать набор понятных HLD-диаграмм (Draw.io + ArchiMate + C4 + PlantUML) для быстрого обсуждения/принятия решений, без ручной дорисовки "каждый раз с нуля".

## Быстрый старт

Разово подготовить окружение (Docker):

```bash
./archpipe setup
```

Проверить HLD:

```bash
./archpipe validate inbox/example.ir.md
./archpipe lint inbox/example.ir.md --profile default --view-pack review
```

Сгенерировать артефакты:

```bash
./archpipe generate inbox/example.ir.md --format all --output-dir auto --view-pack review --force
./archpipe generate inbox/example.ir.md --format all --output-dir auto --view-pack review --notation standard --force
```

Сгенерировать пачкой для папки:

```bash
./archpipe generate inbox --format all --output-dir auto --notation standard --force
```

Где искать результаты:

- `output/<slug>/diagrams/drawio/architecture.drawio`
- `output/<slug>/diagrams/plantuml/*.puml`
- `output/<slug>/reports/review-report.md`

Базовые принципы:

- **IR-first**: схемы строятся из структурированной модели (IR), а не угадываются из описательного текста.
- **Детерминированность**: один и тот же IR должен давать один и тот же результат (в режиме `--reproducible`).
- **Tag-driven**: классификация элементов и состав view определяется тегами (`kind:*`, `role:*`), а не именами/ID.

## 1) Требования к входным данным (HLD + IR)

### 1.1 Формат входного файла

- Формат файла: `Markdown` (`.md`).
- В документе должен быть блок:

````markdown
## Architecture Model (IR)

```archpipe-model
...
```
````

Источник истины для генерации: **только** блок `archpipe-model`.

### 1.1.1 Минимальный пример IR

Ниже минимальный пример, от которого можно отталкиваться (абстрактный, без домена):

````markdown
## Architecture Model (IR)

```archpipe-model
version: "1.0"
metadata:
  title: "Example System"
  description: "High-level architecture for discussions"
  author: "Architecture Team"
  date: "2026-02-09"
  tags: ["microservices"]

system:
  name: "Example System"
  description: "A system that exposes UI, owns a process status, and integrates with externals"

containers:
  - id: web-ui
    name: "Web UI"
    technology: "Browser"
    description: "User-facing UI"
    type: container
    tags: ["kind:client"]

  - id: api-gateway
    name: "API"
    technology: "HTTP API"
    description: "Entry point for UI"
    type: container
    tags: ["kind:process", "role:sot-status"]

  - id: read-model
    name: "Read Projection"
    technology: "Service"
    description: "Read-optimized API for lists/search/export"
    type: container
    tags: ["kind:read"]

  - id: main-db
    name: "Main DB"
    technology: "PostgreSQL"
    description: "Primary storage"
    type: database
    tags: ["kind:data"]

external-systems:
  - id: external-provider
    name: "External Provider"
    description: "External system integration"
    tags: ["kind:product"]

relationships:
  - from: web-ui
    to: api-gateway
    description: "Calls API"
    protocol: "HTTPS"
    patterns: ["read", "write"]

  - from: api-gateway
    to: main-db
    description: "Reads/writes business data"
    protocol: "SQL"
    patterns: ["read", "write"]

  - from: api-gateway
    to: read-model
    description: "Projects state for read scenarios"
    protocol: "Internal"
    patterns: ["project"]

  - from: api-gateway
    to: external-provider
    description: "Sends async commands"
    protocol: "Async"
    patterns: ["async", "idempotent", "no_pii"]

  - from: external-provider
    to: api-gateway
    description: "Returns async results"
    protocol: "Async"
    patterns: ["async", "idempotent", "no_pii"]
```
````

### 1.2 Обязательные секции IR

Обязательные секции:

- `version`
- `metadata.title`
- `system.name`
- `system.description`
- `containers[]` (как минимум: `id`, `name`, `technology`, `description`, `type`, `tags`)
- `relationships[]` (как минимум: `from`, `to`, `description`; `protocol` рекомендуется)

### 1.3 Правила целостности модели

MUST:

- YAML валиден.
- Все `id` уникальны (в `containers`, `components`, `external-systems`).
- Все `relationships.from/to` и `integrations.from/to` указывают на существующие элементы.
- `type` только из: `container`, `database`, `queue`, `cache`, `component`.

### 1.4 Теги (обязательная семантика)

MUST:

- Каждый элемент должен иметь **явную семантику размещения на схемах** через тег `kind:*`.
- Должен быть **ровно один** владелец статуса процесса (Single Source of Truth) с тегом `role:sot-status`.

Рекомендуемый словарь `kind:*` (по умолчанию поддерживается профилем `default`):

- `kind:client` интерфейсы/клиенты
- `kind:process` процессные/координирующие сервисы (write-model)
- `kind:read` read-модели/витрины/API чтения
- `kind:data` хранилища/снапшоты/БД
- `kind:async` брокер/очереди/топики (логические)
- `kind:rules` матрицы/политики/конфиг правил
- `kind:product` продуктовые контуры/внешние домены продукта
- `kind:ops` аудит/наблюдаемость/эксплуатационные компоненты

Примеры дополнительных тегов:

- `external` или `scope:external` помечает элемент как внешний (если он моделируется как container, а не через `external-systems`).
- `legacy` (или `role:legacy`) помечает legacy/источник, к которому запрещены online-вызовы.

### 1.5 Протоколы и patterns для связей

Рекомендуется стандартизировать:

- `relationships[].protocol`: `HTTPS`, `SQL`, `Batch`, `Async`, `Internal`, и т.п.
- `relationships[].patterns`: `read`, `write`, `batch`, `async`, `project`, `idempotent`, `no_pii`, `pii`

Важно:

- Async-связи должны быть помечены как `protocol: Async` и/или `patterns: ["async"]`.
- Если по async-каналу потенциально проходят ПДн, это должно быть явно помечено `patterns: ["pii"]` и **линтер упадет**. Используйте `no_pii` для подтверждения, что payload обезличен/токенизирован.

## 2) Набор диаграмм (view-packs)

`archpipe-cli` генерирует набор view на основе правил в профиле (см. `diagram.views` в профиле).

MUST view-pack (для HLD/review):

- **Context**: граница решения + внешние акторы/системы + ключевые интеграции.
- **Solution / Container**: внутренняя архитектура решения, SoT статуса, read-проекция, sync vs async.
- **Data / Ingestion**: витрина -> канонизация/QC -> read-модели.
- **Process flow**: старт -> async команда -> результат -> проекция статуса (без LLD).
- **Operations**: аудит/наблюдаемость/DLQ как зоны ответственности (упрощенно).

CLI-режимы плотности:

- `--view-pack draft` минимальный набор (быстрее, меньше наложений).
- `--view-pack review` набор для командного ревью.
- `--view-pack full` полный набор (максимум view/легенд).

## 3) Читаемость как SLA (качество диаграмм)

MUST:

- Для каждого view задаются лимиты `max_nodes` / `max_edges` в профиле.
- Если лимит превышен, линтер падает с ошибкой `L300` и сообщением "слишком сложная схема для HLD".
- Подписи на стрелках должны быть короткими. Для полного текста используйте `diagrams/plantuml/relations-legend.md`.

## 4) Lint и quality gates

Команда: `archpipe lint <hld-file>`.

MUST (ошибка, fail):

- Нет владельца статуса процесса (`role:sot-status`) или их несколько.
- Async-связь помечена как содержащая ПДн (`patterns: ["pii"]`) и не помечена `no_pii`.
- Есть online-вызов к legacy (элемент помечен `legacy`, а связь не `Batch/ETL/File`).
- Read-модель выполняет write/update (по `patterns: ["write"|"update"|...]`).
- Любое view превышает лимиты читаемости (`max_nodes`/`max_edges`) для выбранного `--view-pack`.

SHOULD (warning):

- placeholder в `technology` (`TBD`, `unknown` и т.п.)
- слишком короткие `relationships[].description`
- отсутствуют `metadata.author` / `metadata.date`
- высокая fan-out связанность (как сигнал к разбиению view)

## 5) Determinism / Diff-friendly output

Флаг: `--reproducible`.

MUST:

- Убирает/стабилизирует timestamps (Draw.io `modified`, отчеты).
- Стабилизирует порядок элементов/связей, чтобы повторная генерация давала одинаковые файлы.
- В `reports/build-report.json` фиксируются: `codex_cli_version`, `profile`, `view_pack`, `reproducible`.

## 6) Выходные артефакты и структура output

По умолчанию (`--output-dir ./output`):

- `diagrams/drawio/architecture.drawio`
- `diagrams/c4/workspace.dsl`, `diagrams/c4/styles.dsl`
- `diagrams/plantuml/*.puml` + `diagrams/plantuml/relations-legend.md`
- `archimate/model.xml` + `archimate/viewpoints.md`
- `reports/validation.md`, `reports/build-report.json`, `reports/review-report.md`

Для нескольких HLD (multi-project) используйте:

- `--output-dir auto`

Тогда артефакты пишутся в:

- `./output/<relative-path-without-extension>/...`

Например:

- `archpipe generate inbox/a/b/system.md --output-dir auto`
создаст:
- `output/inbox/a/b/system/...`

## 7) Docker-first (без установок на macOS)

Рекомендуемый способ запуска:

```bash
cd archpipe-cli

# Валидация
./scripts/archpipe-docker validate inbox/example.ir.md

# Lint (quality gates)
./scripts/archpipe-docker lint inbox/example.ir.md --profile default --view-pack review

# Генерация
./scripts/archpipe-docker generate inbox/example.ir.md --format all --output-dir auto --view-pack review --force

# Генерация (standard notation): PlantUML=ArchiMate, draw.io=C4
./scripts/archpipe-docker generate inbox/example.ir.md --format all --output-dir auto --view-pack review --notation standard --force

# Тесты (в контейнере)
./scripts/pytest-docker
```

ArchiMate HTML report из `model.xml` (для быстрых превью без GUI Archi):

```bash
./scripts/archi-report-docker /work/output/<...>/archimate/model.xml /work/output/<...>/archimate/html-report
```

## 8) Готовый промпт: HLD -> `archpipe-model` (strict-ready)

````text
Ты — архитектор и валидатор IR-модели для archpipe-cli. Работай строго как инженер по Architecture-as-Code.

Цель:
Из входного HLD (Markdown) построить корректный блок:
```archpipe-model
...
```

Правила:
1) Не придумывай данные, которых нет в HLD.
2) IR-first: текст HLD не является источником истины, если противоречит IR.
3) Если данных недостаточно, сначала задай уточняющие вопросы. Пока есть открытые вопросы по обязательным полям и тегам — финальный archpipe-model не выдавай.
4) Для каждого элемента обязательно добавь tags:
   - kind:* (client|process|read|data|async|rules|product|ops)
   - и ровно один элемент пометь role:sot-status
5) Для async-связей помечай protocol/patterns как async, и явно указывай no_pii (если payload обезличен).

Обязательные секции IR:
- version
- metadata.title
- system.name
- system.description
- containers[] (id, name, technology, description, type, tags)
- relationships[] (from, to, description; protocol желательно; patterns желательно)

Проверки перед выдачей:
- все id уникальны;
- from/to ссылаются на существующие id;
- type только: container, database, queue, cache, component;
- YAML валиден;
- есть ровно один role:sot-status;
- у каждого элемента есть kind:*.

Формат:
Шаг 1: прочитай HLD.
Шаг 2: если не хватает данных — верни блок "Уточнения" со списком вопросов.
Шаг 3: после ответов — верни только:
```archpipe-model
...
```
````

## 9) DoR / DoD (для эпика "Улучшение генератора диаграмм")

DoR:

- Зафиксирован целевой view-pack (draft/review/full) и список обязательных view.
- Зафиксирован словарь `kind:*` и правила маппинга tags -> view (profile).
- Есть 2–3 fixture HLD (минимальный/средний/сложный) и ожидаемые артефакты.
- Зафиксированы лимиты читаемости `max_nodes/max_edges` и политика при превышении (lint fail или split).

DoD:

- `archpipe validate/lint/generate` проходят на всех fixture.
- В `--reproducible` режиме повторная генерация дает идентичные файлы (включая drawio).
- Все обязательные view присутствуют (Draw.io страницы, C4, PlantUML, ArchiMate viewpoints).
- Документация обновлена (как размечать tags/patterns, как настраивать profile/view-pack).
- Есть тесты на schema/validation, lint rules и reproducible output.
