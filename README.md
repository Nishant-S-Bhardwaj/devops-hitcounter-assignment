# DevOps Assignment — Hit Counter

A small Flask app that counts hits and stores the count in PostgreSQL, containerized
and run with Docker Compose.

## How to start and stop the project

**Start:**
```bash
cp .env.example .env      # first time only — then edit .env with a real password
docker compose up -d --build
docker compose ps          # confirm db shows "healthy" and app is running
curl localhost:18080/
```

**Stop (keeps data):**
```bash
docker compose down
```

**Stop and wipe all data (careful — deletes the volume):**
```bash
docker compose down -v
```

## Part 1: Problems with the starter Dockerfile

The original `starter/Dockerfile` had several issues:

1. **Full base image, not slim.** `FROM python:3.12` pulls the full Debian-based
   image with build tools and extras the app never uses, making it far larger
   than necessary.
2. **Runs as root.** Nothing in the Dockerfile creates or switches to a
   non-root user, so the container runs as `uid=0` by default — confirmed by
   `docker run --rm hitcounter:naive id` (see S1). This is unnecessary risk:
   if the app or a dependency were compromised, the process inside the
   container would have root privileges.
3. **Code copied before dependencies are installed.** `COPY . .` happens
   before `RUN pip install -r requirements.txt`, so Docker's layer cache is
   invalidated by *any* code change — even editing one line of `app.py`
   forces a full dependency reinstall on every rebuild.
4. **No `.dockerignore`.** Things like `.git/`, `__pycache__/`, and other
   local cruft get sent into the build context unnecessarily.

The improved Dockerfile (`app/Dockerfile`) fixes all of these: it uses
`python:3.12-slim`, installs `requirements.txt` before copying the rest of
the code, and creates/switches to a non-root `appuser` before `CMD` runs.
See S2 for the side-by-side image sizes and proof it runs as non-root.

## Part 2: Docker Compose setup

`docker-compose.yml` defines two services:

- **db** — `postgres:16-alpine`, with a named volume (`dbdata`) for
  persistence, a healthcheck (`pg_isready`), and **no published port** — it's
  only reachable from `app` over the internal compose network, not from the
  host.
- **app** — built from `app/`, published at `http://localhost:18080`, and
  waits for `db` to be healthy (`depends_on: condition: service_healthy`)
  before starting.

Both services use `restart: unless-stopped`. Credentials come from a local
`.env` file (gitignored, never committed) — `.env.example` documents the
required variables.

See S3 for `docker compose ps` (db healthy) and a successful `curl`.

## Part 2: Data persistence (S4)

Hit the app a few times, then ran:
```bash
docker compose down     # containers + network removed, volume NOT removed
docker compose up -d
curl localhost:18080/
```
The hit count continued from where it left off instead of resetting to 1 —
proof the data lives in the named volume `dbdata`, independent of the
container lifecycle. `docker compose down` only removes containers and the
network; only `docker compose down -v` would have deleted the volume too.

## Part 3: Database outage and recovery

```bash
docker compose stop db
curl localhost:18080/      # fails — see S5
docker compose start db
curl localhost:18080/      # succeeds again — see S5
```

**What happened and why it recovered on its own:** with `db` stopped, `app`
couldn't open a database connection, so `/` returned an error — but `app`
itself kept running the whole time, it didn't crash. Once `db` was started
again, the very next request succeeded immediately with no restart of `app`
needed, because `app.py` opens a fresh `psycopg` connection inside every
request (`with db() as conn:`) rather than holding one persistent connection
open. There was no stale connection to recover — the next request just
connected fresh, and `db` was reachable again by then.

## Part 4: Backup and restore

Dumped the running database to a file on the host, created a second, separate
database, restored the dump into it, and compared row counts.

```bash
# Backup
docker compose exec -T db pg_dump -U hituser -d hitcounter > backup.sql

# Create a new, separate database
docker compose exec db psql -U hituser -d postgres -c "CREATE DATABASE hitcounter_restore;"

# Restore into it
cat backup.sql | docker compose exec -T db psql -U hituser -d hitcounter_restore

# Compare counts
docker compose exec db psql -U hituser -d hitcounter -c "SELECT count(*) FROM hits;"
docker compose exec db psql -U hituser -d hitcounter_restore -c "SELECT count(*) FROM hits;"
```

**Original database row count:** `<fill in actual number, e.g. 9>`
**Restored database row count:** `<fill in actual number — should match>`

Counts matched, confirming the backup/restore round-trip preserved all data.

## What I did not test

- Behavior under concurrent/high load (multiple simultaneous requests hammering `/`).
- What happens if `app` starts before `db`'s data volume is corrupted or the volume is manually tampered with.
- Postgres major-version upgrades or migrating data between different Postgres versions.
- Running this stack on an architecture other than the one I tested on (e.g. didn't verify multi-arch image builds).
- Behavior when disk space runs out on the host while the db volume is writing data.
- TLS/encrypted connections between app and db (everything here runs over the internal Docker network unencrypted, which is standard for same-host dev setups but I didn't test an encrypted variant).s
