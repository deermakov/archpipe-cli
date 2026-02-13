# IR Guide (RU): `archpipe-model`

IR (Intermediate Representation) в `archpipe-cli` это структурированная модель архитектуры в YAML, встроенная прямо в HLD (Markdown) в fenced-блоке `archpipe-model`.

Ключевой принцип: генератор **не угадывает архитектуру из описательного текста**. Источник истины для схем и отчётов это IR.

## Где находится IR в HLD

В документе должен быть блок:

````markdown
## Architecture Model (IR)

```archpipe-model
version: "1.0"
metadata:
  title: "Example"
system:
  name: "Example"
containers: []
external-systems: []
relationships: []
```
````

## Минимально необходимая структура

MUST (минимум для стабильной генерации):

- `version`
- `metadata.title`
- `system.name`
- `containers[]`
- `relationships[]` (может быть пустым, но схемы будут беднее)

## ID (правило стабильности)

Используйте стабильные `id` в kebab-case:

- `api-gateway`, `read-model`, `process-db`

`id` используется как якорь на схемах и влияет на детерминированность (диффы, повторяемость, “золотые” артефакты).

## Типы элементов (type)

Поддерживаемые значения `type`:

- `container` (сервис/подсистема/приложение)
- `component` (вложенный элемент внутри контейнера, если используется)
- `database`
- `queue`
- `cache`

## Теги (определяют семантику и раскладку)

Каждый элемент должен иметь `tags`, и минимум один тег `kind:*`, чтобы генератор понимал роль на диаграммах.

Рекомендуемый словарь `kind:*`:

- `kind:client` клиенты/каналы
- `kind:process` процессный/координирующий контур (write-модель)
- `kind:read` read‑проекции/витрины/API чтения
- `kind:data` хранилища
- `kind:async` брокеры/очереди/топики (логически)
- `kind:rules` правила/матрицы/конфигурация поведения
- `kind:product` внешние продуктовые контуры
- `kind:ops` аудит/наблюдаемость/эксплуатационные сервисы

Роль “единственный источник истины статуса” (если применимо) помечайте:

- `role:sot-status` (должен быть ровно один владелец)

## Связи (relationships)

Связь это ориентированное ребро `from -> to` с описанием:

- `from`, `to` (по `id`)
- `description` (человеко-читаемая подпись)
- `protocol` (рекомендуется: `HTTPS`, `SQL`, `Batch`, `Async`, `Internal`…)
- `patterns` (рекомендуется: `read`, `write`, `project`, `async`, `idempotent`, `no_pii`…)

`patterns` используются валидаторами/линтером и (частично) в легендах/отчётах.

## Абстрактный пример (без домена)

Ниже пример “процесс + read + БД + внешний источник (batch)”:

````yaml
version: "1.0"
metadata:
  title: "Example System"
  description: "Domain-agnostic example"

system:
  name: "Example System"
  description: "UI reads from read API; process service owns status and starts workflows"

containers:
  - id: ui
    name: "UI"
    technology: "Browser"
    description: "User-facing interface"
    type: container
    tags: ["kind:client"]

  - id: process-service
    name: "Process Service"
    technology: "HTTP API"
    description: "Owns process status and starts processing"
    type: container
    tags: ["kind:process", "role:sot-status"]

  - id: read-api
    name: "Read API"
    technology: "HTTP API"
    description: "Read projection for lists/search/export"
    type: container
    tags: ["kind:read"]

  - id: process-db
    name: "Process DB"
    technology: "PostgreSQL"
    description: "State storage"
    type: database
    tags: ["kind:data"]

external-systems:
  - id: upstream-source
    name: "Upstream Source"
    description: "Batch source of snapshots"
    tags: ["kind:product", "legacy"]

relationships:
  - from: upstream-source
    to: read-api
    description: "Loads snapshots"
    protocol: "Batch"
    patterns: ["batch"]

  - from: ui
    to: read-api
    description: "Reads lists/statuses"
    protocol: "HTTPS"
    patterns: ["read"]

  - from: ui
    to: process-service
    description: "Starts process"
    protocol: "HTTPS"
    patterns: ["write"]

  - from: process-service
    to: process-db
    description: "Reads/writes state"
    protocol: "SQL"
    patterns: ["read", "write"]
````

## Что делать, если IR ещё нет

Можно сгенерировать черновик IR из текста (не гарантируется точность):

```bash
./archpipe draft-ir inbox/my-hld.md
```

Дальше обычно делают так:

1. Переносят черновик IR в основной HLD.
2. Прогоняют `validate` и `lint`.
3. Итеративно уточняют теги, связи, протоколы.
