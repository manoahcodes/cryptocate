web: gunicorn backend.wsgi:application --bind 0.0.0.0:$PORT --workers 2 --threads 4 --timeout 120
worker: celery -A backend worker --loglevel=info --concurrency=4
beat: celery -A backend beat --loglevel=inf
