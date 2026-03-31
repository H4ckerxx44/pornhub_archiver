# Python 3.14.2
FROM python:3.14.2-alpine

# Unraid-friendly ENV defaults
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

# Config values
ENV SLEEP_INTERVAL=3600
ENV STEP_SLEEP_INTERVAL=15
ENV DB_HOST='localhost'
ENV DB_PORT=3306
ENV DB_USER="root"
ENV DB_PASSWORD="root"


# Working directory
WORKDIR /app

# System dependencies
# RUN apt-get update
# RUN apk add --no-cache ffmpeg
RUN apk add --no-cache ffmpeg ca-certificates openssl libstdc++ bzip2 gcompat
RUN update-ca-certificates


# Install PhantomJS from official binary
RUN apk add curl && \
    curl -L "https://bitbucket.org/ariya/phantomjs/downloads/phantomjs-2.1.1-linux-x86_64.tar.bz2" | tar -xj -C /tmp && \
    mv /tmp/phantomjs-2.1.1-linux-x86_64/bin/phantomjs /usr/local/bin/phantomjs && \
    chmod +x /usr/local/bin/phantomjs && \
    rm -rf /tmp/phantomjs-2.1.1-linux-x86_64
RUN sed -i 's/openssl_conf = openssl_init/#openssl_conf = openssl_init/g' /etc/ssl/openssl.cnf

# RUN export OPENSSL_CONF=/etc/ssl/
# RUN echo phantomjs --version

# Install deno
RUN apk add deno

# Python dependencies
RUN pip install --no-cache-dir aiomysql yt-dlp
RUN pip install --no-cache-dir "yt-dlp[default,curl-cffi]"

# configure phantomjs
RUN phantomjs --web-security=false
RUN phantomjs --ignore-ssl-errors=true

# Copy application
COPY . /app

# Unraid volume declarations
VOLUME ["/data"]

# Ensure directories exist
RUN mkdir -p /data

# Update yt-dlp
# RUN yt-dlp --update

# main entry point
CMD ["python", "run.py"]
