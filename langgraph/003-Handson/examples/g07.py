# 7-3

from typing import TypedDict
from langgraph.graph import StateGraph, START, END


# 1) 箱作成
class State(TypedDict):
    draft: str
    ok: bool
    retry_count: int


# 2) ノード作成
def make(state):
    ...
    return {"draft": ..., "retry_count": state["retry_count"] + 1}

def check(state):
    ...
    return {"ok": ...}

def route(state):
    if state["ok"]:
        return END
    if state["retry_count"] >= 3:
        return "give up"
    return "make"


# 3) グラフ作成
builder = StateGraph(State)
builder.add_node("make", make)
builder.add_node("check", check)
builder.add_node("route", route)


# 4) グラフの矢印
builder.add_edge(START, "make")
builder.add_edge("make", "check")
builder.add_conditional_edges("check", route, {"make": "make", END: END})


# 5) グラフの実行
graph = builder.compile()
result = graph.invoke({"draft": "", "ok": False, "retry_count": 0})
print(result)