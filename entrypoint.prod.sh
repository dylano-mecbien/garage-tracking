  GNU nano 7.2                                                         entrypoint.prod.sh *                                                                
#!/bin/sh
set -e

# Créer le dossier logs s'il n'existe pas
mkdir -p /app/logs

# Appliquer les migrations (y compris notifications)
python manage.py makemigrations accounts vehicules atelier reception guerite audit notifications
python manage.py migrate

# Collecter les fichiers statiques
python manage.py collectstatic --noinput

python manage.py create_default_admin

# Lancer Gunicorn sur 0.0.0.0:8000
exec gunicorn garage.wsgi:application \
  --bind 0.0.0.0:8000 \
  --workers 4 \
  --threads 4 \
  --worker-class gthread \
  --timeout 120 \
  --access-logfile /app/logs/access.log \
  --error-logfile /app/logs/error.log
