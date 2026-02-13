# Example HLD (domain-agnostic)

This is a minimal, **non-domain** example used to validate the generator.

## Architecture Model (IR)

```archpipe-model
version: "1.0"
metadata:
  title: "Example System"
  description: "Domain-agnostic IR example"
  author: "Architecture Team"
  date: "2026-02-09"
  tags: ["microservices"]

system:
  name: "Example System"
  description: "A system with read-model + process owner + async integration"

containers:
  - id: ui
    name: "UI"
    technology: "Browser"
    description: "User interface"
    type: container
    tags: ["kind:client"]

  - id: process-service
    name: "Process Service"
    technology: "HTTP API"
    description: "Owns process state"
    type: container
    tags: ["kind:process", "role:sot-status"]

  - id: read-api
    name: "Read API"
    technology: "HTTP API"
    description: "Read projection (list/search/export)"
    type: container
    tags: ["kind:read"]

  - id: rules
    name: "Rules"
    technology: "Config"
    description: "Rule configuration"
    type: container
    tags: ["kind:rules"]

  - id: main-db
    name: "Main DB"
    technology: "PostgreSQL"
    description: "Primary storage"
    type: database
    tags: ["kind:data"]

external-systems:
  - id: external-system
    name: "External System"
    description: "External integration"
    tags: ["kind:product"]

relationships:
  - from: ui
    to: read-api
    description: "Reads data"
    protocol: "HTTPS"
    patterns: ["read"]

  - from: ui
    to: process-service
    description: "Starts actions"
    protocol: "HTTPS"
    patterns: ["write"]

  - from: process-service
    to: rules
    description: "Evaluates rules"
    protocol: "Internal"
    patterns: ["read"]

  - from: process-service
    to: main-db
    description: "Stores process state"
    protocol: "SQL"
    patterns: ["read", "write"]

  - from: process-service
    to: read-api
    description: "Projects status"
    protocol: "Internal"
    patterns: ["project"]

  - from: process-service
    to: external-system
    description: "Sends async command"
    protocol: "Async"
    patterns: ["async", "idempotent", "no_pii"]

  - from: external-system
    to: process-service
    description: "Returns async result"
    protocol: "Async"
    patterns: ["async", "idempotent", "no_pii"]

```
