import time
from langgraph.checkpoint.postgres import PostgresSaver
from langgraph.types import Command
from worker_queue.common import connect, log, DB_URL

from prototype_01 import builder


# 0) 途中で止まったジョブを、再び待機状態に戻す
STUCK_SECONDS = 600


# 1) 「キューから票を1枚取る SQL」
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

# 「処理中の票が、一定時間経ったら再び待機状態に戻す SQL」
REQUEUE_SQL = """
    UPDATE queue SET status = 'waiting', locked_at = NULL
    WHERE status = 'processing' AND locked_at < now() - make_interval(secs => %s)
    RETURNING id, case_id, event
"""


# 2) グラフを実行する関数
# 取った票の中身を見て、どのグラフ操作をするか決める係
def run_graph(graph, case_id, store_id, event):
    # thread_id(case-1): 「この案件の途中経過は、この名前のノートに書く」という名前
    # 同じ名前を使うから、あとで続きから動かせる
    config = {"configurable": {"thread_id": f"case-{case_id}"}}

    # event に応じて、グラフの操作を決める
    if event == "deadline":
        snap = graph.get_state(config)                                       # 途中経過を取得
        started = bool(snap.values)                                          # すでに始まっているかどうか
        waiting = bool(snap.next) and any(t.interrupts for t in snap.tasks)  # 途中で止まっているかどうか
        midway = bool(snap.next) and not waiting                             # 途中で止まっていないが、まだ終わっていないかどうか

        # started, midway の3通りに分けて、グラフを動かす
        if not started:
            graph.invoke({"store_id": store_id}, config)                        # まだ始まっていない → 新規に動かす
        elif midway:
            log("worker", f"案件{case_id}: 途中まで終わっている → 続きから動かす")
            graph.invoke(None, config)                                          # 途中まで終わっている → 続きから動かす
        else:
            log("worker", f"案件{case_id}: すでに始まっている → 無視")

    # approve は、店長が承認ボタンを押したときの合図
    elif event == "approve":
        graph.invoke(Command(resume=True), config)
    else:
        log("worker", f"合図'{event}'は使わないので無視します")


# 3) キューのジョブを処理する
# ずっと繰り返して、1と2を呼ぶ係
def main():
    log("worker", "起動")                                                      # 起動表示
    with connect() as conn, PostgresSaver.from_conn_string(DB_URL) as saver:   # データベース接続
        saver.setup()                                                          # チェックポイント用のテーブルを作る
        graph = builder.compile(checkpointer=saver)                            # グラフをコンパイル 
        while True:
            # ← 空欄:log に「仕事○(案件○ '○')が止まっていたので待ちに戻した」と出す
            for job_id, case_id, event in conn.execute(REQUEUE_SQL, (STUCK_SECONDS,)).fetchall():
                log("worker", f"仕事{job_id}(案件{case_id} '{event}')が止まっていたので待ちに戻した")
            job = conn.execute(CLAIM_SQL).fetchone()                       # 票を1枚取る。なければ None

            # ジョブがない場合は1秒待機して再試行
            if job is None:
                time.sleep(1)
                continue

            job_id, case_id, event=job
            log("worker", f"仕事{job_id}を取った: 案件{case_id} の合図 '{event}'")                           # 票があったら、「仕事○を取った」と言う
            store_id = conn.execute("SELECT store_id FROM cases WHERE id = %s", (case_id,)).fetchone()[0]  # その案件が、どの店かを調べる(store_id)
            run_graph(graph, case_id, store_id, event)                                                     # run_graph を呼ぶ(ここでLLMが動く)
            conn.execute("UPDATE queue SET status = 'done', done_at = now() WHERE id = %s", (job_id,))     # 終わったら、票をdoneにする




# 4) キューのジョブを処理する
if __name__ == "__main__":
    main()