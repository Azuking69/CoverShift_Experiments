"""api：案件を作る・締切を登録する・様子を見る。仕事そのものはしない。

起動: uvicorn api:app --port 8000

このファイルは「窓口」です。外から来た依頼を受け取って、
データベース（PostgreSQL）に書き込んだり、読んで返したりするだけです。
仕事を進めるのは worker.py、時刻を見張るのは scheduler.py の担当です。
"""
from fastapi import FastAPI, HTTPException  # FastAPI：窓口の本体 / HTTPException：エラーを返すための道具
from pydantic import BaseModel                 # BaseModel：「受け取るデータの書式」を作る土台
from common import connect, ensure_schema     # 自作の common.py から：DBにつなぐ関数と、列を足す関数

# ------------------------------------------------------------
# 0. 準備
# ------------------------------------------------------------

# 足りない列（queue.done_at）があれば足す。すでにあれば何もしない
ensure_schema()

# FastAPI(...)：窓口の本体（インスタンス＝実物）を作る。title は自動でできる説明ページの題名
# この app に「このアドレスが来たら、この関数」を登録していく
app = FastAPI(title="WorkerQueue")


# ------------------------------------------------------------
# 1. 受け取るデータの「書式」
#    外から届くデータが「こういう形のはず」と先に決めておく。
#    形が違う（例：seconds に「あした」）と、FastAPI が自動で断る（エラー422）
# ------------------------------------------------------------

# 案件を作るときに受け取るデータ
class NewCase(BaseModel):  # class：データの「型」を作る。BaseModel を土台にすると、形の確認が自動で付く
    name: str  # 案件の名前。str＝文字


# 締切を登録するときに受け取るデータ
class Deadline(BaseModel):
    seconds: int = 10  # 何秒後に締切の合図を出すか。int＝整数。「= 10」は省略したときの初期値。デモ用に短くしてある


# 合図を直接入れるときに受け取るデータ
class Event(BaseModel):
    event: str  # 合図の名前（文字）。例：review_done / approved


# ------------------------------------------------------------
# 2. 道具の関数（名前が _ で始まるのは「このファイルの中だけで使う」印）
#    データベースの答えを、JSON にできる形（辞書）に直すだけ
# ------------------------------------------------------------

# SQL を実行して、答えの「1行」を辞書で返す。答えが空なら None
# 例：{"id": 1, "name": "A店", "state": "collecting"}
# 引数：conn＝DBとのつながり / sql＝実行する SQL / params＝SQL の %s に入れる値（なければ空）
def _one(conn, sql, params=()):
    cur = conn.execute(sql, params)           # execute：SQL を実行するメソッド。答えを読む係（cur＝カーソル）が返る
    cols = [c.name for c in cur.description]  # description：答えの列の情報。そこから列の名前（id, name, state ...）を集める
    row = cur.fetchone()                      # fetchone：答えの「1行」を取り出す。もう行がなければ None
    # zip：列の名前と値を、順番にペアにする  dict：そのペアから辞書を作る
    # 「A if 条件 else B」：条件が成り立てば A、そうでなければ B。ここでは、答えが空なら None を返す
    return dict(zip(cols, row)) if row else None


# SQL を実行して、答えの「全部の行」を、辞書のリストで返す
def _all(conn, sql, params=()):
    cur = conn.execute(sql, params)
    cols = [c.name for c in cur.description]
    # fetchall：答えの「全部の行」を取り出す。[... for r in ...]：1行ずつ辞書にして、リストに集める
    return [dict(zip(cols, r)) for r in cur.fetchall()]


# ------------------------------------------------------------
# 3. 窓口（アドレスごとの関数）
#    @app.post / @app.get の行が「このアドレスに、この種類の依頼が来たら
#    下の関数を動かす」という登録。post＝書き込む、get＝見るだけ
# ------------------------------------------------------------

# 案件を作る        POST /cases
@app.post("/cases")
def create_case(body: NewCase):  # body：届いたデータ。NewCase の形のはず
    # with ~ as conn：connect() で作ったDBとのつながりを conn と呼び、ブロックを出たら自動で閉じる
    with connect() as conn:
        # %s：「値が入る場所」の印（プレースホルダ）。値は後ろの (body.name,) から入る
        #     SQL に値を直接つなげないので、変な文字を入れられても安全
        # body.name：届いた NewCase の name
        # RETURNING：追加した行（id, name, state）をそのまま返す、という意味
        return _one(conn, "INSERT INTO cases(name) VALUES (%s) RETURNING id, name, state", (body.name,))


# 締切を登録する    POST /cases/（案件の番号）/deadline
# {case_id} の部分に入った番号が、関数の引数 case_id に入る
@app.post("/cases/{case_id}/deadline")
def set_deadline(case_id: int, body: Deadline):
    """管理者が締切を設定した、に当たる。予約表に1行入れるだけ。"""
    with connect() as conn:
        # その案件があるか先に確かめる。なければ「見つからない」を返して終わる
        if not _one(conn, "SELECT id FROM cases WHERE id=%s", (case_id,)):
            # raise：エラー（例外）を発生させて、ここで処理を打ち切る
            # HTTPException：エラーを窓口の返事として返すための道具
            # 404：「見つからない」を表す番号  "case not found"：エラーの文章
            raise HTTPException(404, "case not found")
        # 予約表(schedules)に「今から seconds 秒後に、deadline の合図」を1行入れる
        # now() + make_interval(secs => N)：「今の時刻」＋「N秒」＝N秒後の時刻（fire_at＝合図を出す時刻）
        # 時刻になったら、scheduler.py がこの予約を仕事リストへ移す
        return _one(
            conn,
            "INSERT INTO schedules(case_id, event, fire_at) "
            "VALUES (%s, 'deadline', now() + make_interval(secs => %s)) RETURNING id, fire_at",
            (case_id, body.seconds),
        )


# 合図を直接入れる  POST /cases/（案件の番号）/events
@app.post("/cases/{case_id}/events")
def send_event(case_id: int, body: Event):
    """合図を、予約を通さずに直接キューへ入れる（順番や二重処理のテスト用）。"""
    with connect() as conn:
        if not _one(conn, "SELECT id FROM cases WHERE id=%s", (case_id,)):
            raise HTTPException(404, "case not found")
        # 予約表を通さず、仕事リスト(queue)へ直接入れる。ワーカーがこれを取って処理する
        return _one(conn, "INSERT INTO queue(case_id, event) VALUES (%s, %s) RETURNING id, event, status",
                    (case_id, body.event))


# 案件の一覧を見る  GET /cases
@app.get("/cases")
def list_cases():
    with connect() as conn:
        # ORDER BY id：id の小さい順に並べる
        return _all(conn, "SELECT id, name, state FROM cases ORDER BY id")


# 案件を1件見る     GET /cases/（案件の番号）
@app.get("/cases/{case_id}")
def get_case(case_id: int):
    with connect() as conn:
        row = _one(conn, "SELECT id, name, state FROM cases WHERE id=%s", (case_id,))
        if not row:  # row が None（空）なら、案件がなかったということ
            raise HTTPException(404, "case not found")  # 案件がなければ 404（見つからない）
        return row


# 仕事リストの中身を見る  GET /queue
@app.get("/queue")
def list_queue():
    with connect() as conn:
        return _all(conn, "SELECT id, case_id, event, status, locked_at, done_at FROM queue ORDER BY id")