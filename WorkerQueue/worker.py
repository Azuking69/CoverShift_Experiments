"""worker：キューから仕事を1件取って、状態を進める。

起動: python worker.py            （WORK_SECONDS=3 python worker.py のように処理時間を変えられる）
折衷案の consumer Lambda に当たる。

ここで学ぶこと:
  1. 同じ案件の合図は、順番どおりに1つずつ（FIFO のグループ ＝ 案件）
  2. ワーカーを何個動かしても、同じ仕事を2回やらない（SKIP LOCKED）
  3. 処理中に落ちたら、仕事は一定時間後に戻ってやり直される
"""
import os
import time
from common import connect, log

POLL_SECONDS = 1
WORK_SECONDS = float(os.getenv("WORK_SECONDS", "2"))   # 重い処理のまね（CP-SAT や LLM の待ち時間）
STUCK_SECONDS = int(os.getenv("STUCK_SECONDS", "10"))  # 処理中のまま、これ以上たったら「落ちた」とみなす
WORKER_NAME = os.getenv("WORKER_NAME", f"worker-{os.getpid()}")

# 仕事を1件取る。条件:
#   ・待ち（waiting）である
#   ・同じ案件が処理中ではない        → 同じ案件は同時に1つだけ
#   ・同じ案件で、もっと古い待ちがない → 古い順に処理する
#   ・他のワーカーが掴んでいる行は飛ばす（SKIP LOCKED）→ 二重に取らない
CLAIM_SQL = """
UPDATE queue SET status = 'processing', locked_at = now()
WHERE id = (
    SELECT q.id FROM queue q
    WHERE q.status = 'waiting'
      AND NOT EXISTS (SELECT 1 FROM queue p WHERE p.case_id = q.case_id AND p.status = 'processing')
      AND NOT EXISTS (SELECT 1 FROM queue e WHERE e.case_id = q.case_id AND e.status = 'waiting' AND e.id < q.id)
    ORDER BY q.id
    FOR UPDATE SKIP LOCKED
    LIMIT 1
)
RETURNING id, case_id, event
"""

# 処理中のまま放置された仕事を、待ちに戻す（落ちたワーカーの後始末）
REQUEUE_SQL = """
UPDATE queue SET status = 'waiting', locked_at = NULL
WHERE status = 'processing' AND locked_at < now() - make_interval(secs => %s)
RETURNING id, case_id, event
"""


def finish(conn, job_id, case_id, event):
    """状態を進める ＋ 仕事を完了にする。この2つは、まとめて確定する（片方だけ進まない）。"""
    from states import next_state

    with conn.transaction():
        row = conn.execute("SELECT state FROM cases WHERE id = %s FOR UPDATE", (case_id,)).fetchone()
        current = row[0]
        new = next_state(current, event)
        if new is None:
            log(WORKER_NAME, f"案件{case_id}: 状態 '{current}' に合図 '{event}' は不要 → 無視して完了")
        else:
            conn.execute("UPDATE cases SET state = %s, updated_at = now() WHERE id = %s", (new, case_id))
            log(WORKER_NAME, f"案件{case_id}: '{current}' → '{new}'  (合図 '{event}')")
        conn.execute("UPDATE queue SET status = 'done' WHERE id = %s", (job_id,))


def main():
    log(WORKER_NAME, f"起動。1件の処理に約{WORK_SECONDS}秒かかる設定")
    with connect() as conn:
        while True:
            for job_id, case_id, event in conn.execute(REQUEUE_SQL, (STUCK_SECONDS,)).fetchall():
                log(WORKER_NAME, f"仕事{job_id}(案件{case_id} '{event}') が止まっていたので待ちに戻した")

            job = conn.execute(CLAIM_SQL).fetchone()
            if job is None:
                time.sleep(POLL_SECONDS)
                continue

            job_id, case_id, event = job
            log(WORKER_NAME, f"仕事{job_id}を取った: 案件{case_id} の合図 '{event}'")
            time.sleep(WORK_SECONDS)  # ← ここで Ctrl+C すると「処理中に落ちた」を再現できる
            finish(conn, job_id, case_id, event)


if __name__ == "__main__":
    main()
