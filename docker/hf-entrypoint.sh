#!/bin/sh
# HF Spaces entrypoint: gate the public demo behind HTTP Basic Auth before
# starting nginx+uvicorn. Fails closed -- if DEMO_BASIC_AUTH_USER/PASS
# aren't set as Space secrets, a random password is generated and never
# printed, so the default state is "inaccessible," not "open with real
# API costs on every request" (this app has no other rate limiting or auth).
set -e

if [ -n "$DEMO_BASIC_AUTH_USER" ] && [ -n "$DEMO_BASIC_AUTH_PASS" ]; then
    htpasswd -b -c /etc/nginx/.htpasswd "$DEMO_BASIC_AUTH_USER" "$DEMO_BASIC_AUTH_PASS"
else
    RANDOM_PASS=$(head -c 24 /dev/urandom | base64 | tr -dc 'a-zA-Z0-9' | head -c 24)
    htpasswd -b -c /etc/nginx/.htpasswd "demo" "$RANDOM_PASS"
    echo "WARNING: DEMO_BASIC_AUTH_USER/DEMO_BASIC_AUTH_PASS not set as Space secrets." >&2
    echo "The demo is locked behind a randomly generated password that is not logged anywhere." >&2
    echo "Set both as Space secrets and restart to choose real credentials." >&2
fi

exec /usr/bin/supervisord -c /etc/supervisor/conf.d/supervisord.conf
