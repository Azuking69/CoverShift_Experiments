# 10

from typing import TypedDict
from langgraph.graph import StateGraph, START, END
from langgraph.checkpoint.memory import MemorySaver


# 1) 箱作成
class State(TypedDict):
    n: int


# 2) ノード作成
def inc(state):
    print("inc", state["n"])
    return {"n": state["n"] + 1}
    


# 3) グラフ作成
builder = StateGraph(State)
builder.add_node("inc", inc)


# 4) グラフの矢印
builder.add_edge(START, "inc")
builder.add_edge("inc", END)


# 5) グラフの実行
graph = builder.compile(checkpointer = MemorySaver())

t1 = {"configurable": {"thread_id": "t1"}}
t2 = {"configurable": {"thread_id": "t2"}}

graph.invoke({"n": 0}, t1)
graph.invoke({"n": 10}, t2)