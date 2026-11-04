from typing import TypedDict 
from langgraph.graph import StateGraph, START, END


# 1) state 型の定義
class State(TypedDict): # TypedDict: 決まった項目だけを持つ辞書
    name: str
    greeting: str


# 2) Node 関数の定義
def make_greeting(state:State) -> dict:
    # 変えたいところだけを返す
    print("[make_greeting] name =", state["name"])
    return {"greeting": "안녕하세요, " + state["name"]}

def add_mark(state: State) -> dict:
    # 変えたいところだけを返す
    print("[add_mark] greeting = ", state["greeting"])
    return {"greeting": state["greeting"] + "님!"}


# 3) グラフの設計
builder = StateGraph(State) # Stateというグラフの箱を用意する
# 関数をノードとして追加
builder.add_node("make_greeting", make_greeting) 
builder.add_node("add_mark", add_mark)

# 4) 関数(ノード)同士のつながりを定義
builder.add_edge(START, "make_greeting") # START -> make_greeting
builder.add_edge("make_greeting", "add_mark") # make_greeting -> add_mark
builder.add_edge("add_mark", END) # add_mark -> END


#  5) グラフを検査して使える状態にする
graph = builder.compile() # graph という変数にグラフを入れる
result = graph.invoke({"name": "홍길동", "greeting": ""}) # graph.invoke() でグラフを実行する。{}の中に初期状態を入れる
print(result) # 最終状態を表示