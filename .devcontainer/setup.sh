#!/usr/bin/env bash
set -euo pipefail

USER_NAME="$(id -un)"
CLAUDE_DIR="${CLAUDE_CONFIG_DIR:-$HOME/.claude}"
GH_DIR="$HOME/.config/gh"

# Fix ownership only when the dir exists and isn't already ours. This makes the
# script idempotent: it skips the sudo call on rebuilds where the persisted
# volume is already correct.
for dir in "$GH_DIR" "$CLAUDE_DIR"; do
  if [ -d "$dir" ] && [ "$(stat -c '%U' "$dir")" != "$USER_NAME" ]; then
    sudo chown -R "$USER_NAME:$USER_NAME" "$dir"
  fi
done

# Seed an empty Claude config if missing so the extension's first locked save
# can lstat the file (avoids a noisy ENOENT error on a brand-new volume).
if [ ! -s "$CLAUDE_DIR/.claude.json" ]; then
  mkdir -p "$CLAUDE_DIR"
  echo '{}' > "$CLAUDE_DIR/.claude.json"
fi

# Scraper system deps: Chrome (driven by nodriver) and Xvfb (Cloudflare blocks
# headless Chrome, so we run headful on a virtual display).
if ! command -v google-chrome >/dev/null || ! command -v Xvfb >/dev/null; then
  tmp_deb="$(mktemp --suffix=.deb)"
  wget -qO "$tmp_deb" https://dl.google.com/linux/direct/google-chrome-stable_current_amd64.deb
  sudo apt-get update -qq
  sudo DEBIAN_FRONTEND=noninteractive apt-get install -y -qq "$tmp_deb" xvfb
  rm -f "$tmp_deb"
fi

uv sync
