#!/usr/bin/env bash
set -euo pipefail

APP_DIR="/opt/finance-bot"
SERVICE_NAME="finance-bot"
BOT_USER="financebot"
REPO_URL="https://github.com/supportkadi-sudo/finance-.git"
BRANCH="${1:-main}"

if [[ "${EUID}" -ne 0 ]]; then
  echo "Запусти через sudo: sudo bash scripts/install_vps.sh"
  exit 1
fi

if ! id "$BOT_USER" >/dev/null 2>&1; then
  useradd --system --home "$APP_DIR" --shell /usr/sbin/nologin "$BOT_USER"
fi

if [[ -d "$APP_DIR/.git" ]]; then
  git -C "$APP_DIR" fetch origin
  git -C "$APP_DIR" checkout "$BRANCH"
  git -C "$APP_DIR" reset --hard "origin/$BRANCH"
else
  rm -rf "$APP_DIR"
  git clone --branch "$BRANCH" --single-branch "$REPO_URL" "$APP_DIR"
fi

python3 -m venv "$APP_DIR/.venv"
"$APP_DIR/.venv/bin/pip" install --upgrade pip
"$APP_DIR/.venv/bin/pip" install -r "$APP_DIR/requirements.txt"

chown -R "$BOT_USER:$BOT_USER" "$APP_DIR"
chmod +x "$APP_DIR/scripts/setup_env.sh"

if [[ ! -f "$APP_DIR/.env" ]]; then
  echo
  echo "Сейчас введи BOT_TOKEN и Supabase secret key. Ввод секретов не отображается."
  echo
  runuser -u "$BOT_USER" -- "$APP_DIR/scripts/setup_env.sh"
fi

cp "$APP_DIR/deploy/finance-bot.service" "/etc/systemd/system/$SERVICE_NAME.service"
systemctl daemon-reload
systemctl enable "$SERVICE_NAME"
systemctl restart "$SERVICE_NAME"

sleep 2
systemctl --no-pager --full status "$SERVICE_NAME" || true
