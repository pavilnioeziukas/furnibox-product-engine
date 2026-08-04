#!/bin/sh
set -eu

state_dir="${FURNIBOX_WEB_STATE_DIR:-/app/web_state}"
mkdir -p "$state_dir/output" "$state_dir/shared_data" "$state_dir/runs" "$state_dir/uploads"

if [ -e /app/output ] && [ ! -L /app/output ]; then
    cp -a /app/output/. "$state_dir/output/" 2>/dev/null || true
    rm -rf /app/output
fi
ln -sfn "$state_dir/output" /app/output

exec gunicorn \
    --workers 1 \
    --threads 8 \
    --timeout 1800 \
    --bind "0.0.0.0:${PORT:-8080}" \
    webapp.app:app
