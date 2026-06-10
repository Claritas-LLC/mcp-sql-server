FROM python:3.14-slim AS builder

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    curl \
    unixodbc-dev \
    && rm -rf /var/lib/apt/lists/*

COPY pyproject.toml /app/pyproject.toml
COPY src /app/src

# Install project to prefix FIRST so pip doesn't skip already-installed deps.
# Then upgrade build tools globally (not needed in prefix).
RUN pip install --no-cache-dir --prefix=/install . && \
    pip install --no-cache-dir --upgrade pip setuptools wheel

FROM python:3.14-slim AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    FASTMCP_HOST=0.0.0.0 \
    FASTMCP_PORT=8080

# Install Microsoft ODBC 17 driver via official apt repo.
# Build with --build-arg MSODBC_VERSION=... to pin a specific driver version.
ARG MSODBC_VERSION=17.10.6.1-1
RUN apt-get update && apt-get install -y --no-install-recommends \
    ca-certificates \
    curl \
    gnupg \
    unixodbc \
    && curl -fsSL https://packages.microsoft.com/keys/microsoft.asc \
    | gpg --dearmor -o /usr/share/keyrings/microsoft.gpg \
    && echo "deb [arch=amd64 signed-by=/usr/share/keyrings/microsoft.gpg] https://packages.microsoft.com/debian/12/prod bookworm main" \
    > /etc/apt/sources.list.d/mssql-release.list \
    && apt-get update \
    && ACCEPT_EULA=Y apt-get install -y --no-install-recommends \
    "msodbcsql17=${MSODBC_VERSION}" \
    && rm -rf /var/lib/apt/lists/*

RUN useradd -u 10001 -s /usr/sbin/nologin -m -d /home/mcpuser mcpuser

WORKDIR /app
COPY --from=builder /install /usr/local
COPY config /app/config
COPY policy /app/policy
COPY src /app/src

RUN mkdir -p /var/log/mcp && chown -R mcpuser:mcpuser /var/log/mcp /app

USER mcpuser

EXPOSE 8080

ENTRYPOINT ["python", "-m", "src.server"]
