import time
from worker_queue.common import connect, log

POLL_SECONDS = 2

# 1つの SQL で「予約を“出した”にする」と「キューへ足す」を同時にやる。
# 途中で落ちても、半分だけ進むことがない。スケジューラーを2つ動かしても二重にならない
# （FOR UPDATE SKIP LOCKED：他の人が掴んでいる行は飛ばす）。
MOVE_DUE_SQL = """
    WITH due AS (
        SELECT id FROM scheduler
        WHERE fired = false AND fire_at <= now()
        ORDER BY fire_at
        FOR UPDATE SKIP LOCKED
    ), upd AS (
        UPDATE scheduler s SET fired = true
        FROM due WHERE s.id = due.id
        RETURNING s.case_id, s.event, s.fire_at
    )
    INSERT INTO queue(case_id, event)
    SELECT case_id, event FROM upd ORDER BY fire_at
    RETURNING case_id, event
"""


def main():
    log("scheduler", f"起動。{POLL_SECONDS}秒ごとに予約表を見る")
    with connect() as conn:
        while True:
            for case_id, event in conn.execute(MOVE_DUE_SQL).fetchall(): # 予約が来た行を取得
                log("scheduler", f"締切が来た → キューへ: 案件{case_id} の合図 '{event}'")
            time.sleep(POLL_SECONDS)


if __name__ == "__main__":
    main()