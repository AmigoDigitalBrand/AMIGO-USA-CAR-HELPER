# ─────────────────────────────────────────────
# Stage 1 — Build telegram-bot-api from source
# ─────────────────────────────────────────────
FROM ubuntu:22.04 AS tg-builder

ENV DEBIAN_FRONTEND=noninteractive

RUN apt-get update && apt-get install -y --no-install-recommends \
    ca-certificates cmake make g++ git zlib1g-dev libssl-dev gperf \
    && rm -rf /var/lib/apt/lists/*

RUN git clone --depth 1 --recurse-submodules \
    https://github.com/tdlib/telegram-bot-api.git /tg \
    && mkdir /tg/build \
    && cd /tg/build \
    && cmake -DCMAKE_BUILD_TYPE=Release -DCMAKE_INSTALL_PREFIX=/usr/local .. \
    && cmake --build . --target install -j$(nproc)

# ─────────────────────────────────────────────
# Stage 2 — Python bot + local API server
# ─────────────────────────────────────────────
FROM python:3.11-slim

RUN apt-get update && apt-get install -y --no-install-recommends supervisor \
    && rm -rf /var/lib/apt/lists/*

# Copy the compiled binary from stage 1
COPY --from=tg-builder /usr/local/bin/telegram-bot-api /usr/local/bin/telegram-bot-api

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt \
    && playwright install chromium --with-deps

COPY . .

RUN mkdir -p /tmp/tg-data /tmp/tg-temp /var/log/supervisor

CMD ["supervisord", "-n", "-c", "/app/supervisord.conf"]
