# 11-6

from typing import TypedDict
from langgraph.graph import StateGraph, START, END
from langgraph.types import interrupt, Command
from langgraph.checkpoint.memory import MemorySaver


# 1) 箱作成
class State(TypedDict):
    draft: str
    version: int
    rejects: int
    status: str


# 2) ノード作成
def make(state):
    v = state["version"] + 1
    print(f"[make] 안 v{v}")
    return {"draft": f"안v{v}", "version": v}

def review(state) -> Command:
    decision = interrupt({
        "draft": state["draft"], 
        "ask": "인증(True)/각하(False)"
    })

    # decisionがTrueならfinishへ
    if decision:
        return Command(goto="finish")
    # decisionがFalseならrejectsを1増やしてgive up
    if state["rejects"] + 1 >= 2:
        return Command(
            goto="give up",
            update={"rejects": state["rejects"] + 1}
        )
    # それ以外はmakeへ
    return Command(
        goto="make",
        update={"rejects": state["rejects"] + 1}
    )

def finish(state):
    print("[finish] 확정: ", state["draft"])
    return {"status": "확정"}

def give_up(state):
    print("[give up] 포기: ", state["draft"])
    return {"status": "포기"}


# 3) グラフ作成
builder = StateGraph(State)
builder.add_node("make", make)
builder.add_node("review", review)
builder.add_node("finish", finish)
builder.add_node("give up", give_up)


# 4) グラフ接続
builder.add_edge(START, "make")
builder.add_edge("make", "review")
builder.add_edge("finish", END)
builder.add_edge("give up", END)


# 5) グラフ実行
graph = builder.compile(checkpointer=MemorySaver())

from langchain_core.runnables import RunnableConfig
config: RunnableConfig = {
    "configurable": {
        "thread_id": "x"
    }}
result = graph.invoke({
    "draft": "",
    "version": 0,
    "rejects": 0,
    "status": ""
}, config)
print("기다리기: ", result["__interrupt__"][0].value) 

result = graph.invoke(Command(resume=False), config) # 却下 -> makeへ
print("기다리기: ", result["__interrupt__"][0].value)  

result = graph.invoke(Command(resume=True), config)   # 承認 → 確定
