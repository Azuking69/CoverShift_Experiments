"""3つのプロセス（api / scheduler / worker）が共通で使う道具。"""
import os
import time
import psycopg

# os: 環境変数を読むために使う
DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://wq:wq@localhost:5433/wq")



# DB 接続
def connect():
    # autocommit=True: 1つの SQL が、そのまま確定する。まとめて確定したいときは
    # `with conn.transaction():` を使う（worker.py の finish を参照）
    return psycopg.connect(DATABASE_URL, autocommit=True)


# ログ出力
def log(role: str, message: str):
    # strftime: 時間を文字列に変換する。%H:%M:%S は「時:分:秒」の形式
    # role: api / scheduler / worker のどれが出力したかを示す
    # flush=True: バッファリングせずにすぐ出力する。ログが遅れて出るのを防ぐ
    print(f"{time.strftime('%H:%M:%S')} [{role}] {message}", flush=True)



def ensure_schema():
    """あとから足した列を、古い DB にも足す（何回実行しても安全）。api / worker / scheduler の起動時に呼ぶ。"""
    with connect() as conn:
        # ALTER TABLE ... ADD COLUMN IF NOT EXISTS: すでに列がある場合は何もしない
        conn.execute("ALTER TABLE queue ADD COLUMN IF NOT EXISTS done_at TIMESTAMPTZ")
