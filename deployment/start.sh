#!/usr/bin/env sh
set -eu

exec uvicorn app.production:app \
  --host 0.0.0.0 \
  --port "${PORT:-8010}" \
  --proxy-headers \
  --forwarded-allow-ips "${FORWARDED_ALLOW_IPS:-127.0.0.1}"
