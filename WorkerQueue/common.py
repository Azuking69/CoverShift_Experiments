"""3つのプロセス（api / scheduler / worker）が共通で使う道具。"""
import os
import time
import psycopg

DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://wq:wq@localhost:5433/wq")


def connect():
    # autocommit=True: 1つの SQL が、そのまま確定する。まとめて確定したいときは
    # `with conn.transaction():` を使う（worker.py の finish を参照）
    return psycopg.connect(DATABASE_URL, autocommit=True)


def log(role: str, message: str):
    print(f"{time.strftime('%H:%M:%S')} [{role}] {message}", flush=True)


def ensure_schema():
    """あとから足した列を、古い DB にも足す（何回実行しても安全）。api / worker / scheduler の起動時に呼ぶ。"""
    with connect() as conn:
        conn.execute("ALTER TABLE queue ADD COLUMN IF NOT EXISTS done_at TIMESTAMPTZ")
