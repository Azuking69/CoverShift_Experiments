# V1：LangGraph Agent Server
- `entry.py` … `core/graph.py` のグラフを、Agent Serverに渡す入口（保存先は、サーバーが差し込む）。
- `langgraph.json` … サーバーの設定。
- `tests/e1_e3_e4.py` … E1・E3・E4。`tests/e2_before_kill.py` → サーバーを `kill -9` → 再起動 → `tests/e2_after_restart.py` … E2。
- 実行手順は、ルートの README を見る。
