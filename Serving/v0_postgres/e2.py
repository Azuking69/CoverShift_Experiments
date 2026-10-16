"""V0（基準）の E2・E3：PostgreSQLに保存して、計算中に強制終了したあとの状態を見る。
使い方（ルートで）:  python v0_postgres/e2.py
  A 計算中に落とす : 計算の人工的な待ち20秒のうち、開始の8秒後に、プロセスを強制終了 → 状態 → 続きを実行
  B 承認待ちで落ちる: 承認待ちまで進めてプロセスが終了 → 別プロセスから状態 → 承認して再開
  C 同じ案件に同時に2本
"""
import os, subprocess, sys, time, uuid
HERE = os.path.dirname(os.path.abspath(__file__))
W = os.path.join(HERE, "worker.py")

def env(wait): return {**os.environ, "SOLVER_EXTRA_WAIT_SEC": str(wait), "PYTHONUTF8": "1"}
def run(action, tid, wait=0):
    r = subprocess.run([sys.executable, W, action, tid], env=env(wait), capture_output=True, text=True, encoding="utf-8")
    return (r.stdout.strip().splitlines() or ["(出力なし)"])[-1] if r.returncode == 0 else "ERROR " + r.stderr.strip()[-300:]

print("=== A 計算中に落とす（人工的な待ち20秒の、8秒後に強制終了）===")
t = "v0A-" + uuid.uuid4().hex[:8]
p = subprocess.Popen([sys.executable, W, "start", t], env=env(20), stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, encoding="utf-8")
# 起動（部品の読み込み・DB接続・テーブル作成）に時間がかかるので、「STARTED」が出てから数える
line = p.stdout.readline()
if "STARTED" not in line:
    print("ワーカーが開始前に終了した：", p.stderr.read()[-400:]); sys.exit(1)
time.sleep(8); p.kill(); p.wait()
print("強制終了した（STARTEDの8秒後）。終了コード =", p.returncode, "（Windowsでは、強制終了は 1 と出る）")
print("A1 別プロセスから state    ->", run("state", t))
print("A2 continue（続きを実行）  ->", run("continue", t, wait=0))
print("A3 resume（承認）          ->", run("resume", t))

print("=== B 承認待ちまで進めて、プロセスが終了 ===")
t = "v0B-" + uuid.uuid4().hex[:8]
print("B1 start（承認待ちで終了） ->", run("start", t))
print("B2 別プロセスから state    ->", run("state", t))
print("B3 resume（承認）          ->", run("resume", t))

print("=== C 同じ案件に同時に2本 start ===")
t = "v0C-" + uuid.uuid4().hex[:8]
ps = [subprocess.Popen([sys.executable, W, "start", t], env=env(0), stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, encoding="utf-8") for _ in range(2)]
for i, q in enumerate(ps, 1):
    o, e = q.communicate(); print(f"C{i} ->", (o.strip().splitlines() or ["(出力なし)"])[-1] if q.returncode == 0 else "ERROR " + e.strip()[-300:])
print("C3 state ->", run("state", t))