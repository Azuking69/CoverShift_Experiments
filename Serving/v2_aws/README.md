# V2：AWS AgentCore
- `app.py` … `BedrockAgentCoreApp` の入口。payload：`{"action":"start|resume|state","thread_id":"…"}`。保存先は環境変数 `AGENTCORE_MEMORY_ID` があれば AgentCore Memory、なければ仮の保存先。
- `tests/run_experiments.py` … E1・E3・E4（`local` または `aws <agentRuntimeArn>`）。
- AWS上の動作は未確認。実行手順は、ルートの README を見る。
