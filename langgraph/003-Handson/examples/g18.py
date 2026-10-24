# 12-2 ~ 3

from typing import TypedDict
from langgraph.graph import StateGraph, START, END
from langgraph.config import get_stream_writer


# 1) 箱作成
class State(TypedDict):
    num: int


# 2) グラフ作成
def increment(state):
    return {"num": state["num"] + 1}

def double(state):
    return {"num": state["num"] * 2}

def add(state):
    write = get_stream_writer()
    write({"progress": "계산중..."}) # 好きな内容を外に書き出す
    return {"num": state["num"] + 1}

# 3) グラフ定義
builder = StateGraph(State)
builder.add_node("increment", increment)
builder.add_node("double", double)
builder.add_node("add", add)


# 4) グラフ実行
builder.add_edge(START, "increment")
builder.add_edge("increment", "double")
builder.add_edge("double", "add")
builder.add_edge("add", END)


# 5) グラフ実行
graph = builder.compile()

# chunkは状態の更新を表す辞書
# stream_mode="updates"、"custom"を指定することで、状態の更新が発生する度にchunkが返される
for chunk in graph.stream({"num": 1}, stream_mode=["updates", "custom"]): 
    print(chunk)