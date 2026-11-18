#!/usr/bin/env bash
# start.sh — Render production startup script
# Runs before gunicorn: ensures DB is migrated and default superuser exists.
set -e

echo "==> Running database migrations..."
python manage.py migrate --noinput

echo "==> Creating default superuser (skips if already exists)..."
python manage.py create_default_superuser

echo "==> Starting gunicorn..."
exec gunicorn config.wsgi:application --bind "0.0.0.0:${PORT}" --workers 2 --timeout 120
