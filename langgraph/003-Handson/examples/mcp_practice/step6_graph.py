import asyncio
from typing import TypedDict
from langgraph.graph import StateGraph, START, END
from mcp_call import call_mcp_tool


# 1) スタッフのデータの型を定義する
class State(TypedDict):
    llm_all_staff: list



# 2) グラフを作成する
async def collect(state: State):
    data = await call_mcp_tool("step4b_server.py", "get_staff_availablility")
    return {"llm_all_staff": data["staff"]}


# 3) グラフの定義
builder = StateGraph(State)
builder.add_node("collect", collect)


# 4) グラフの連結
builder.add_edge(START, "collect")
builder.add_edge("collect", END)


# 5) グラフの実行
graph = builder.compile()
if __name__ == "__main__":
    out = asyncio.run(graph.ainvoke({"llm_all_staff": []}))
    print("人数: ", len(out["llm_all_staff"]))
