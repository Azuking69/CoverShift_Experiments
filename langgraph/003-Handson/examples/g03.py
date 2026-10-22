# 3-4

import operator
from typing import TypedDict, Annotated
from langgraph.graph import StateGraph, START, END


# 1) state 型の定義
class State(TypedDict):
    # リデューサー：返した値を結合する
    log: Annotated[list, operator.add] # log はリストで、operator.add で返した値を結合することを示す
    count: int   # 上書き


# 2) 関数（ノード）の定義
def n1(state):
    return {"log": ["n1 실행"], "count": 1}

def n2(state):
    return {"log": ["n2 실행"], "count": 2}


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
result = graph.invoke({"log": ["시작"], "count": 0})
print(result)