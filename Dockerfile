FROM python:3.12-slim

# System deps for lxml, pdfplumber, BeautifulSoup
RUN apt-get update && apt-get install -y --no-install-recommends \
        libxml2 \
        libxslt1.1 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Copy project metadata first for layer caching
COPY pyproject.toml ./
COPY src/ ./src/
COPY alembic/ ./alembic/
COPY alembic.ini ./

# Install server + optional litellm (skip PySide6/client)
RUN pip install --no-cache-dir -e ".[server]" \
    && pip install --no-cache-dir -e ".[litellm]" 2>/dev/null || true

# Data directory for SQLite and certs
RUN mkdir -p /data

COPY scripts/docker-entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

EXPOSE 8000

ENTRYPOINT ["/entrypoint.sh"]
