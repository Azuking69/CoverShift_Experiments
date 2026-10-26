# 14-2

import os
from typing import TypedDict
from langgraph.graph import StateGraph, START, END
from langgraph.checkpoint.postgres import PostgresSaver
from dotenv import load_dotenv

load_dotenv()                 # 環境変数をロードする
DB_URL = os.environ["DB_URL"] # DBの接続URL


# 1) 箱作成
class State(TypedDict):
    num: int                  # ここに状態を定義する


# 2) ノード作成
def add(state):
    return {"num": state.get("num", 0) + 1} # n に毎回 +1 する


# 3) グラフ作成
builder = StateGraph(State)
builder.add_node("add", add)


# 4) グラフ連結
builder.add_edge(START, "add")
builder.add_edge("add", END)


# 5) グラフ実行
with PostgresSaver.from_conn_string(DB_URL) as saver: # PostgresSaver を使って、DBに保存する
    saver.setup()                                     # 初期設定
    graph = builder.compile(checkpointer=saver)       # グラフをコンパイルして、PostgresSaver を設定する
    cfg = {"configurable": {
        "thread_id": "trd_1"                          # 名札
        }}                                            
    
    result = graph.invoke(State(num=0), cfg)          # 動かして、結果を受け取る
    print(result)
    print(len(list(graph.get_state_history(cfg))))    # 名札で、履歴の件数を数える