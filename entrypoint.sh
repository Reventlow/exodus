#!/bin/bash
set -e

python manage.py migrate --noinput

exec gunicorn exodus.wsgi:application --bind 0.0.0.0:8000 --workers 3
