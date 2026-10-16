"""AgentCore Runtime 用のエントリポイント。
受け取る payload:
  {"action": "start",  "thread_id": "...", "store_id": "S1"}
  {"action": "resume", "thread_id": "...", "approved": true}
  {"action": "state",  "thread_id": "..."}
保存先: 環境変数 AGENTCORE_MEMORY_ID があれば AgentCore Memory(AgentCoreMemorySaver)。
        なければ InMemorySaver（手元の動作確認用。E2の答えにはならない）。
"""
import os
from bedrock_agentcore.runtime import BedrockAgentCoreApp
from langgraph.types import Command
import os as _os, sys as _sys
_sys.path.insert(0, _os.path.abspath(_os.path.join(_os.path.dirname(__file__), "..")))
from core.graph import build_graph

MEMORY_ID = os.getenv("AGENTCORE_MEMORY_ID")
ACTOR_ID = os.getenv("AGENTCORE_ACTOR_ID", "covershift-exp")

if MEMORY_ID:
    from langgraph_checkpoint_aws import AgentCoreMemorySaver
    saver = AgentCoreMemorySaver(MEMORY_ID, region_name=os.getenv("AWS_REGION", "ap-southeast-2"))
    BACKEND = "agentcore-memory"
else:
    from langgraph.checkpoint.memory import InMemorySaver
    saver = InMemorySaver()
    BACKEND = "in-memory(local)"

graph = build_graph(saver)
app = BedrockAgentCoreApp()


def _cfg(thread_id: str) -> dict:
    # thread_id は AgentCore の session_id、actor_id は actor_id に対応する（langgraph-checkpoint-aws の README）
    return {"configurable": {"thread_id": thread_id, "actor_id": ACTOR_ID}}


def _view(thread_id: str) -> dict:
    st = graph.get_state(_cfg(thread_id))
    return {"backend": BACKEND, "thread_id": thread_id, "next": list(st.next),
            "status": st.values.get("status"), "approved": st.values.get("manager_approved"),
            "retry_count": st.values.get("retry_count"),
            "interrupted": any(t.interrupts for t in st.tasks)}


@app.entrypoint
def invoke(payload):
    action, tid = payload.get("action"), payload.get("thread_id")
    if not tid:
        return {"error": "thread_id が必要"}
    if action == "start":
        graph.invoke({"store_id": payload.get("store_id", "S1"), "retry_count": 0, "raw_input_names": {}}, _cfg(tid))
    elif action == "resume":
        graph.invoke(Command(resume=bool(payload.get("approved"))), _cfg(tid))
    elif action != "state":
        return {"error": f"不明なaction: {action}"}
    return _view(tid)


if __name__ == "__main__":
    app.run()  # 手元: http://localhost:8080/invocations
