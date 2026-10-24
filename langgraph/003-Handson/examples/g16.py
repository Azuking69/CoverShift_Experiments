# 11-2

from typing import TypedDict
from langgraph.graph import StateGraph, START, END
from langgraph.types import interrupt, Command
from langgraph.checkpoint.memory import MemorySaver


# 1) 箱作成
class State(TypedDict):
    log: list
    answer: str


# 2) ノード作成
def before(state):
    print("[before]")
    return {"log": ["before"]}

def ask(state):
    print("[ask 시동]")
    answer = interrupt({"question": "어떡해?"})               # ここでユーザーに質問を投げる ＝ 止まる
    print("[ask 재시동]")                                     # ここでユーザーの回答を受け取る = 再開
    return {"answer": answer, "log": state["log"] + ["ask"]} # ここで返す値は、次のノードに渡される

def after(state):
    print("[after]")
    return {"log": state["log"] + ["after"]}


# 3) グラフ作成
builder = StateGraph(State)
builder.add_node("before", before)
builder.add_node("ask", ask)
builder.add_node("after", after)


# 4) グラフの接続
builder.add_edge(START, "before")
builder.add_edge("before", "ask") 
builder.add_edge("ask", "after")
builder.add_edge("after", END)


# 5) グラフの実行
graph = builder.compile(checkpointer=MemorySaver())

from langchain_core.runnables import RunnableConfig 
config: RunnableConfig = { # この辞書は RunnableConfig の形です、というメモ
    "configurable":{
        "thread_id": "x"
    }
}

result = graph.invoke({
    "log": [],
    "answer": ""
    }, config
)

print("첫번째: ", result)
print("멈추는 곳: ", graph.get_state(config).next)

reslut = graph.invoke(Command(resume="인증"), config)
print("두번째: ", reslut)
