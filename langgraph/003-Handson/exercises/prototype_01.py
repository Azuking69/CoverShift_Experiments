import os
from typing import TypedDict, Literal
from langchain_core.tools import tool
from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import StateGraph, START, END
from langgraph.checkpoint.postgres import PostgresSaver
from langgraph.types import Command, interrupt
from dotenv import load_dotenv


# 0) 初期設定
load_dotenv()                 # 環境変数をロードする
DB_URL = os.environ["DB_URL"] # DBの接続URL


# 1) 箱作成
class State(TypedDict):
    all_staff: list            # 全社員のリスト
    staff_id: int              # 社員ID
    staff_name: str            # 社員名
    preferred_shift: list      # 希望シフト
    staff_skill: int           # スキルレベル
    admin_rate: int            # 管理者評価
    draft_month_shift: list    # 各社員の月間シフト案
    draft_store_shift: list    # 店全体の月間シフト案
    result: str                # 検査の結果
    deficiency: str            # 不足の有無
    return_count: int          # 戻り値の数


# 2) グラフ作成
# 【コード】希望・スキル・指示を読む
def collect(state):
    print("希望シフトを収集中...")
    print("スキルを評価中...")
    return {"draft": f"{state['staff_name']}の希望シフト: {state['preferred_shift']}"}


def route_1(state) -> Literal["skill_check", "auto_draft"]:
    return "skill_check" if state["staff_skill"] != state["admin_rate"] else "auto_draft"


# 【コード】未確認を「要指導」とみなして、店長に知らせる(止まらない)
def skill_check(state):
    print("スキルチェック中...")
    if state["staff_skill"] == state["admin_rate"]:
        print(f"{state['staff_name']}のスキルが正しいです。")
        return {"draft": f"{state['staff_name']}のスキルが正しいです。"}
    else:
        print(f"{state['staff_name']}のスキルが不正です。店長に知らせます。")
        return {"draft": f"{state['staff_name']}のスキルが不正です。店長に知らせます。"}


# 【LLM】AIが編成案を作る
@tool
def auto_draft(state):
    """
    希望のシフト・スキル・管理者評価をもとに、LLMが自動で編成案を作る。
    1) アルバイト・パートの希望シフト(preferred_shift: list)を確認する
    2) 社員の希望休暇(preferred_shift: list)を確認する
    3) スキル・管理者評価をもとに、シフトの組み合わせを考える
    4) 可能な限り希望シフトを尊重しつつ、必要なスキルを確保する
    5) 編成案(draft_month_shift: list)を作成する
    """
    print("自動編成中...")
    return f"〇月のシフト: {state['draft_month_shift']}"


# 【コード】ルールを守っているか検査する
def validate(state):
    print("編成案を検査中...")

    # 【分岐】検査結果
    if validate(state):
        print("編成案は有効です。")
        return {"draft": f"{state['staff_name']}の編成案は有効です。"}
    elif not validate(state):
        print("編成案は無効です。再度編成を行います。")
        return {"draft": f"{state['staff_name']}の編成案は無効です。再度編成を行います。"}
    else:
        print("編成案の検査結果が不明です。")
        return {"draft": f"{state['staff_name']}の編成案の検査結果が不明です。再度編成を行います。"}


# 【待機】スタッフに LINE で聞いて、返事を待つ[]
def contact(state):
    print("スタッフに連絡中...")
    response = interrupt({"draft_month_shift": state["draft_month_shift"], "ask": "承認|却下"})

    # (分岐)スタッフの返事
    if response == "承認":
        print("スタッフが承認しました。")
        return {"draft": f"{state['staff_name']}の編成案は承認されました。"}
    elif response == "却下":
        print("スタッフが却下しました。再度編成を行います。")
        return {"draft": f"{state['staff_name']}の編成案は却下されました。再度編成を行います。"}


# 【待機】店長の承認を待つ
def approve(state):
    decision = interrupt({"draft_store_shift": state["draft_store_shift"], "ask": "承認(True)|却下(False)"})

# 【返信】店長の選択
def route_2(state) -> Command[Literal["finalize", "auto_draft"]]:
    next_node = "finalize" if state["decision"] == True else "auto_draft"
    return Command(goto=next_node, update={"draft_store_shift": state["draft_store_shift"] + ["承認済み"]})


# 【コード】最新データで再チェックして、確定を保存
def finalize(state):
    print("編成案を確定しました。")
    return {"draft": f"{state['staff_name']}の編成案を確定しました。"}



# 3) グラフの設計
builder = StateGraph(State)
builder.add_node("collect", collect)
builder.add_node("skill_check", skill_check)
builder.add_node("auto_draft", auto_draft)
builder.add_node("validate", validate)
builder.add_node("contact", contact)
builder.add_node("approve", approve)
builder.add_node("finalize", finalize)


# 4) グラフ連結
builder.add_edge(START, "collect")
builder.add_conditional_edges("collect", route_1, {"skill_check": "skill_check", "auto_draft": "auto_draft"})
builder.add_edge("skill_check", "auto_draft")
builder.add_edge("auto_draft", "validate")
builder.add_edge("validate", "contact")
builder.add_edge("contact", "auto_draft")
builder.add_edge("approve", "finalize")
builder.add_edge("finalize", END)


# 5) グラフ実行
with PostgresSaver.from_conn_string(DB_URL) as saver:
    saver.setup()
    graph = builder.compile(checkpointer=saver)
    thread_001 = {"configurable": {"thread_id": "thread_001"}}
    thread_002 = {"configurable": {"thread_id": "thread_002"}}
    thread_003 = {"configurable": {"thread_id": "thread_003"}}
    thread_004 = {"configurable": {"thread_id": "thread_004"}}
    thread_005 = {"configurable": {"thread_id": "thread_005"}}

    print(graph.invoke({"staff_id": 1, "staff_name": "Alice",   "preferred_shift": ["Mon", "Tue"], "staff_skill": 3, "admin_rate": 3, "draft_month_shift": [], "draft_store_shift": [], "result": "", "deficiency": "", "return_count": 0}, thread_001))
    print(graph.invoke({"staff_id": 2, "staff_name": "Bob",     "preferred_shift": ["Wed", "Thu"], "staff_skill": 3, "admin_rate": 3, "draft_month_shift": [], "draft_store_shift": [], "result": "", "deficiency": "", "return_count": 0}, thread_002))
    print(graph.invoke({"staff_id": 3, "staff_name": "Charlie", "preferred_shift": ["Fri", "Sat"], "staff_skill": 3, "admin_rate": 3, "draft_month_shift": [], "draft_store_shift": [], "result": "", "deficiency": "", "return_count": 0}, thread_003))
    print(graph.invoke({"staff_id": 4, "staff_name": "David",   "preferred_shift": ["Sun", "Mon"], "staff_skill": 3, "admin_rate": 3, "draft_month_shift": [], "draft_store_shift": [], "result": "", "deficiency": "", "return_count": 0}, thread_004))
    print(graph.invoke({"staff_id": 5, "staff_name": "Eve",     "preferred_shift": ["Tue", "Wed"], "staff_skill": 3, "admin_rate": 3, "draft_month_shift": [], "draft_store_shift": [], "result": "", "deficiency": "", "return_count": 0}, thread_005))

    print("〇月のシフト:", result)
    print(len(list(graph.get_state_history(cfg))))