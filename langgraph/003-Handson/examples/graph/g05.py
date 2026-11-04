# 3-6

from langgraph.graph import StateGraph, START, END
from typing import TypedDict

# 1) 状態クラスの定義
class In(TypedDict):
    question: str

class Out(TypedDict):
    answer: str

class All(In, Out):
    memo: str

# 2) ノード作成
def work(state: All):
    print("[work] state keys:", list(state.keys()))
    return {"memo": "내부 메모", "answer": "답" + state["question"]} # 履歴に追加するメッセージを返す


# 3) グラフ作成
builder = StateGraph(All, input_schema=In, output_schema=Out)
builder.add_node("work", work)


# 4) グラフの矢印
builder.add_edge(START, "work")
builder.add_edge("work", END)


# 5) グラフの実行
graph = builder.compile()
result = graph.invoke({"question": "질문"})
print(result)
