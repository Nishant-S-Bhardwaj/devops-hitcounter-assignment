import os
import time
import psycopg
from flask import Flask, jsonify

app = Flask(__name__)
DSN = os.environ["DATABASE_URL"]
VERSION = os.environ.get("APP_VERSION", "dev")


def db():
    return psycopg.connect(DSN, connect_timeout=3)


def init_db():
    for _ in range(30):
        try:
            with db() as conn:
                conn.execute(
                    "CREATE TABLE IF NOT EXISTS hits "
                    "(id serial PRIMARY KEY, at timestamptz DEFAULT now())"
                )
            return
        except psycopg.OperationalError:
            time.sleep(1)
    raise SystemExit("database never became ready")


@app.get("/")
def index():
    with db() as conn:
        conn.execute("INSERT INTO hits DEFAULT VALUES")
        n = conn.execute("SELECT count(*) FROM hits").fetchone()[0]
    return jsonify(message="hello", version=VERSION, hits=n)


@app.get("/healthz")
def healthz():
    try:
        with db() as conn:
            conn.execute("SELECT 1")
    except Exception:
        return jsonify(status="db down"), 503
    return jsonify(status="ok", version=VERSION)


init_db()

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8000)
