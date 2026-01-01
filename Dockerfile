# Python 3.14.2
FROM python:3.14.2-alpine

# Unraid-friendly ENV defaults
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

# Config values
ENV SLEEP_INTERVAL=3600
ENV DB_HOST='localhost'
ENV DB_PORT=3306

# Working directory
WORKDIR /app

# System dependencies
# RUN apt-get update
RUN apk add --no-cache ffmpeg ca-certificates openssl libstdc++ bzip2 gcompat
RUN update-ca-certificates


# Install PhantomJS from official binary
RUN apk add curl && \
    curl -L "https://bitbucket.org/ariya/phantomjs/downloads/phantomjs-2.1.1-linux-x86_64.tar.bz2" | tar -xj -C /tmp && \
    mv /tmp/phantomjs-2.1.1-linux-x86_64/bin/phantomjs /usr/local/bin/phantomjs && \
    chmod +x /usr/local/bin/phantomjs && \
    rm -rf /tmp/phantomjs-2.1.1-linux-x86_64

RUN export OPENSSL_CONF=/dev/null

# Install deno
RUN apk add deno

# Python dependencies
RUN pip install --no-cache-dir aiomysql yt-dlp
RUN pip install "yt-dlp[default,curl-cffi]"

# Copy application
COPY . /app

# Unraid volume declarations
VOLUME ["/data"]

# Ensure directories exist
RUN mkdir -p /data

# Update yt-dlp
RUN yt-dlp --update

# main entry point
CMD ["python", "run.py"]
