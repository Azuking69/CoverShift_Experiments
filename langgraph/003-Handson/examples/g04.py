# 3-5

from langgraph.graph import StateGraph, START, END, MessagesState
from langchain_core.messages import HumanMessage, AIMessage


# 2) ノード作成
def talk(state: MessagesState):
    return {"messages": [AIMessage("안녕하세요")]} # 履歴に追加するメッセージを返す


# 3) グラフ作成
graph = StateGraph(MessagesState)
graph.add_node("talk", talk)


# 4) グラフのつなぎ
graph.add_edge(START, "talk")
graph.add_edge("talk", END)


# 5) 実行結果の表示
out = graph.compile().invoke({"messages": [HumanMessage("안녕")]}) # 履歴に HumanMessage を追加して実行
for msg in out["messages"]:
    print(type(msg).__name__, "|", msg.content) # __name__ でクラス名を取得