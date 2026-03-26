FROM python:3.12-slim-bookworm


WORKDIR /app

# Install system dependencies and ODBC driver in one layer
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
        curl gnupg2 apt-transport-https unixodbc-dev ca-certificates && \
    curl -fsSL https://packages.microsoft.com/keys/microsoft.asc | gpg --dearmor -o /usr/share/keyrings/microsoft-prod.gpg && \
    curl https://packages.microsoft.com/config/debian/12/prod.list > /etc/apt/sources.list.d/mssql-release.list && \
    apt-get update && \
    ACCEPT_EULA=Y apt-get install -y msodbcsql17 msodbcsql18 && \
    apt-get clean && rm -rf /var/lib/apt/lists/*


# Create non-root user
RUN groupadd -r appuser && useradd -r -g appuser -d /app appuser


COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy all project files (except those in .dockerignore)
COPY . .


# Change ownership to non-root user
RUN chown -R appuser:appuser /app

EXPOSE 8000
ENV MCP_HOST=0.0.0.0
ENV MCP_PORT=8000
USER appuser
CMD ["python", "server_startup.py"]