FROM python:3.14-alpine AS builder

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

RUN apk add --no-cache \
    build-base \
    curl \
    unixodbc-dev

COPY pyproject.toml /app/pyproject.toml
COPY src /app/src

RUN pip install --no-cache-dir --upgrade pip setuptools wheel && \
    pip install --no-cache-dir --prefix=/install .

FROM python:3.14-alpine AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    FASTMCP_HOST=0.0.0.0 \
    FASTMCP_PORT=8080

RUN apk add --no-cache \
    ca-certificates \
    curl \
    gnupg \
    unixodbc

# Install Microsoft ODBC 18 driver (extract from Debian package for Alpine)
RUN apk add --no-cache dpkg && \
    curl -fsSL https://packages.microsoft.com/keys/microsoft.asc \
    | gpg --dearmor -o /etc/apk/keys/microsoft.gpg && \
    curl -fsSL -o /tmp/msodbcsql.deb \
    "https://packages.microsoft.com/debian/12/prod/pool/main/m/msodbcsql18/msodbcsql18_18.4.1.1-1_amd64.deb" && \
    dpkg-deb -x /tmp/msodbcsql.deb /tmp/msodbcsql && \
    mkdir -p /opt/microsoft && \
    cp -r /tmp/msodbcsql/opt/microsoft/msodbcsql18 /opt/microsoft/msodbcsql18 && \
    cp /tmp/msodbcsql/opt/microsoft/msodbcsql18/etc/odbcinst.ini /etc/odbcinst.ini && \
    ln -s /opt/microsoft/msodbcsql18/lib64/libmsodbcsql-18.4.so.1.1 \
          /usr/lib/libmsodbcsql-18.so && \
    rm -rf /tmp/msodbcsql* && \
    apk del dpkg

RUN adduser -D -u 10001 -s /usr/sbin/nologin mcpuser

WORKDIR /app
COPY --from=builder /install /usr/local
# Ensure packaging is present in runtime (transitive dep of FastMCP)
RUN pip install --no-cache-dir packaging
COPY config /app/config
COPY policy /app/policy
COPY src /app/src

RUN mkdir -p /var/log/mcp && chown -R mcpuser:mcpuser /var/log/mcp /app

USER mcpuser

EXPOSE 8080

ENTRYPOINT ["python", "-m", "src.server"]
