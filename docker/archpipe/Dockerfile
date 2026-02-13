# syntax=docker/dockerfile:1.7
FROM python:3.12-slim

ENV DEBIAN_FRONTEND=noninteractive
ENV PYTHONUNBUFFERED=1
ENV PIP_DISABLE_PIP_VERSION_CHECK=1

RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        ca-certificates \
        curl \
        unzip \
        bash \
        graphviz \
        openjdk-21-jre-headless \
    && rm -rf /var/lib/apt/lists/*

# PlantUML local binary (avoids Docker fallback during render).
RUN curl -fsSL https://github.com/plantuml/plantuml/releases/latest/download/plantuml.jar -o /opt/plantuml.jar \
    && printf '#!/usr/bin/env bash\nexec java -jar /opt/plantuml.jar "$@"\n' > /usr/local/bin/plantuml \
    && chmod +x /usr/local/bin/plantuml

# Structurizr CLI local binary (avoids Docker fallback during C4 export).
RUN curl -fsSL https://github.com/structurizr/cli/releases/latest/download/structurizr-cli.zip -o /tmp/structurizr-cli.zip \
    && unzip -q /tmp/structurizr-cli.zip -d /opt/structurizr \
    && rm -f /tmp/structurizr-cli.zip \
    && printf '#!/usr/bin/env bash\nexec /opt/structurizr/structurizr.sh "$@"\n' > /usr/local/bin/structurizr \
    && chmod +x /usr/local/bin/structurizr /opt/structurizr/structurizr.sh

WORKDIR /app

# Keep this layer narrow: docs that change often should not invalidate pip install.
COPY pyproject.toml README.md ./
COPY src ./src

RUN --mount=type=cache,target=/root/.cache/pip \
    pip install ".[dev]"

WORKDIR /work

ENTRYPOINT ["archpipe"]
CMD ["--help"]
