# 10-5

from typing import TypedDict
from langgraph.graph import StateGraph, START, END
from langgraph.checkpoint.memory import MemorySaver


# 1) 箱作成
class State(TypedDict):
    num: int


# 2) グラフ作成
def increment(state):
    print("[increment]")
    return {"num": state["num"] + 1}

def double(state):
    print("[double]")
    return {"num": state["num"] * 2}


# 3) グラフ定義
builder = StateGraph(State)
builder.add_node("increment", increment)
builder.add_node("double", double)


# 4) グラフの接続
builder.add_edge(START, "increment")
builder.add_edge("increment", "double")
builder.add_edge("double", END)


# 5) グラフの実行
graph = builder.compile(checkpointer=MemorySaver())
configuration = {
    "configurable": {
        "thread_id": "tt"
    }
}
print(graph.invoke({"num": 1}, configuration))          # -> {'num': 4}, (1 + 1 = 2, 2 * 2 = 4)

history = list(graph.get_state_history(configuration))  # -> 状態遷移の履歴を取得
past = [h for h in history if h.next == ("double",)][0] # incrementが終わった後の状態を取得
print(graph.invoke(None, past.config))                  # -> その時点の状態からdoubleを実行するので{'num': 4}が返る

fork = graph.update_state(past.config, {"num": 100})    # stateを書き換えて分かれる
print(graph.invoke(None, fork))                         # 枝分かれ先を実行するので{'num': 200}が返る