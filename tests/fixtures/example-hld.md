# Simple Web App

Minimal architecture used in tests.

## Architecture Model (IR)

```archpipe-model
version: "1.0"
metadata:
  title: "Simple Web App"
  description: "Test fixture"
  author: "Tests"
  date: "2026-02-06"
  tags: ["test"]

system:
  name: "Web App"
  description: "Basic CRUD application"

containers:
  - id: webapp
    name: "Web Application"
    technology: "Node.js + Express"
    description: "REST API server"
    type: container
    tags: ["kind:process", "role:sot-status"]
    deployment:
      platform: "Docker"
      scaling: manual
      replicas: 2

  - id: db
    name: "Database"
    technology: "PostgreSQL"
    description: "Application data"
    type: database
    tags: ["kind:data"]

relationships:
  - from: webapp
    to: db
    description: "Reads and writes data"
    protocol: "SQL"
    patterns: ["read", "write"]

quality-attributes:
  - attribute: availability
    target: "99.9%"
    measurement: "uptime"
```
