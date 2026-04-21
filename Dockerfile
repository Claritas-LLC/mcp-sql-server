FROM python:3.12-slim-bookworm AS base

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

# Allowed values: 17, 18, both
ARG ODBC_DRIVER_MAJOR=both

WORKDIR /app

# Install only runtime OS dependencies needed by pyodbc and SQL Server ODBC drivers.
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
        ca-certificates \
        curl \
        gpg \
        unixodbc && \
    curl -fsSL https://packages.microsoft.com/keys/microsoft.asc | gpg --dearmor -o /usr/share/keyrings/microsoft-prod.gpg && \
    curl -fsSL https://packages.microsoft.com/config/debian/12/prod.list > /etc/apt/sources.list.d/mssql-release.list && \
    apt-get update && \
    if [ "$ODBC_DRIVER_MAJOR" = "17" ]; then \
        ACCEPT_EULA=Y apt-get install -y --no-install-recommends msodbcsql17; \
    elif [ "$ODBC_DRIVER_MAJOR" = "18" ]; then \
        ACCEPT_EULA=Y apt-get install -y --no-install-recommends msodbcsql18; \
    elif [ "$ODBC_DRIVER_MAJOR" = "both" ]; then \
        ACCEPT_EULA=Y apt-get install -y --no-install-recommends msodbcsql17 msodbcsql18; \
    else \
        echo "Invalid ODBC_DRIVER_MAJOR='$ODBC_DRIVER_MAJOR' (expected: 17, 18, both)"; \
        exit 1; \
    fi && \
    rm -rf /var/lib/apt/lists/*

RUN groupadd -r appuser && useradd -r -g appuser -d /app appuser


FROM base AS builder

COPY requirements.txt ./

# Build/download dependency wheels in a throwaway stage.
RUN python -m pip install --upgrade pip && \
    pip wheel --no-cache-dir --wheel-dir /tmp/wheels -r requirements.txt


FROM denoland/deno:bin-2.1.9 AS deno-bin

FROM base AS runtime

COPY --from=deno-bin /deno /usr/local/bin/deno
COPY requirements.txt ./
COPY --from=builder /tmp/wheels /tmp/wheels

# Install from local wheels only to keep final image deterministic and small.
RUN pip install --no-cache-dir --no-compile --no-index --find-links=/tmp/wheels -r requirements.txt && \
    rm -rf /tmp/wheels

# /app is created by WORKDIR as root; grant write access to runtime user for dynamic folders (e.g., /app/logs).
RUN chown appuser:appuser /app

# Copy app files with final ownership to avoid an expensive recursive chown layer.
COPY --chown=appuser:appuser . .

EXPOSE 8000
ENV MCP_HOST=0.0.0.0
ENV MCP_PORT=8000
USER appuser
CMD ["python", "server_startup.py"]