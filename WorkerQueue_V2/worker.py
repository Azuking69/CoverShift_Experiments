"""worker（V2）：キューから仕事を1件取って、LangGraph のグラフを進める。

V1 との違い：「状態表で次の状態を引く」代わりに、graph.py のグラフを動かす。
グラフの途中経過は PostgreSQL に保存されるので、落ちても、承認待ちで止めても、続きから再開できる。


起動: python worker.py            （WORK_SECONDS=3 python worker.py のように処理時間を変えられる）
折衷案の consumer Lambda に当たる。

ここで学ぶこと:
  1. 同じ案件の合図は、順番どおりに1つずつ（FIFO のグループ ＝ 案件）
  2. ワーカーを何個動かしても、同じ仕事を2回やらない（SKIP LOCKED）
  3. 処理中に落ちたら、仕事は一定時間後に戻ってやり直される
"""
import os
import time
from langgraph.checkpoint.postgres import PostgresSaver
from langgraph.types import Command
from common import connect, log, ensure_schema, DATABASE_URL
from graph import build, WORK_SECONDS

POLL_SECONDS = 1
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


def run_graph(graph, case_id, event):
    """合図に応じて、グラフを「始める／続ける／再開する」。同じ合図が2回来ても、結果が変わらないようにする。"""
    cfg = {"configurable": {"thread_id": f"case-{case_id}"}}
    snap = graph.get_state(cfg)
    started = bool(snap.values)
    waiting = bool(snap.next) and any(t.interrupts for t in snap.tasks)  # 承認待ちで止まっている
    midway = bool(snap.next) and not waiting                              # 途中で落ちた（続きがある）

    if event == "deadline":
        if not started:
            log(WORKER_NAME, f"案件{case_id}: グラフを新しく始める")
            graph.invoke({"case_id": case_id, "a_done": False, "b_done": False, "approved": False}, cfg)
        elif midway:
            log(WORKER_NAME, f"案件{case_id}: 途中まで終わっている → 次は {snap.next} から続ける")
            graph.invoke(None, cfg)
        else:
            log(WORKER_NAME, f"案件{case_id}: すでに始まっている（{'承認待ち' if waiting else '完了'}） → 無視")
    elif event == "approved":
        if waiting:
            log(WORKER_NAME, f"案件{case_id}: 承認待ちから再開する")
            graph.invoke(Command(resume=True), cfg)
        elif midway:
            log(WORKER_NAME, f"案件{case_id}: 途中から続ける（承認は、承認待ちに着いたあとに受ける）")
            graph.invoke(None, cfg)
        else:
            log(WORKER_NAME, f"案件{case_id}: 承認待ちではない → 無視")
    else:
        log(WORKER_NAME, f"案件{case_id}: 合図 '{event}' はV2では使わない → 無視")


def complete(conn, job_id):
    conn.execute("UPDATE queue SET status = 'done', done_at = now() WHERE id = %s", (job_id,))


def main():
    ensure_schema()
    log(WORKER_NAME, f"起動。1ステップに約{WORK_SECONDS}秒かかる設定")
    with connect() as conn, PostgresSaver.from_conn_string(DATABASE_URL) as saver:
        saver.setup()  # グラフの保存用の表を作る（何回実行しても安全）
        graph = build(saver)
        while True:
            for job_id, case_id, event in conn.execute(REQUEUE_SQL, (STUCK_SECONDS,)).fetchall():
                log(WORKER_NAME, f"仕事{job_id}(案件{case_id} '{event}') が止まっていたので待ちに戻した")

            job = conn.execute(CLAIM_SQL).fetchone()
            if job is None:
                time.sleep(POLL_SECONDS)
                continue

            job_id, case_id, event = job
            log(WORKER_NAME, f"仕事{job_id}を取った: 案件{case_id} の合図 '{event}'")
            run_graph(graph, case_id, event)  # ← 処理中に落とすと、次のワーカーが続きから再開する
            complete(conn, job_id)


if __name__ == "__main__":
    main()
