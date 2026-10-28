# 10-3 ~ 4

from typing import TypedDict
from langgraph.graph import StateGraph, START, END
from langgraph.checkpoint.memory import MemorySaver


# 1) 箱作成
class State(TypedDict):
    num: int


# 2) ノード作成
def inc(state):
    return {"num": state["num"] + 1} # n に毎回 +1 する


# 3) グラフ作成
builder = StateGraph(State)
builder.add_node("inc", inc)


# 4) グラフの矢印
builder.add_edge(START, "inc")
builder.add_edge("inc", END) 


# 5) グラフの実行
graph = builder.compile(checkpointer = MemorySaver())

t1 = {"configurable": {"thread_id": "t1"}} # t1 という thread_id を持つ state を作成
graph.invoke({"num": 0}, t1) # t1 という thread_id を持つ state に {"num": 0} を渡して実行。オートセーブ

print(graph.get_state(t1).values) # 一番新しい state の値
print(graph.get_state(t1).next)   # 次に実行するノードの名前
print("이력 수:", len(list(graph.get_state_history(t1))))

for state in graph.get_state_history(t1):
    # state.values: state の値
    # state.next: 次に実行するノードの名前
    # state.metadata: state に付随するメタデータ
    # state.metadata.get("step"): state の実行回数
    print(state.values, "next=", state.next, "step=", state.metadata.get("step"))

graph.update_state(t1, {"num": 100})
print(graph.get_state(t1).values) # 一番新しい state の値