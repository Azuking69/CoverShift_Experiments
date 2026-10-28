# 13-2

from typing import TypedDict
from langchain_core.tools import tool
from langgraph.graph import StateGraph, START, END


# 1) 箱作成
class State(TypedDict):
    store_id: str
    result: str


# 2) ノード作成
@tool # tool: 
def get_staff_count(store_id: str) -> str:
    """store_idに対応する店舗のスタッフ数を返すツール"""
    return f"가게 {store_id}에는 10명의 직원이 있습니다."

def count(state):
    return {"result": get_staff_count.invoke({"store_id": state["store_id"]})}  # get_staff_countを呼び出す


# 3) グラフ定義
builder = StateGraph(State)
builder.add_node("count", count)


# 4) グラフ連結
builder.add_edge(START, "count")
builder.add_edge("count", END)


# 5) グラフ実行
graph = builder.compile()
result = graph.invoke({"store_id": "s1"})  # store_idに「s1」を指定してグラフを実行
print(result)  # {'store_id': 's1', 'result': '가게 s1에는 10명의 직원이 있습니다.'}