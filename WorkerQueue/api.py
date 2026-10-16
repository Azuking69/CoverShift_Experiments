"""api：案件を作る・締切を登録する・様子を見る。仕事そのものはしない。

起動: uvicorn api:app --port 8000
"""
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from common import connect

app = FastAPI(title="WorkerQueue")


class NewCase(BaseModel):
    name: str


class Deadline(BaseModel):
    seconds: int = 10  # 何秒後に締切の合図を出すか（デモ用に短く）


class Event(BaseModel):
    event: str  # review_done / approved など


def _one(conn, sql, params=()):
    cur = conn.execute(sql, params)
    cols = [c.name for c in cur.description]
    row = cur.fetchone()
    return dict(zip(cols, row)) if row else None


def _all(conn, sql, params=()):
    cur = conn.execute(sql, params)
    cols = [c.name for c in cur.description]
    return [dict(zip(cols, r)) for r in cur.fetchall()]


@app.post("/cases")
def create_case(body: NewCase):
    with connect() as conn:
        return _one(conn, "INSERT INTO cases(name) VALUES (%s) RETURNING id, name, state", (body.name,))


@app.post("/cases/{case_id}/deadline")
def set_deadline(case_id: int, body: Deadline):
    """管理者が締切を設定した、に当たる。予約表に1行入れるだけ。"""
    with connect() as conn:
        if not _one(conn, "SELECT id FROM cases WHERE id=%s", (case_id,)):
            raise HTTPException(404, "case not found")
        return _one(
            conn,
            "INSERT INTO schedules(case_id, event, fire_at) "
            "VALUES (%s, 'deadline', now() + make_interval(secs => %s)) RETURNING id, fire_at",
            (case_id, body.seconds),
        )


@app.post("/cases/{case_id}/events")
def send_event(case_id: int, body: Event):
    """合図を、予約を通さずに直接キューへ入れる（順番や二重処理のテスト用）。"""
    with connect() as conn:
        if not _one(conn, "SELECT id FROM cases WHERE id=%s", (case_id,)):
            raise HTTPException(404, "case not found")
        return _one(conn, "INSERT INTO queue(case_id, event) VALUES (%s, %s) RETURNING id, event, status",
                    (case_id, body.event))


@app.get("/cases")
def list_cases():
    with connect() as conn:
        return _all(conn, "SELECT id, name, state FROM cases ORDER BY id")


@app.get("/cases/{case_id}")
def get_case(case_id: int):
    with connect() as conn:
        row = _one(conn, "SELECT id, name, state FROM cases WHERE id=%s", (case_id,))
        if not row:
            raise HTTPException(404, "case not found")
        return row


@app.get("/queue")
def list_queue():
    with connect() as conn:
        return _all(conn, "SELECT id, case_id, event, status FROM queue ORDER BY id")
