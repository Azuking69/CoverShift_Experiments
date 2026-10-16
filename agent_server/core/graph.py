"""v6_gen の main_graph.py の流れ（LangGraph本体）。AgentServer・AgentCore の両方がこれを使う。サービス固有のコードは入れない。
solver(本物のCP-SAT) → explain(仮名化→Claude→復元) → manager_review(interrupt) → finalize
Claude呼び出しは core/llm.py（鍵があれば本物、なければ偽物）。送る直前の本文を outbound.log に追記する（E4用）。
"""
import json, os, time
from typing import Any, Dict, Optional, TypedDict
from langgraph.graph import StateGraph, END
from langgraph.types import interrupt

from .fixtures import STAFF, REQUIREMENTS, WEIGHTS
from .solver import solve_shift
from .llm import call_claude

MAX_REJECTS = 2
SLEEP = float(os.getenv("SOLVER_EXTRA_WAIT_SEC", "0"))

class State(TypedDict, total=False):
    store_id: str
    status: str
    draft_shift: Optional[Any]
    llm_explanation: Optional[str]
    manager_approved: Optional[bool]
    raw_input_names: Dict[str, str]
    retry_count: int

def pseudonym(i: int) -> str:
    return "スタッフ" + chr(ord("A") + i)

def node_solver(state: State) -> dict:
    # 仮名化：名前はここで記号に置き換え、ソルバーにも渡さない。対応表(記号→実名)は状態に持つ（AIの外）。
    mapping, staff = {}, []
    for i, st in enumerate(STAFF):
        p = pseudonym(i)
        mapping[p] = st["name"]
        staff.append({"id": st["id"], "name": p, "unpreferred_days": st["unpreferred_days"]})
    if SLEEP: time.sleep(SLEEP)   # 試験用の人工的な待ち（E2：計算中に落とす用）。本物のソルバーの時間とは別
    result = solve_shift(staff, REQUIREMENTS, WEIGHTS)   # 本物のCP-SAT
    if result["status"] != "SUCCESS":
        return {"status": "S1_生成失敗", "draft_shift": result.get("reason"), "raw_input_names": mapping}
    lines = [f"{d['day']}日目 " + " / ".join(f"{k}:{','.join(v)}" for k, v in d["assignments"].items())
             for d in result["schedule"]]
    return {"status": "S1_生成完了", "draft_shift": "\n".join(lines), "raw_input_names": mapping}

def node_explain(state: State) -> dict:
    prompt = "次のシフト案を説明して: " + str(state.get("draft_shift"))  # 実名は送らない
    text = call_claude(prompt)
    for pseudo, real in state.get("raw_input_names", {}).items():
        text = text.replace(pseudo, real)  # 復元はAIの外（コード）
    return {"status": "S4_説明生成完了", "llm_explanation": text}

def node_manager_review(state: State) -> dict:
    # 注意: 再開のとき、このノードは最初から実行し直される。interrupt()より前に副作用を書かない。
    approved = interrupt({"message": "シフト案とAI解説を確認し、承認してください。",
                          "draft": state.get("draft_shift"),
                          "explanation": state.get("llm_explanation")})
    retry = state.get("retry_count", 0) + (0 if approved else 1)
    return {"manager_approved": bool(approved), "status": "S5_確認完了", "retry_count": retry}

def node_finalize(state: State) -> dict:
    return {"status": "S6_確定済み"}

def route(state: State) -> str:
    if state.get("manager_approved"): return "finalize"
    if state.get("retry_count", 0) >= MAX_REJECTS: return "give_up"
    return "solver"

def build_graph(checkpointer=None):
    b = StateGraph(State)
    b.add_node("solver", node_solver); b.add_node("explain", node_explain)
    b.add_node("manager_review", node_manager_review); b.add_node("finalize", node_finalize)
    b.set_entry_point("solver"); b.add_edge("solver", "explain"); b.add_edge("explain", "manager_review")
    b.add_conditional_edges("manager_review", route, {"finalize": "finalize", "solver": "solver", "give_up": END})
    b.add_edge("finalize", END)
    return b.compile(checkpointer=checkpointer)
