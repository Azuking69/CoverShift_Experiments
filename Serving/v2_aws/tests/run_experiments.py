"""E1・E3・E4 を、手元(http://localhost:8080)またはデプロイ済みRuntime(boto3)に対して流す。
手元:   python tests/run_experiments.py local
AWS:    python tests/run_experiments.py aws <agentRuntimeArn>   （AWS認証が必要。承認待ちの再開を含む）
"""
import json, sys, threading, uuid, urllib.request

MODE = sys.argv[1] if len(sys.argv) > 1 else "local"
ARN = sys.argv[2] if len(sys.argv) > 2 else None

def call(payload: dict, session: str | None = None) -> dict:
    if MODE == "local":
        req = urllib.request.Request("http://localhost:8080/invocations", json.dumps(payload).encode(),
                                     {"Content-Type": "application/json"})
        return json.loads(urllib.request.urlopen(req, timeout=120).read())
    import boto3
    c = boto3.client("bedrock-agentcore", region_name="ap-northeast-1")
    # runtimeSessionId は長さの制約があるため、十分長いIDを使う（要確認）
    r = c.invoke_agent_runtime(agentRuntimeArn=ARN, runtimeSessionId=(session or payload["thread_id"]).ljust(33, "0"),
                               payload=json.dumps(payload).encode())
    body = r["response"].read() if hasattr(r["response"], "read") else r["response"]
    return json.loads(body)

# E1: 承認待ち→再開、却下
t = "e1-" + uuid.uuid4().hex
print("[E1] start  ->", call({"action": "start", "thread_id": t}))
print("[E1] resume ->", call({"action": "resume", "thread_id": t, "approved": True}))
t = "e1r-" + uuid.uuid4().hex
call({"action": "start", "thread_id": t})
print("[E1] reject ->", call({"action": "resume", "thread_id": t, "approved": False}))

# E3: 同じthreadに同時に2本
t = "e3-" + uuid.uuid4().hex
out = []
def go(): 
    try: out.append(call({"action": "start", "thread_id": t}))
    except Exception as e: out.append({"error": type(e).__name__ + ": " + str(e)[:150]})
ths = [threading.Thread(target=go) for _ in range(2)]
[x.start() for x in ths]; [x.join() for x in ths]
print("[E3] 2本同時 ->", out)
print("[E3] 最終 state ->", call({"action": "state", "thread_id": t}))
print("outbound.log を tests/check_outbound.py で確認すること（E4）")
