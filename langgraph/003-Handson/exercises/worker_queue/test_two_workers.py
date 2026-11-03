"""
2つのワーカーの同時実行テスト(LLM は呼ばない。グラフも動かさない)
  確かめること
    ① 2つのワーカーで票を分け合うとき、同じ票を二重に取らない
    ② 同じ案件の票は、同時に動かない(古い順)。違う案件は、同時に動く
    ③ 合図(heartbeat_at の更新)がないと、STUCK_SECONDS より長い仕事は二重に取られる
    ④ 合図があれば二重にならない
    ⑤ ワーカーが落ちて合図が止まったら、別のワーカーが拾い直す
  使い方(exercises フォルダで)
    先に worker.py と scheduler.py を止める → python -m worker_queue.test_two_workers
  票の合図は 'test'(本物のワーカーが動いていても、無視されるだけ)
"""
import os, re, sys, time, threading, pathlib

# --- DB への接続(いつもの common.py があればそれを使う) ---
try:
    from worker_queue.common import connect
except Exception:
    import psycopg
    def connect():
        return psycopg.connect(os.environ["TEST_DSN"], autocommit=True)

# --- worker.py の中の SQL を、そのまま読み取る(prototype_01 は読み込まない) ---
here = pathlib.Path(__file__).with_name("worker.py")
src = here.read_text(encoding="utf-8")
def grab(name):
    m = re.search(name + r'\s*=\s*"""(.*?)"""', src, re.S)
    return m.group(1)
CLAIM_SQL, REQUEUE_SQL = grab("CLAIM_SQL"), grab("REQUEUE_SQL")

WORK = 1.0   # 1枚の仕事にかかる秒数(LLM の代わりの sleep)
log_lock = threading.Lock()

def beat(job_id, stop, every):
    """仕事中、every 秒ごとに「生きている」と知らせる(worker.py の beat と同じ)"""
    with connect() as c2:
        while not stop.wait(every):
            c2.execute("UPDATE queue SET heartbeat_at = now() WHERE id = %s", (job_id,))

def worker(name, conn, events, stop, stuck=None, work=WORK, every=None, die_after=None):
    """本物の worker.py の main と同じ形:(REQUEUE →)CLAIM → 仕事 → done
       every: 合図の間隔(None なら合図なし) / die_after: W1 だけ、この秒数のあと落ちる(done にしない)"""
    while not stop.is_set():
        if stuck is not None:
            for job_id, case_id, ev in conn.execute(REQUEUE_SQL, (stuck,)).fetchall():
                with log_lock: events.append((time.time(), name, "requeue", job_id, case_id))
        job = conn.execute(CLAIM_SQL).fetchone()
        if job is None:
            time.sleep(0.1); continue
        job_id, case_id, ev = job
        with log_lock: events.append((time.time(), name, "start", job_id, case_id))
        bstop = threading.Event()
        if every:
            threading.Thread(target=beat, args=(job_id, bstop, every), daemon=True).start()
        try:
            if die_after is not None and name == "W1":
                time.sleep(die_after)
                with log_lock: events.append((time.time(), name, "die", job_id, case_id))
                return                                   # 落ちた(done にしない)
            time.sleep(work)
        finally:
            bstop.set()
        conn.execute("UPDATE queue SET status='done', done_at=now() WHERE id=%s", (job_id,))
        with log_lock: events.append((time.time(), name, "end", job_id, case_id))

def run(n_workers, tickets, stuck=None, work=WORK, seconds=None, every=None, die_after=None):
    ids = []
    with connect() as c:
        for case_id in tickets:
            ids.append(c.execute("INSERT INTO queue (case_id, event, status) VALUES (%s,'test','waiting') RETURNING id",
                                 (case_id,)).fetchone()[0])
    events, stop = [], threading.Event()
    conns = [connect() for _ in range(n_workers)]
    ths = [threading.Thread(target=worker, args=(f"W{i+1}", conns[i], events, stop, stuck, work, every, die_after)) for i in range(n_workers)]
    t0 = time.time()
    for t in ths:
        t.start()
        if die_after is not None: time.sleep(0.5)   # 落ちる W1 に、先に票を取らせる
    with connect() as c:
        while time.time() - t0 < (seconds or 60):
            left = c.execute("SELECT count(*) FROM queue WHERE id = ANY(%s) AND status <> 'done'", (ids,)).fetchone()[0]
            if left == 0: break
            time.sleep(0.2)
    stop.set(); [t.join() for t in ths]; [c.close() for c in conns]
    return ids, events, t0

def cleanup(ids):
    with connect() as c:
        c.execute("DELETE FROM queue WHERE id = ANY(%s)", (ids,))

