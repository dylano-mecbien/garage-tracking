#!/bin/sh
set -e

# Créer le dossier logs s'il n'existe pas
mkdir -p /app/logs

# Appliquer les migrations (y compris notifications)
python manage.py makemigrations accounts vehicules atelier reception guerite audit notifications
python manage.py migrate

# Collecter les fichiers statiques
python manage.py collectstatic --noinput

# Lancer Gunicorn sur 0.0.0.0:8000
exec gunicorn garage.wsgi:application \
  --bind 0.0.0.0:8000 \
  --workers 2 \
  --threads 2 \
  --timeout 120 \
  --access-logfile /app/logs/access.log \
  --error-logfile /app/logs/error.log
