"""V0（基準）：同じグラフ（core/graph.py）を、PostgresSaver（PostgreSQLに保存）で動かす1回きりの実行。
使い方:  python v0_postgres/worker.py <start|continue|resume|state> <thread_id>
  start    : 新しく始める（入力を渡す）
  continue : 途中で落ちたものの続きを実行する（入力なし。graph.invoke(None, ...)）
  resume   : 承認待ちを「承認」して再開する
  state    : 保存されている状態を表示する
接続先: 環境変数 V0_DSN（既定 postgresql://covershift:covershift@localhost:5434/v0）
"""
import json, os, sys
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
from langgraph.checkpoint.postgres import PostgresSaver
from langgraph.types import Command
from core.graph import build_graph

DSN = os.getenv("V0_DSN", "postgresql://covershift:covershift@localhost:5434/v0")
action, tid = sys.argv[1], sys.argv[2]

with PostgresSaver.from_conn_string(DSN) as saver:
    saver.setup()
    graph = build_graph(saver)
    cfg = {"configurable": {"thread_id": tid}}
    if action == "start":
        print("STARTED", flush=True)   # 試験用の目印：ここから先で、計算（solver）が始まる
        graph.invoke({"store_id": "S1", "retry_count": 0, "raw_input_names": {}}, cfg)
    elif action == "continue":
        graph.invoke(None, cfg)
    elif action == "resume":
        graph.invoke(Command(resume=True), cfg)
    elif action != "state":
        sys.exit("不明なaction: " + action)
    st = graph.get_state(cfg)
    print(json.dumps({"thread_id": tid, "next": list(st.next), "status": st.values.get("status"),
                      "approved": st.values.get("manager_approved"), "retry_count": st.values.get("retry_count"),
                      "interrupted": any(t.interrupts for t in st.tasks)}, ensure_ascii=False))