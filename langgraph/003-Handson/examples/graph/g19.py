# 12-5

from typing import TypedDict
from langgraph.graph import StateGraph, START, END
from langgraph.types import interrupt, Command
from langgraph.checkpoint.memory import MemorySaver


# 1) 箱作成
class State(TypedDict):
    approved: bool


# 2) グラフ作成
def ask(state):
    ok = interrupt("인증합니까?")
    return {"approved": ok}


# 3) グラフ定義
builder = StateGraph(State)
builder.add_node("ask", ask)


# 4) グラフ連結
builder.add_edge(START, "ask")
builder.add_edge("ask", END)


# 5) グラフ実行
graph = builder.compile(checkpointer=MemorySaver())
graph_config = {"configurable": {"thread_id": "s1"}}                                  # 「s1 という名札のセーブデータ」を使う

for chunk in graph.stream({"approved": False}, graph_config, stream_mode="updates"):  # 承認待ちで止まる
    print(chunk)
for chunk in graph.stream(Command(resume=True), graph_config, stream_mode="updates"): # 再開
    print(chunk)