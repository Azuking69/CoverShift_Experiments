# 10-6

import os
from typing import TypedDict
from langgraph.graph import StateGraph, START, END
from langgraph.checkpoint.sqlite import SqliteSaver # SQLite: データベース


# 1) 箱作成
class State(TypedDict):
    num: int


# 2) ノード作成
def increment(state):
    return {"num": state["num"] + 1}


# 3) グラフ作成
builder = StateGraph(State)
builder.add_node("increment", increment)


# 4) グラフの接続
builder.add_edge(START, "increment")
builder.add_edge("increment", END)

if os.path.exists("checkpoint.db"):    # 既にファイルがある場合
    os.remove("checkpoint.db")         # 毎回初期化


# 5) グラフ実行
# from_conn_string: SQLiteの接続文字列からSaverを作成する
with SqliteSaver.from_conn_string("checkpoint.db") as saver:   # サーバーを立てる
    graph1 = builder.compile(checkpointer=saver)
    # keep: スレッドIDを保持することで、同じスレッドで実行される
    graph1.invoke({"num": 5}, {"configurable": {"thread_id": "keep"}})

with SqliteSaver.from_conn_string("checkpoint.db") as saver:   # サーバー再起動
    graph2 = builder.compile(checkpointer=saver)
    # invokeを使わず、get_stateで状態を取得する
    print(graph2.get_state({"configurable": {"thread_id": "keep"}}).values)