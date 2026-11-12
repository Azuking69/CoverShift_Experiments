# 9-1

from typing import TypedDict
from langgraph.graph import StateGraph, START, END


# 1) 箱作成
class Sub(TypedDict):
    text: str

# 2) ノード作成
def up(state):
    return {"text": state["text"].upper()}

# 3) グラフ作成
sub = StateGraph(Sub)
sub.add_node("up", up)

# 4) グラフの矢印
sub.add_edge(START, "up")
sub.add_edge("up", END)

# 5) グラフの実行
sub_graph = sub.compile() # sub_graphをコンパイルして、StateGraphのインスタンスを作成する。


# 1) 箱作成
class Parent(TypedDict):
    text: str
    done: bool

# 2) ノード作成
def finish(state):
    return {"done": True}


# 3) グラフ作成
builder = StateGraph(Parent)
builder.add_node("sub", sub_graph) # sub_graphをノードとして追加する。
builder.add_node("finish", finish)


# 4) グラフの矢印
builder.add_edge(START, "sub")
builder.add_edge("sub", "finish")
builder.add_edge("finish", END)


# 5) グラフの実行
graph = builder.compile()
result = graph.invoke({"text": "hello", "done": False})
print(result)