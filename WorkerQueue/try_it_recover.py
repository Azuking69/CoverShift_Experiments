"""落ちたときと、止まっていたときの確認。自分でワーカーとスケジューラーを起動・停止する。

【先にやること】
  ・ワーカーとスケジューラーのターミナルは、Ctrl+C で止めておく（このスクリプトが自分で起動する）
  ・api（uvicorn）と PostgreSQL は、動かしたままにする
実行:  python try_it_recover.py
"""
import json
import os
import subprocess
import sys
import time
import urllib.request

BASE = "http://localhost:8000"
HERE = os.path.dirname(os.path.abspath(__file__))
procs = []


def call(method, path, body=None):
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(BASE + path, data=data, method=method,
                                 headers={"Content-Type": "application/json"})
    # urlopen(): HTTPリクエストを送信し、レスポンスを取得する。JSONレスポンスを辞書に変換して返す。
    with urllib.request.urlopen(req) as r:
        # loads(): JSON文字列をPythonの辞書に変換する。r.read() はバイト列なので、decode() で文字列に変換する。
        return json.loads(r.read())


def start(script, **env):
    p = subprocess.Popen([sys.executable, script], cwd=HERE, env={**os.environ, **env},
                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    procs.append(p)
    return p


def kill_tree(p):
    """Windows では .venv の python が「親」と「本物の子」の2段になる。子まで確実に止める。"""
    if os.name == "nt":
        subprocess.run(["taskkill", "/F", "/T", "/PID", str(p.pid)],
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    else:
        # kill(): プロセスにシグナルを送る。SIGTERM は「終了要求」。子プロセスも止める。
        p.kill()


# 待つ。cond が True になるまで待つ。timeout 秒でタイムアウト。
def wait(cond, timeout):
    t = time.time()
    while time.time() - t < timeout:
        if cond():
            return time.time() - t
        time.sleep(0.5)
    return None


# 指定した条件が True なら OK、False なら NG と表示する。
def check(label, ok):
    print(("  OK  " if ok else "  NG  ") + label)


# 代替ワーカーが仕事を取り直すのを待つ。timeout 秒でタイムアウト。
try:
    print("⑤ 処理中にワーカーが落ちたら、別のワーカーがやり直す")
    c = call("POST", "/cases", {"name": "落ちるテスト"})["id"]
    w1 = start("worker.py", WORKER_NAME="worker-落ちる", WORK_SECONDS="8", STUCK_SECONDS="5")
    time.sleep(1)
    call("POST", f"/cases/{c}/events", {"event": "deadline"})
    got = wait(lambda: any(r["case_id"] == c and r["status"] == "processing" for r in call("GET", "/queue")), 10)
    check("ワーカーが仕事を取った（status='processing'）", got is not None)
    first_lock = [r for r in call("GET", "/queue") if r["case_id"] == c][0]["locked_at"]  # 最初に取られた時刻
    kill_tree(w1)  # 処理の途中で、いきなり落とす（子プロセスまで）
    print("      …ワーカーを強制終了した")
    time.sleep(1)
    print("      …別のワーカーを起動（5秒たっても処理中のままの仕事を、待ちに戻して取り直す）")
    start("worker.py", WORKER_NAME="worker-引き継ぐ", WORK_SECONDS="1", STUCK_SECONDS="5")
    t = wait(lambda: call("GET", f"/cases/{c}")["state"] == "reviewing", 40)
    check("やり直されて 'reviewing' になった" + (f"（{t:.0f}秒後）" if t else ""), t is not None)
    job = [r for r in call("GET", "/queue") if r["case_id"] == c][0]
    check("仕事は『取り直された』（取った時刻が変わった＝落ちたワーカーが自分で終わらせたのではない）",
          job["locked_at"] != first_lock)

    print("⑥ スケジューラーが止まっている間に過ぎた締切は、再開後に出る")
    c2 = call("POST", "/cases", {"name": "遅れるテスト"})["id"]
    call("POST", f"/cases/{c2}/deadline", {"seconds": 2})
    time.sleep(6)
    stopped = call("GET", f"/cases/{c2}")["state"] == "collecting"
    check("スケジューラー停止中は 'collecting' のまま（締切は過ぎている）", stopped)
    
    # start(): スケジューラーを起動する。wait(): 指定した条件が True になるまで待つ。timeout 秒でタイムアウト。
    if not stopped:
        print("      ※ 別のスケジューラーが動いています。止めてからやり直してください")
    start("scheduler.py")
    t = wait(lambda: call("GET", f"/cases/{c2}")["state"] == "reviewing", 30)
    check("スケジューラーを起動したら 'reviewing' になった" + (f"（{t:.0f}秒後）" if t else ""), t is not None)

# kill_tree(): ワーカーとスケジューラーを止める。Windows では子プロセスまで確実に止める。
finally:
    for p in procs:
        kill_tree(p)
    print("（このスクリプトが起動したワーカーとスケジューラーは、終了しました）")
