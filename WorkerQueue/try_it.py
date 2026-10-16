"""動作確認スクリプト。api / scheduler / worker を起動してから実行する。

  python try_it.py          …… ①基本の流れ と ②順番 を確かめる
標準ライブラリだけで動く（追加のインストール不要）。
"""
import json
import time
import urllib.request

BASE = "http://localhost:8000"


def call(method, path, body=None):
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(BASE + path, data=data, method=method,
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req) as r:
        return json.loads(r.read())


def wait_state(case_id, want, timeout=40):
    end = time.time() + timeout
    while time.time() < end:
        if call("GET", f"/cases/{case_id}")["state"] == want:
            return True
        time.sleep(1)
    return False


def check(label, ok):
    print(("  OK  " if ok else "  NG  ") + label)


print("① 基本の流れ：締切 → 検討 → 承認待ち → 終了")
c = call("POST", "/cases", {"name": "10月 第2週シフト"})["id"]
call("POST", f"/cases/{c}/deadline", {"seconds": 3})
check("締切の3秒後に、スケジューラー→キュー→ワーカーを通って 'reviewing' になる", wait_state(c, "reviewing"))
call("POST", f"/cases/{c}/events", {"event": "review_done"})
check("review_done で 'waiting_approval' になる", wait_state(c, "waiting_approval"))
call("POST", f"/cases/{c}/events", {"event": "approved"})
check("approved で 'finished' になる", wait_state(c, "finished"))

print("② 順番：3つの合図をまとめて入れても、入れた順に処理される")
print("   （ワーカーを2つ以上動かしていても、順番が崩れなければ 'finished' になる）")
c2 = call("POST", "/cases", {"name": "順番テスト"})["id"]
for ev in ["deadline", "review_done", "approved"]:
    call("POST", f"/cases/{c2}/events", {"event": ev})
check("最終的に 'finished' になる", wait_state(c2, "finished", timeout=60))

print("③ 二重：同じ合図が2回届いても、2回目は無視される（ワーカーのログを見る）")
c3 = call("POST", "/cases", {"name": "二重テスト"})["id"]
for ev in ["deadline", "deadline"]:
    call("POST", f"/cases/{c3}/events", {"event": ev})
check("状態は 'reviewing' のまま（2回目で進みすぎない）", wait_state(c3, "reviewing") and (time.sleep(8) or
      call("GET", f"/cases/{c3}")["state"] == "reviewing"))
