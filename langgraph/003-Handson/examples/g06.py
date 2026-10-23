# 7-1

from typing import TypedDict
from langgraph.graph import StateGraph, START, END


# 1) 箱作成
class State(TypedDict):
    num: int


# 2) ノード作成
def inc(state):
    print("inc", state["num"])
    return {"num": state["num"] + 1}

def route(state):
    return "inc" if state["num"] < 3 else END


# 3) グラフ作成
builder = StateGraph(State)
builder.add_node("inc", inc)
builder.add_node("route", route)

# 4) グラフの矢印
builder.add_edge(START, "inc")
builder.add_conditional_edges("inc", route, {"inc": "inc", END: END})

# 5) グラフの実行
graph = builder.compile()
result = graph.invoke({"num": 0})
print(result)