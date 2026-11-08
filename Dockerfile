FROM debian:bookworm-slim

RUN apt-get update && apt-get install -y --no-install-recommends \
        python3 \
        python3-venv \
        ca-certificates \
        osmium-tool \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt /tmp/requirements.txt
RUN python3 -m venv /opt/venv \
    && /opt/venv/bin/pip install --no-cache-dir -r /tmp/requirements.txt \
    && rm /tmp/requirements.txt
ENV PATH="/opt/venv/bin:${PATH}"

WORKDIR /app
COPY french_tolls/ /app/french_tolls/
COPY alembic.ini /app/alembic.ini
COPY alembic/ /app/alembic/
ENV PYTHONPATH=/app
ENV PYTHONUNBUFFERED=1

CMD ["python3", "-m", "french_tolls.web"]
