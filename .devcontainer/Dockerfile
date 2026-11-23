FROM python:3.11-slim-bookworm
RUN apt-get update && apt-get install -y --no-install-recommends \
    ffmpeg fontconfig fonts-noto-core git curl ca-certificates \
    && rm -rf /var/lib/apt/lists/* \
    && groupadd --gid 1000 vscode \
    && useradd --uid 1000 --gid 1000 --create-home --shell /bin/bash vscode
USER vscode
