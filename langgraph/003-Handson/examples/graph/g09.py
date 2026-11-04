# 8-4

import operator
from typing import TypedDict, Annotated
from langgraph.graph import StateGraph, START, END
from langgraph.types import Send


# 1) 箱作成
class Over(TypedDict):
    staff: list
    replies: Annotated[list, operator.add] # 型ヒントにアノテーションを追加

class One(TypedDict):
    person: str


# 2) ノード作成
def fan_out(state):
    return {}

def dispatch(state):
    return [Send("ask", {"person": person})
            for person in state["staff"]]

def ask(state: One):
    return {"replies": [f"{state['person']}:가능"]}

def collect(state):
    print("collect", state["replies"])
    return {}


# 3) グラフ作成
builder = StateGraph(Over)
builder.add_node("fan_out", fan_out)
builder.add_node("ask", ask)
builder.add_node("collect", collect)


# 4) グラフの矢印
builder.add_edge(START, "fan_out")
builder.add_conditional_edges("fan_out", dispatch, ["ask"]) # fan_outの出力に応じてaskを複数回呼び出す。
                                                            # dispatchの返り値はSendのリストであり、
                                                            # 各Sendはaskノードを呼び出すための情報を持つ。
builder.add_edge("ask", "collect")
builder.add_edge("collect", END)


# 5) グラフの実行
graph = builder.compile()
result = graph.invoke({"staff": ["A", "B", "C", "D", "E"], "replies": []})
print(result)