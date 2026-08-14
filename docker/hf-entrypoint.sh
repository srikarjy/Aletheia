#!/bin/sh
# HF Spaces entrypoint: bootstrap the bundled Postgres (no managed DB or
# persistent volume on HF Spaces -- see Dockerfile.hf), then gate the
# public demo behind HTTP Basic Auth, before handing off to supervisord
# (nginx + uvicorn + postgres, all managed there from this point on).
set -e

PGDATA="${PGDATA:-/var/lib/postgresql/data}"
PG_BIN="${PG_BIN:-/usr/lib/postgresql/15/bin}"

mkdir -p "$PGDATA"
chown -R postgres:postgres "$PGDATA"

if [ ! -s "$PGDATA/PG_VERSION" ]; then
    echo "Initializing Postgres data directory at $PGDATA" >&2
    su postgres -c "$PG_BIN/initdb -D $PGDATA" >/tmp/initdb.log 2>&1
fi

# Start once, synchronously, to create the role/db/schema, then stop --
# supervisord's [program:postgres] takes over as the long-running process.
su postgres -c "$PG_BIN/pg_ctl -D $PGDATA -l /tmp/postgres-bootstrap.log -w start"

su postgres -c "$PG_BIN/psql -tAc \"SELECT 1 FROM pg_roles WHERE rolname='aletheia'\"" | grep -q 1 \
    || su postgres -c "$PG_BIN/psql -c \"CREATE ROLE aletheia LOGIN PASSWORD 'aletheia';\""
su postgres -c "$PG_BIN/psql -tAc \"SELECT 1 FROM pg_database WHERE datname='aletheia'\"" | grep -q 1 \
    || su postgres -c "$PG_BIN/createdb -O aletheia aletheia"

# init.sql runs as the postgres superuser -- pgvector's CREATE EXTENSION
# isn't marked trusted in this build, so aletheia (a plain LOGIN role) can't
# run it itself ("must be superuser to create this extension"). That means
# the tables it creates end up owned by postgres, not aletheia, even though
# aletheia owns the *database* (via createdb -O above) -- so grant aletheia
# explicit privileges on what was just created rather than trying to make
# it powerful enough to have created them itself. A first deploy of this
# bootstrap skipped this and every app query failed with "permission denied
# for table embeddings".
su postgres -c "$PG_BIN/psql -d aletheia -f /app/db/init.sql"
su postgres -c "$PG_BIN/psql -d aletheia -c \"GRANT ALL PRIVILEGES ON ALL TABLES IN SCHEMA public TO aletheia; GRANT ALL PRIVILEGES ON ALL SEQUENCES IN SCHEMA public TO aletheia;\""

su postgres -c "$PG_BIN/pg_ctl -D $PGDATA -w stop"

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
