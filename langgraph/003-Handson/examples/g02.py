# 3-1 ~ 3-3

from typing import TypedDict
from langgraph.graph import StateGraph, START, END


# 1) state 型の定義
class State(TypedDict):
    name: str    # 文字列
    count: int   # 整数
    items: list  # リスト


# 2) 関数（ノード）の定義
def n1(state):
    print("[n1] 실행")
    return {"name": "Bob"}

def n2(state):
    print("[n2] 실행")
    return {"items": state["items"] + ["x"]}


# 3) グラフの構築
builder = StateGraph(State)

builder.add_node("n1", n1)
builder.add_node("n2", n2)


# 4) グラフのつなぎ
builder.add_edge(START, "n1")
builder.add_edge("n1", "n2")
builder.add_edge("n2", END)


# 5) グラフの実行
graph = builder.compile()
result = graph.invoke({"name": "Alice", "count": 0, "items": []})
print(result)