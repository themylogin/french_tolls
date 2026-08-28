# The application that consumes what the pipeline publishes: the aiohttp web
# service, the Telegram bot, and the test suite. One image serves all three —
# they share the routing client, the booth lookups, and the accounting, and a
# second image would only be a second place for those to drift.
#
# Debian packages wherever Debian has one, as builder/Dockerfile does.
FROM debian:bookworm-slim

RUN apt-get update && apt-get install -y --no-install-recommends \
        python3 \
        python3-aiohttp \
        python3-yaml \
        python3-pytest \
        python3-venv \
        ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# python-telegram-bot is not in Debian, so this is the one layer of this project
# that needs a package index. Bookworm marks the system environment externally
# managed, so it goes into a venv rather than over the distribution's packages.
#
# --system-site-packages is what lets the venv's interpreter see the Debian
# aiohttp, yaml and pytest above, so one interpreter runs all three services.
RUN python3 -m venv --system-site-packages /opt/venv \
    && /opt/venv/bin/pip install --no-cache-dir "python-telegram-bot==21.*"
ENV PATH="/opt/venv/bin:${PATH}"

WORKDIR /app
COPY . /app/french_tolls/
ENV PYTHONPATH=/app

# Unbuffered so log lines appear as a request is served rather than at exit.
ENV PYTHONUNBUFFERED=1

CMD ["python3", "-m", "french_tolls.web"]
