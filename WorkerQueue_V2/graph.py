"""graph：1件の案件の流れを、LangGraph のグラフとして書いたもの（V2で states.py の代わり）。

    step_a（計算） → step_b（検証） → wait_approval（人の承認待ち） → finish（確定）

・各ステップが終わるたびに、LangGraph が「ここまで終わった」を PostgreSQL に保存する（checkpoint）
・wait_approval で interrupt() を呼ぶと、そこで止まる。ワーカーは手を離し、何も握らない
・あとで Command(resume=...) を渡すと、止まった場所から続きが動く
・step_a / step_b は、重い処理のまね（time.sleep）。始まるたびに node_runs へ1行書く
"""
import os
import time
from typing_extensions import TypedDict
from langgraph.graph import StateGraph, START, END
from langgraph.types import interrupt
from common import connect, log

WORK_SECONDS = float(os.getenv("WORK_SECONDS", "2"))  # 1ステップの処理時間（CP-SAT や LLM の待ち時間のまね）
WORKER_NAME = os.getenv("WORKER_NAME", f"worker-{os.getpid()}")


class CaseState(TypedDict):
    case_id: int
    a_done: bool
    b_done: bool
    approved: bool


def _set_state(case_id: int, state: str):
    with connect() as conn:
        conn.execute("UPDATE cases SET state = %s, updated_at = now() WHERE id = %s", (state, case_id))


def _work(case_id: int, node: str):
    with connect() as conn:
        conn.execute("INSERT INTO node_runs(case_id, node, worker) VALUES (%s, %s, %s)", (case_id, node, WORKER_NAME))
    log(WORKER_NAME, f"案件{case_id}: {node} 開始（約{WORK_SECONDS}秒）")
    time.sleep(WORK_SECONDS)


def step_a(s: CaseState):
    _set_state(s["case_id"], "reviewing")
    _work(s["case_id"], "step_a")
    return {"a_done": True}


def step_b(s: CaseState):
    _work(s["case_id"], "step_b")
    return {"b_done": True}


def wait_approval(s: CaseState):
    _set_state(s["case_id"], "waiting_approval")
    ok = interrupt("承認待ち")  # ← ここで止まる。再開すると、この行から ok に値が入って続く
    return {"approved": bool(ok)}


def finish(s: CaseState):
    _set_state(s["case_id"], "finished")
    return {}


def build(checkpointer):
    g = StateGraph(CaseState)
    g.add_node("step_a", step_a)
    g.add_node("step_b", step_b)
    g.add_node("wait_approval", wait_approval)
    g.add_node("finish", finish)
    g.add_edge(START, "step_a")
    g.add_edge("step_a", "step_b")
    g.add_edge("step_b", "wait_approval")
    g.add_edge("wait_approval", "finish")
    g.add_edge("finish", END)
    return g.compile(checkpointer=checkpointer)
