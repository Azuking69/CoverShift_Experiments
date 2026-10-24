# 12-2

from typing import TypedDict
from langgraph.graph import StateGraph, START, END


# 1) 箱作成
class State(TypedDict):
    num: int


# 2) グラフ作成
def increment(state):
    return {"num": state["num"] + 1}

def double(state):
    return {"num": state["num"] * 2}


# 3) グラフ定義
builder = StateGraph(State)
builder.add_node("increment", increment)
builder.add_node("double", double)


# 4) グラフ実行
builder.add_edge(START, "increment")
builder.add_edge("increment", "double")
builder.add_edge("double", END)


# 5) グラフ実行
graph = builder.compile()

# chunkは状態の更新を表す辞書
# stream_mode="updates"を指定することで、状態の更新が発生する度にchunkが返される
for chunk in graph.stream({"num": 1}, stream_mode="updates"): 
    print(chunk)