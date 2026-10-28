# 8-1

import operator
from typing import TypedDict, Annotated
from langgraph.graph import StateGraph, START, END


# 1) 箱作成
class State(TypedDict):
    results: Annotated[list, operator.add] # 型ヒントにアノテーションを追加


# 2) ノード作成
def a(state):
    print("a")
    return {"results": ["A"]}

def b(state):
    print("b")
    return {"results": ["B"]}

def join(state):
    print("join: 받았다 =", state["results"])
    return {}


# 3) グラフ作成
builder = StateGraph(State)
builder.add_node("a", a)
builder.add_node("b", b)
builder.add_node("join", join)


# 4) グラフの矢印
builder.add_edge(START, "a") # 2つに分岐する
builder.add_edge(START, "b")
builder.add_edge("a", "join") # 分岐からの矢印を結合する
builder.add_edge("b", "join")
builder.add_edge("join", END)


# 5) グラフの実行
graph = builder.compile()
result = graph.invoke({"results": []})
print(result)