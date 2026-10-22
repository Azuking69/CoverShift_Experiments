"""V2 の確認用。使い方: python try_v2.py <1|2|3|4>
  1 承認待ちで止めて、ワーカーを全部止めても、あとで再開できる
  2 処理の途中でワーカーを落としても、終わった分をやり直さず、続きから再開する
  3 1つの処理が STUCK_SECONDS(10秒) を超えると、別のワーカーが取り直す（課題4で未実行だった弱点を見る）
  4 順番どおり・二重取りなし・同じ合図が2回来ても結果が同じ
事前に PostgreSQL を立て、DATABASE_URL を設定しておくこと。
"""
import os, subprocess, sys, time
import psycopg

URL = os.getenv("DATABASE_URL", "postgresql://wq:wq@localhost:5433/wq")
ENV = {**os.environ, "DATABASE_URL": URL, "PYTHONUTF8": "1", "PYTHONIOENCODING": "utf-8"}  # Windowsでも日本語のログが文字化けしないように
procs = []


def q(sql, params=()):
    with psycopg.connect(URL, autocommit=True) as c:
        cur = c.execute(sql, params)
        return cur.fetchall() if cur.description else None


def reset():
    q("DROP SCHEMA public CASCADE; CREATE SCHEMA public;")
    q(open("db.sql", encoding="utf-8").read())
    subprocess.run([sys.executable, "-c",
        "from langgraph.checkpoint.postgres import PostgresSaver; import os\n"
        "with PostgresSaver.from_conn_string(os.environ['DATABASE_URL']) as s: s.setup()"], env=ENV, check=True)


def start(script, name=None, **env):
    e = {**ENV, **{k: str(v) for k, v in env.items()}}
    if name: e["WORKER_NAME"] = name
    p = subprocess.Popen([sys.executable, "-u", script], env=e, stdout=open(f"log_{name or script}.txt", "a"), stderr=subprocess.STDOUT)
    procs.append(p)
    return p


def kill(p):
    p.kill(); p.wait()  # 強制終了（Linuxは kill -9、Windowsは TerminateProcess。どちらも「いきなり落ちる」）


def cleanup():
    for p in procs:
        if p.poll() is None: p.kill()


def new_case(name="case"):
    return q("INSERT INTO cases(name) VALUES (%s) RETURNING id", (name,))[0][0]


def event(case_id, ev):
    q("INSERT INTO queue(case_id, event) VALUES (%s,%s)", (case_id, ev))


def state(case_id): return q("SELECT state FROM cases WHERE id=%s", (case_id,))[0][0]


def runs(case_id):
    rows = q("SELECT node, worker FROM node_runs WHERE case_id=%s ORDER BY id", (case_id,))
    out = {}
    for n, w in rows: out.setdefault(n, []).append(w)
    return out


def wait_for(fn, timeout=60, label=""):
    t = time.time()
    while time.time() - t < timeout:
        if fn(): return True
        time.sleep(0.5)
    print(f"  !! タイムアウト: {label}"); return False


def show(title, ok): print(("  ✅ " if ok else "  ❌ ") + title)


def t1():
    print("① 承認待ちで止めて、ワーカーを全部止めてから再開")
    reset(); c = new_case()
    w = start("worker.py", "A", WORK_SECONDS=1)
    event(c, "deadline")
    wait_for(lambda: state(c) == "waiting_approval", 30, "承認待ちに到達")
    time.sleep(2)
    print("  承認待ち中の queue:", q("SELECT status, count(*) FROM queue GROUP BY status"))
    show("承認待ちの間、processing の仕事は0件（ワーカーは何も握らない）",
         q("SELECT count(*) FROM queue WHERE status='processing'")[0][0] == 0)
    kill(w); print("  → ワーカーを全部止めた（3秒待つ）"); time.sleep(3)
    w2 = start("worker.py", "B", WORK_SECONDS=1)
    event(c, "approved")
    ok = wait_for(lambda: state(c) == "finished", 30, "finished")
    show("別のワーカー(B)が、承認の合図から再開して finished になった", ok)
    r = runs(c); print("  実行記録:", r)
    show("step_a・step_b は1回ずつだけ（再開で計算をやり直していない）", len(r.get("step_a", [])) == 1 and len(r.get("step_b", [])) == 1)


