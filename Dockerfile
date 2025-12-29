
# FROM ubuntu:latest as phantomjs_builder
#
# WORKDIR /opt/backend
# RUN su -
# RUN  apt-get update
# RUN apt-get install sudo -y
# RUN sudo apt install curl -y
# RUN curl -sL https://deb.nodesource.com/setup_17.x -o nodesource_setup.sh
# RUN sudo bash nodesource_setup.sh
# RUN sudo apt install nodejs -y
# RUN sudo apt-get install -y fontconfig
# RUN sudo apt-get install -y libfontconfig
#
# COPY . .
# # Reference [https://github.com/Medium/phantomjs#linux-note][1]
# RUN sudo npm set strict-ssl false
# RUN sudo npm install
# RUN sudo npm install -g phantomjs-prebuilt
# RUN sudo npm install -g html-pdf
#
# RUN sudo npm rebuild
# RUN sudo npm run build
#
# EXPOSE 3005
# CMD npm run start:$env_Profile

# COPY --from=phantomjs_builder ?? /usr/local/bin/phantomjs

# Python 3.14.2
# FROM python:3.14.2-alpine
FROM python:3.14-alpine

# ----------------------------
# Unraid-friendly ENV defaults
# ----------------------------
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

# ----------------------------
# config values
# ----------------------------
ENV SLEEP_INTERVAL=3600
ENV DB_HOST='localhost'
ENV DB_PORT=3306

# ----------------------------
# Working directory
# ----------------------------
WORKDIR /app

# ----------------------------
# System dependencies
# ----------------------------
# RUN apt-get update
RUN apk add --no-cache ffmpeg ca-certificates openssl libstdc++

RUN update-ca-certificates

# ----------------------------
# Python dependencies
# ----------------------------
RUN pip install --no-cache-dir yt-dlp rich aiomysql
RUN pip install "yt-dlp[default,curl-cffi]"



# ----------------------------
# Install yt-dlp dependencies
# ----------------------------
COPY --from=denoland/deno:bin /deno /usr/local/bin/deno

# ----------------------------
# instal phantom js
# ----------------------------
# below works
RUN apk add --no-cache curl && \
    cd /tmp && curl -Ls https://github.com/topseom/phantomized/releases/download/2.1.1a/dockerized-phantomjs.tar.gz | tar xz && \
    mkdir -p usr/share && \
    mkdir -p etc/fonts && \
    cp -R lib lib64 / && \
    cp -R usr/lib/x86_64-linux-gnu /usr/lib && \
    cp -R usr/share /usr/share && \
    cp -R etc/fonts /etc && \
    curl -k -Ls https://bitbucket.org/ariya/phantomjs/downloads/phantomjs-2.1.1-linux-x86_64.tar.bz2 | tar -jxf - &&\
    cp phantomjs-2.1.1-linux-x86_64/bin/phantomjs /usr/local/bin/phantomjs && \
    rm -fR phantomjs-2.1.1-linux-x86_64 && \
    apk del curl

# ----------------------------
# Update yt-dlp
# ----------------------------
RUN yt-dlp --update

# ----------------------------
# Copy application
# ----------------------------
COPY . /app

# ----------------------------
# Unraid volume declarations
# ----------------------------
VOLUME ["/data"]

# Ensure directories exist
RUN mkdir -p /data

# ----------------------------
# Default command
# ----------------------------
CMD ["python", "run.py"]