def main():
    with connect() as c:
        busy = c.execute("SELECT count(*) FROM queue WHERE status IN ('waiting','processing')").fetchone()[0]
        cases = [r[0] for r in c.execute("SELECT id FROM cases ORDER BY id LIMIT 3").fetchall()]
    if busy:
        print(f"中止: queue に waiting/processing の票が {busy} 枚あります。worker.py と scheduler.py を止めて、片づけてから流してください"); sys.exit(1)
    if len(cases) < 2:
        print("中止: cases に案件が2つ以上必要です"); sys.exit(1)
    ok_all = True
    all_ids = []

    # ---------- ①② 分け合い ----------
    tickets = [c for c in cases for _ in range(2)]            # 例: 案件1,1,2,2,3,3
    ids, ev, t0 = run(2, tickets)
    all_ids += ids
    starts = [e for e in ev if e[2] == "start"]
    ends = {e[3]: e[0] for e in ev if e[2] == "end"}
    st = {e[3]: e[0] for e in starts}
    print("【①② 2つのワーカーで、票%d枚(案件%s)】" % (len(ids), sorted(set(cases))))
    for e in sorted(ev, key=lambda x: x[0]):
        if e[2] in ("start", "end"):
            print(f"  {e[0]-t0:5.1f}秒  {e[1]}  {e[2]:5s} 票{e[3]}(案件{e[4]})")
    taken = [e[3] for e in starts]
    dup = sorted({i for i in taken if taken.count(i) > 1})
    r1 = (sorted(taken) == sorted(ids))
    print("  ① 全部の票が、ちょうど1回ずつ取られた:", "OK" if r1 else f"NG(二重: {dup} / 取られた数 {len(taken)})")
    r2 = True
    for case in cases:
        js = sorted(i for i, c in zip(ids, tickets) if c == case)
        for a, b in zip(js, js[1:]):
            if a in ends and b in st and st[b] < ends[a] - 0.01: r2 = False
            if a in st and b in st and st[b] < st[a]: r2 = False
    print("  ② 同じ案件の票は、重ならず、古い順に動いた:", "OK" if r2 else "NG")
    spans = {}
    for i, c in zip(ids, tickets): spans.setdefault(c, []).append((st[i], ends[i]))
    ov = any(a[0] < b[1] and b[0] < a[1] for x in cases for y in cases if x < y for a in spans[x] for b in spans[y])
    print("  ②' 違う案件は、同時に動いた(重なりあり):", "OK" if ov else "NG(2つが並んで動いていない)")
    total = max(ends.values()) - t0
    print(f"  所要 {total:.1f}秒(1枚{WORK}秒 × {len(ids)}枚 = 1人だと約{WORK*len(ids):.0f}秒)")
    ok_all = ok_all and r1 and r2 and ov

    # ---------- ③④⑤ 長い仕事・落ちたワーカー(STUCK_SECONDS=3 に縮めて試す) ----------
    def count(ev, ids3, kind): return len([e for e in ev if e[2] == kind and e[3] == ids3[0]])
    ids3, ev3, _ = run(2, [cases[0]], stuck=3, work=6.0, seconds=14)             # 合図なし
    all_ids += ids3
    n = count(ev3, ids3, "start"); rq = count(ev3, ids3, "requeue") or len([e for e in ev3 if e[2] == "requeue"])
    r3 = n > 1
    print(f"【③ 合図なし・6秒の仕事1枚・STUCK_SECONDS=3】 取られた回数={n} 待ちに戻された回数={rq}")
    print("  → 仕事中なのに待ちに戻され、別のワーカーが同じ仕事を二重に動かした(危険の再現)" if r3 else "  → 二重にならなかった(想定と違う)")
    ids4, ev4, _ = run(2, [cases[0]], stuck=3, work=6.0, seconds=14, every=1.0)  # 合図あり
    all_ids += ids4
    n = count(ev4, ids4, "start"); rq = len([e for e in ev4 if e[2] == "requeue"])
    r4 = (n == 1 and rq == 0)
    print(f"【④ 合図あり(1秒ごと)・6秒の仕事1枚・STUCK_SECONDS=3】 取られた回数={n} 待ちに戻された回数={rq}")
    print("  → 二重にならない: OK" if r4 else "  → NG(二重になった)")
    ids5, ev5, t5 = run(2, [cases[0]], stuck=3, work=1.0, seconds=14, every=1.0, die_after=2.0)   # W1 が2秒後に落ちる
    all_ids += ids5
    n = count(ev5, ids5, "start"); rq = len([e for e in ev5 if e[2] == "requeue"])
    who = [e[1] for e in sorted(ev5, key=lambda x: x[0]) if e[2] == "start"]
    with connect() as c:
        status = c.execute("SELECT status FROM queue WHERE id=%s", (ids5[0],)).fetchone()[0]
    r5 = (n == 2 and rq == 1 and status == "done" and who == ["W1", "W2"])
    print(f"【⑤ W1 が2秒後に落ちる(合図が止まる)・STUCK_SECONDS=3】 取ったワーカー={who} 待ちに戻された回数={rq} 最後の状態={status}")
    print("  → 落ちたあと、別のワーカーが拾い直して完了した: OK" if r5 else "  → NG")
    ok_all = ok_all and r3 and r4 and r5
    cleanup(all_ids)
    print("まとめ:", "①〜⑤すべて想定どおり" if ok_all else "想定と違うものあり(上を見てください)")

if __name__ == "__main__":
    main()