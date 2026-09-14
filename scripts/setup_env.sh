#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
ENV_FILE="$ROOT_DIR/.env"

read -rsp "Telegram BOT_TOKEN: " BOT_TOKEN
printf "\n"
read -rsp "Supabase secret/service-role key: " SUPABASE_SERVICE_ROLE_KEY
printf "\n"
read -rp "Telegram owner ID: " OWNER_TELEGRAM_ID

if [[ -z "$BOT_TOKEN" || -z "$SUPABASE_SERVICE_ROLE_KEY" || -z "$OWNER_TELEGRAM_ID" ]]; then
  echo "Все значения обязательны."
  exit 1
fi

umask 077
cat > "$ENV_FILE" <<EOF
BOT_TOKEN=$BOT_TOKEN
SUPABASE_URL=https://fmpkliqfbuvucutjljfd.supabase.co
SUPABASE_SERVICE_ROLE_KEY=$SUPABASE_SERVICE_ROLE_KEY
OWNER_TELEGRAM_ID=$OWNER_TELEGRAM_ID
TIMEZONE=Asia/Tashkent
EOF

chmod 600 "$ENV_FILE"
echo ".env создан: $ENV_FILE"
