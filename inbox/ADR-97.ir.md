```archpipe-model
version: "1.0"
metadata:
  title: "ADR-97"
system:
  name: "ADR-97"
  description: "ADR-097 Урегулирование убытков - Интеграция с 1С:ФС и МС ПП"
containers:
  - id: ms-claims-orchestrator
    name: "ms-claims-orchestrator Оркестратор убытков"
    technology: "Java/Spring Boot"
    description: "Координация бизнес-процессов урегулирования"
    type: container
    tags: ["kind:process", "kind:rules", "role:sot-status"]
  - id: esb-adapter
    name: "Адаптер ESB для УУ"
    technology: "Java/Spring Boot"
    description: "Интеграция с внешней интеграционной шиной"
    type: container
    tags: ["kind:client", "kind:process"]
  - id: kafka-topic-insurance-act
    name: "Топик Страховой акт"
    technology: "Apache Kafka"
    description: "Передача Страховых актов и Выплат по СА"
    type: queue
    tags: ["kind:data", "kind:async"]
  - id: kafka-topic-application
    name: "Топик Заявление"
    technology: "Apache Kafka"
    description: "Передача Заявлений"
    type: queue
    tags: ["kind:data", "kind:async"]
  - id: kafka-topic-esb-notification
    name: "Топик ESB notification"
    technology: "Apache Kafka"
    description: "Уведомления от ESB"
    type: queue
    tags: ["kind:data", "kind:async"]
  - id: insurance-act
    name: "Страховой акт"
    technology: "JSON schema"
    description: "Страховой акт"
    type: data_object
    tags: ["kind:data"]
  - id: insurance-act-payment
    name: "Выплата по страховому акту"
    technology: "JSON schema"
    description: "Выплата по страховому акту"
    type: data_object
    tags: ["kind:data"]
  - id: application
    name: "Заявление"
    technology: "JSON schema"
    description: "Заявление"
    type: data_object
    tags: ["kind:data"]
external-systems:
  - id: esb
    name: "ESB"
    description: "Интеграционная шина"
    tags: ["kind:product"]
relationships:
  - from: ms-claims-orchestrator
    to: kafka-topic-insurance-act
    description: "Отправка Страхового акта и Выплаты по СА"
    protocol: "Kafka"
    patterns: ["write", "async"]
  - from: insurance-act
    to: kafka-topic-insurance-act
    description: "Отправка Страхового акта и Выплаты по СА"
    protocol: "Kafka"
    patterns: ["write", "async"]
  - from: insurance-act-payment
    to: kafka-topic-insurance-act
    description: "Отправка Страхового акта и Выплаты по СА"
    protocol: "Kafka"
    patterns: ["write", "async"]
  - from: kafka-topic-insurance-act
    to: esb-adapter
    description: "Отправка Страхового акта и Выплаты по СА"
    protocol: "Kafka"
    patterns: ["read", "async"]
  - from: ms-claims-orchestrator
    to: kafka-topic-application
    description: "Отправка Заявления"
    protocol: "Kafka"
    patterns: ["write", "async"]
  - from: application
    to: kafka-topic-application
    description: "Отправка Заявления"
    protocol: "Kafka"
    patterns: ["write", "async"]
  - from: kafka-topic-application
    to: esb-adapter
    description: "Отправка Заявления"
    protocol: "Kafka"
    patterns: ["read", "async"]
  - from: esb-adapter
    to: kafka-topic-esb-notification
    description: "Уведомление от ESB о событиях"
    protocol: "Kafka"
    patterns: ["write", "async"]
  - from: kafka-topic-esb-notification
    to: ms-claims-orchestrator
    description: "Уведомление от ESB о событиях"
    protocol: "Kafka"
    patterns: ["write", "async"]
  - from: esb-adapter
    to: esb
    description: "Синхронный вызов ESB для обработки заявления"
    protocol: "REST API"
    patterns: ["read", "write"]
```