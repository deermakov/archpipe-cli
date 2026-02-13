# LLM Guide (RU): как готовить HLD для `archpipe-cli`

Цель: использовать LLM так, чтобы на выходе получался **корректный, доменно-агностичный HLD** с IR-блоком `archpipe-model`, который можно положить в `inbox/` и прогнать через генератор.

Ключевой принцип: генератор строит схемы **только** из IR (`archpipe-model`), а не из описательного текста.

---

## 1) Какой результат считаем “готовым”

В одном Markdown-файле должны быть:

1. Короткое HLD-описание (границы, решения, потоки, эксплуатационные гарантии, DR).
2. В конце файла один блок:

````
```archpipe-model
...
```
````

IR должен быть:
- валидным YAML,
- без приватных данных,
- со стабильными `id`,
- со связями, которые ссылаются на существующие `id`.

---

## 2) Минимальная структура HLD (рекомендуемый шаблон)

1. **Назначение**: 2–3 предложения, что делает система.
2. **Границы**: что входит/не входит (in/out).
3. **Компоненты**: краткий список или таблица.
4. **Связи**: список/таблица `from -> to` (протокол, sync/async, критичность).
5. **Потоки (E2E)**:
   - основной поток,
   - отказ `timeout`,
   - отказ `unavailable`,
   - (опционально) “поздний результат” для async.
6. **Эксплуатация и наблюдаемость**:
   - корреляция “запрос → процесс → сообщения/интеграции → результат”,
   - базовые метрики/алерты на ключевые компоненты,
   - политика зависаний/таймаутов/повторов (на уровне принципа).
7. **DR (Design Requests)**: вопросы, без которых нельзя финализировать контракты/статусы/интеграции.
8. **Критерии готовности**: что считается “готово к UAT/эксплуатации” (короткий список).

---

## 3) Правила для LLM (чтобы не было “доменных выдумок”)

LLM обязана:

- **Не выдумывать факты.**
  - Если данных нет: оформить как `A-*` (Assumption) или `DR-*` и **не добавлять** спорное в IR.
- **Не добавлять приватное.**
  - Никаких персональных данных, внутренних идентификаторов, ключей, секретов, “реальных” названий, если их нельзя публиковать.
- **Делать IR минимальным, но точным.**
  - Лучше меньше компонентов и связей, но подтверждённых, чем “богатая” схема на основе предположений.

---

## 4) Готовый промпт для LLM (копируй-вставляй)

```text
Ты генерируешь HLD для archpipe-cli.

ВХОД: пользователь описывает систему (может быть неполно).
ВЫХОД: один Markdown-файл со структурой:

1) Назначение (2–3 предложения)
2) Границы (in/out)
3) Компоненты системы (таблица)
   | id | name | type | technology | responsibility | tags |
   - id: kebab-case
   - type: container|database|queue|cache
   - tags: обязательно минимум один kind:* (kind:client|kind:process|kind:read|kind:data|kind:async|kind:rules|kind:product|kind:ops)

4) Связи между компонентами (таблица)
   | from | to | protocol | sync | criticality | description |
   - protocol: HTTPS|HTTP|gRPC|SQL|Kafka|RabbitMQ|Batch|Internal
   - sync: sync/async
   - criticality: critical/optional

5) Потоки (E2E)
   - Основной поток: шаги через компоненты
   - Отказ timeout: что происходит (где таймаут, что видит пользователь, какой статус)
   - Отказ unavailable: что происходит (что деградирует, что ретраим, что фиксируем)

6) Эксплуатация и наблюдаемость (кратко)
   - корреляция запрос/процесс/сообщения
   - метрики: latency/errors/throughput для ключевых компонентов

7) DR (вопросы без ответов)

8) IR-блок (ОБЯЗАТЕЛЬНО) в конце:
```archpipe-model
version: "1.0"
metadata:
  title: "<краткое название>"
system:
  name: "<название системы>"
  description: "<1–2 строки>"
containers:
  - id: <kebab-case>
    name: "<display name>"
    technology: "<если известно>"
    description: "<1 строка>"
    type: container|database|queue|cache
    tags: ["kind:..."]
external-systems:
  - id: <kebab-case>
    name: "<display name>"
    description: "<1 строка>"
    tags: ["kind:product"]
relationships:
  - from: <id>
    to: <id>
    description: "<для чего>"
    protocol: "<HTTPS|SQL|Kafka|...>"
    patterns: ["read"|"write"|"async"|"batch"|"idempotent"|"no_pii"]
```

ПРАВИЛА:
- Не выдумывай факты. Если данных нет: создай Assumption (A-*) или DR (DR-*), и НЕ добавляй спорное в IR.
- IR должен быть валидным YAML.
- Все id уникальны.
- Все relationships.from/to ссылаются на существующие id.
```

---

## 5) Проверка результата (перед тем как класть в `inbox/`)

1) Валидация:

```bash
./archpipe validate inbox/<file>.md
```

2) Архитектурный линт (рекомендуется):

```bash
./archpipe lint inbox/<file>.md --strict
```

3) Генерация артефактов:

```bash
./archpipe generate inbox/<file>.md --format all --output-dir auto --notation standard --force
```

Если нужны только исходники без картинок:

```bash
./archpipe generate inbox/<file>.md --format all --output-dir auto --notation standard --no-render-images --force
```

---

## 6) Частые ошибки и как исправлять

- **IR-блок не найден / YAML невалиден**:
  - убедитесь, что fenced-блок называется именно `archpipe-model`.
- **Связи ссылаются на неизвестные id**:
  - проверьте, что `relationships.from/to` существуют в `containers` или `external-systems`.
- **Плохие id**:
  - используйте kebab-case и уникальные значения.
- **Слишком много предположений**:
  - удалите спорные элементы из IR и перенесите их в DR.

---

## 7) Ссылки

- IR: `/Users/alexander/Documents/hld/archpipe-cli/IR_GUIDE.md`
- Quickstart для запуска: `/Users/alexander/Documents/hld/archpipe-cli/README.md`
