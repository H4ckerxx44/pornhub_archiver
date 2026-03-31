# Python 3.14.2
FROM python:3.14.2-alpine

# Runtime behaviour
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

# Config defaults (override at runtime)
ENV SLEEP_INTERVAL=3600 \
    STEP_SLEEP_INTERVAL=15 \
    DB_HOST=localhost \
    DB_PORT=3306 \
    DB_USER=root \
    DB_PASSWORD=root

WORKDIR /app

# System dependencies — single layer
RUN apk add --no-cache \
        ffmpeg \
        ca-certificates \
        openssl \
        libstdc++ \
        bzip2 \
        gcompat \
        curl \
        deno \
    && update-ca-certificates \
    && sed -i 's/openssl_conf = openssl_init/#openssl_conf = openssl_init/g' /etc/ssl/openssl.cnf

# PhantomJS — single layer
RUN curl -L "https://bitbucket.org/ariya/phantomjs/downloads/phantomjs-2.1.1-linux-x86_64.tar.bz2" \
        | tar -xj -C /tmp \
    && mv /tmp/phantomjs-2.1.1-linux-x86_64/bin/phantomjs /usr/local/bin/phantomjs \
    && chmod +x /usr/local/bin/phantomjs \
    && rm -rf /tmp/phantomjs-2.1.1-linux-x86_64

# Python dependencies — single layer, deduplicated
RUN pip install --no-cache-dir \
        aiomysql \
        "yt-dlp[default,curl-cffi]"

# Application code — last so code changes don't invalidate dependency layers
COPY . /app

VOLUME ["/data"]

CMD ["python", "run.py"]