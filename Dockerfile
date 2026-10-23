# Google Chrome only ships for amd64, so this image is amd64-only.
FROM python:3.11-slim-bookworm

COPY --from=ghcr.io/astral-sh/uv:0.13.5 /uv /uvx /bin/

# Chrome (driven by nodriver) and Xvfb: Cloudflare blocks headless Chrome, so the
# bot runs it headful on a virtual display it starts itself.
RUN apt-get update \
    && apt-get install -y --no-install-recommends ca-certificates wget \
    && wget -qO /tmp/chrome.deb https://dl.google.com/linux/direct/google-chrome-stable_current_amd64.deb \
    && apt-get install -y --no-install-recommends /tmp/chrome.deb xvfb \
    && rm -rf /tmp/chrome.deb /var/lib/apt/lists/* \
    # Xvfb wants this root-owned; creating it here avoids a warning as non-root.
    && mkdir -p /tmp/.X11-unix && chmod 1777 /tmp/.X11-unix

RUN useradd --create-home --uid 1000 bot
WORKDIR /app
RUN mkdir -p data && chown bot:bot /app data

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    PYTHONUNBUFFERED=1 \
    PATH="/app/.venv/bin:$PATH"

USER bot

# Dependencies first, so code changes don't reinstall them.
COPY --chown=bot:bot pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project

COPY --chown=bot:bot src ./src
RUN uv sync --frozen --no-dev

# Listings DB and the Chrome profile (keeps the Cloudflare clearance between runs).
VOLUME ["/app/data"]

CMD ["miata-bot"]
