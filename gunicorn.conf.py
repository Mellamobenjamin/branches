import os

# Behind a reverse proxy, set GUNICORN_BIND (e.g. 127.0.0.1:8005) to the
# address your proxy forwards to.
bind = os.environ.get("GUNICORN_BIND", f"0.0.0.0:{os.environ.get('PORT', '8005')}")
workers = 2
threads = 2
timeout = 60
pidfile = "gunicorn.pid"
accesslog = "access.log"
errorlog = "error.log"
