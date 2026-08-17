FROM python:3.14.7-alpine AS phantomjs

ARG PHANTOMJS_VERSION=2.1.1

RUN apk add --no-cache \
        bzip2 \
        curl \
    && curl -fsSL "https://bitbucket.org/ariya/phantomjs/downloads/phantomjs-${PHANTOMJS_VERSION}-linux-x86_64.tar.bz2" \
        | tar -xj -C /tmp \
    && mv "/tmp/phantomjs-${PHANTOMJS_VERSION}-linux-x86_64/bin/phantomjs" /usr/local/bin/phantomjs \
    && chmod +x /usr/local/bin/phantomjs

FROM python:3.14.7-alpine

# Runtime behaviour
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_NO_CACHE_DIR=1 \
    OPENSSL_CONF=/dev/null \
    PYTHONPATH=/app/src

# Config defaults (override at runtime)
ENV SLEEP_INTERVAL=3600 \
    STEP_SLEEP_INTERVAL=15 \
    DATA_PATH=/data \
    DB_HOST=localhost \
    DB_PORT=3306 \
    DB_USER=root \
    DB_PASSWORD=root \
    LOKI_URL="" \
    LOKI_USERNAME="" \
    LOKI_PASSWORD="" \
    LOKI_LABELS="" \
    LOKI_APP_LABEL=pornhub-archiver \
    LOKI_TIMEOUT=5 \
    LOG_PATH=/logs \
    CONSOLE_COLORS=true \
    CONCURRENT_FRAGMENT_DOWNLOADS=4

WORKDIR /app

RUN apk add --no-cache \
        ca-certificates \
        deno \
        ffmpeg \
        gcompat \
        libstdc++ \
        openssl \
    && update-ca-certificates

COPY --from=phantomjs /usr/local/bin/phantomjs /usr/local/bin/phantomjs

RUN pip install \
        aiohttp \
        aiomysql \
        arrow \
        humanize \
        "yt-dlp[default,curl-cffi]"

COPY src/ /app/src/

VOLUME ["/data", "/logs"]

CMD ["python", "-m", "pornhub_archiver.run"]
