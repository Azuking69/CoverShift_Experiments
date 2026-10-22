from typing import TypedDict, Annotated


# 1) state 型の定義
class State(TypedDict):
    name: str    # 文字列
    count: int   # 整数
    items: list  # リスト


# 2) 関数（ノード）の定義
def n1(state):
    return {"a": "A1"}

def n2(state):
    return {"items": state["items"] + ["x"]}

