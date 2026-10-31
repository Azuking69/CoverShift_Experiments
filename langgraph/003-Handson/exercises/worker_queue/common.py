import os
import time
import psycopg
from dotenv import load_dotenv


# 0) 環境変数をロードする
load_dotenv()
DB_URL = os.environ["DB_URL"]


# 1) DB の入り口を開ける
def connect():
    # DB の入り口を開ける。psycopg は、Python から PostgreSQL に話しかける部品
    return psycopg.connect(DB_URL, autocommit=True)


# 2) 「何時に・誰が・何をした」を表示する
# role: 誰が
# message: 何をした
def log(role, message):
    print(f"{time.strftime('%H:%M:%S')} [{role}] {message}", flush=True)