def t2():
    print("② 処理の途中（step_b の最中）で落とす")
    reset(); c = new_case()
    w = start("worker.py", "A", WORK_SECONDS=3, STUCK_SECONDS=10)
    event(c, "deadline")
    wait_for(lambda: "step_b" in runs(c), 30, "step_b 開始")
    time.sleep(1); kill(w); print("  → step_b の途中で A を落とした（kill -9）")
    t0 = time.time()
    start("worker.py", "B", WORK_SECONDS=3, STUCK_SECONDS=10)
    ok = wait_for(lambda: state(c) == "waiting_approval", 60, "承認待ちに到達")
    print(f"  B が引き継いで承認待ちに着くまで: 約{time.time()-t0:.0f}秒（待ちに戻る10秒を含む）")
    r = runs(c); print("  実行記録:", r)
    show("承認待ちまで到達した", ok)
    show("step_a は1回だけ（終わった分はやり直していない）", len(r.get("step_a", [])) == 1)
    show("step_b は2回（落ちた回＋再開した回）。落ちた途中の1ステップだけやり直し", len(r.get("step_b", [])) == 2)


def t3():
    print("③ 1ステップが10秒を超える（8秒×2ステップ＝16秒。STUCK_SECONDS=10）")
    reset(); c = new_case()
    start("worker.py", "A", WORK_SECONDS=8, STUCK_SECONDS=10)
    start("worker.py", "B", WORK_SECONDS=8, STUCK_SECONDS=10)
    event(c, "deadline")
    time.sleep(40)
    r = runs(c); print("  実行記録:", r)
    print("  案件の状態:", state(c), " queue:", q("SELECT id,event,status FROM queue ORDER BY id"))
    print("  checkpoint数:", q("SELECT count(*) FROM checkpoints")[0][0])
    for n in ("A", "B"):
        print(f"  --- worker {n} のログ ---"); print(open(f"log_{n}.txt", encoding="utf-8").read())
    dup = any(len(v) > 1 for v in r.values())
    show("どのステップも1回だけ（二重に動いていない）" if not dup else "二重に動いたステップがある（弱点を確認）", not dup)


def t4():
    print("④ 順番・二重取り：承認が先に来る／deadline が2回来る／2案件を2ワーカーで")
    reset(); c1, c2 = new_case("c1"), new_case("c2")
    start("worker.py", "A", WORK_SECONDS=1); start("worker.py", "B", WORK_SECONDS=1)
    time.sleep(2)
    for ev in ("approved", "deadline", "deadline"): event(c1, ev)   # 承認が先・deadline 二重
    for ev in ("deadline",): event(c2, ev)
    wait_for(lambda: state(c1) == "waiting_approval" and state(c2) == "waiting_approval", 40, "両方承認待ち")
    time.sleep(3)
    print("  案件1:", state(c1), runs(c1)); print("  案件2:", state(c2), runs(c2))
    show("案件1：先に来た approved は無視され、deadline は1回だけ実行（step_a 1回）", state(c1) == "waiting_approval" and len(runs(c1).get("step_a", [])) == 1)
    show("案件2：2ワーカーでも step_a は1回", len(runs(c2).get("step_a", [])) == 1)
    event(c1, "approved"); event(c2, "approved"); event(c2, "approved")
    wait_for(lambda: state(c1) == "finished" and state(c2) == "finished", 40, "両方 finished")
    show("両方 finished（二重の approved は無視）", state(c1) == "finished" and state(c2) == "finished")
    print("  queue:", q("SELECT status, count(*) FROM queue GROUP BY status"))
    print("  案件1の記録の順:", [r[0] for r in q("SELECT event FROM queue WHERE case_id=%s ORDER BY id", (c1,))],
          "→ 実行の順（done_at）:", [r[0] for r in q("SELECT event FROM queue WHERE case_id=%s ORDER BY done_at", (c1,))])


if __name__ == "__main__":
    for n in ("A", "B", "worker.py"):
        try: os.remove(f"log_{n}.txt")
        except FileNotFoundError: pass
    try:
        {"1": t1, "2": t2, "3": t3, "4": t4}[sys.argv[1]]()
    finally:
        cleanup()