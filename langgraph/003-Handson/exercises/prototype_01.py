import os
from typing import TypedDict, Literal
from langchain_anthropic import ChatAnthropic
from langchain_core.tools import tool
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.outputs import ChatGeneration, ChatResult
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage
from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import StateGraph, START, END, MessagesState
from langgraph.checkpoint.postgres import PostgresSaver
from langgraph.types import Command, interrupt
from langgraph.prebuilt import ToolNode, tools_condition

from dotenv import load_dotenv
from staff_data import STAFF, ALL_STAFF, STAFF_INFO


# 0) 初期設定
load_dotenv()                 # 環境変数をロードする
DB_URL = os.environ["DB_URL"] # DBの接続URL


# 1) 箱作成
class State(TypedDict):
    store_id: int              # 店舗ID
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
    upper_limit: int           # 上限値


# 2) グラフ作成
# 【コード】希望・スキル・指示を読む
def collect(state):
    print("希望シフトを収集中...")
    print("スキルを評価中...")
    return {"draft_month_shift": state['preferred_shift']}


# 【分岐】スキルチェックが必要かどうかを判断する
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
def llm_tool(draft_store_shift: list, all_staff: list) -> str:
    """店舗の月間シフト案を作成するために、店舗のスタッフ数を返す"""
    # ここで実際のLLMを呼び出すことができます。今回はダミーとして、単純にリストを返します。
    return f"店舗のスタッフ数: {len(all_staff)}"

class FakeLLM(BaseChatModel):
    """実験用のLLM。実際には、OpenAIやAnthropicなどのLLMを使うことができます。"""

    @property
    def _llm_type(self) -> str:
        return "fake"

    def bind_tools(self, tools, **kwargs):
        return self

    def _generate(self, messages, stop=None, run_maneger=None, **kwargs):
        if any(isinstance(msg, ToolMessage) for msg in messages):
            msg = AIMessage("店舗の月間シフト案を作成しました: " + messages[-1].content)
        else:
            msg = AIMessage("", tool_calls=[{
                "name": "llm_tool",
                "args": {"store_id": "101", "all_staff": []},
                "id": "tool_call_1"
            }])
        return ChatResult(generations=[ChatGeneration(message=msg)])

llm = ChatAnthropic(model="claude-sonnet-5-5", api_key=os.environ["ANTHROPIC_API_KEY"])

def auto_draft(state: State):
    """
    希望のシフト・スキル・管理者評価をもとに、LLMが自動で編成案を作る。
    1) アルバイト・パートの希望シフト(preferred_shift: list)を確認する
    2) 社員の希望休暇(preferred_shift: list)を確認する
    3) スキル・管理者評価をもとに、シフトの組み合わせを考える
    4) 可能な限り希望シフトを尊重しつつ、必要なスキルを確保する
    5) 編成案(draft_store_shift: list)を作成する
    """
    print("自動編成中...")
    state["return_count"] += 1
    return {"draft_store_shift": [llm.invoke(state["draft_store_shift"])], "return_count": state["return_count"]}


# 【コード】ルールを守っているか検査する
def validate(state: State):
    print("編成案を検査中...")

    # 【分岐】検査回数が上限に達しているかどうかを判断する
    print(f"検査回数: {state['return_count']}/{state['upper_limit']}")
    if state["return_count"] > state["upper_limit"] :
        print("編成案の検査回数が上限に達しました。手動編成を行います。")
        state["result"] = "limit_reached"
        return {"result": state['result']}

    else:
        # 検査ロジック実装
        if state["deficiency"] in state["draft_store_shift"]:
            state["result"] = "no_staff"
        elif state["draft_store_shift"] == []:
            state["result"] = "problem_O"
        elif state["draft_store_shift"] != []:
            state["result"] = "valid"
        else:
            state["result"] = "error_shift"

        # 【分岐】検査結果
        if state["result"] == "valid":
            print("編成案は有効です。")
            return {"result": state['result']}
        elif state["result"] == "no_staff":
            print("編成案に必要なスタッフが不足しています。再度編成を行います。")
            return {"result": state['result']}
        elif state["result"] == "limit_reached":
            print("編成案の検査回数が上限に達しました。手動編成を行います。")
            return {"result": state['result']}
        elif state["result"] == "problem_O":
            print("編成案の検査結果が不明です。")
            return {"result": state['result']}
        else:
            print("編成案に問題があります。再度編成を行います。")
            return {"result": state['result']}



# 【分岐】検査結果に応じて、スタッフに連絡するか、自動編成を再度行うかを判断する
def route_2(state) -> Literal["approve", "contact", "auto_draft", "manual_draft"]:
    if state["result"] == "valid":
        return "approve"
    elif state["result"] == "no_staff":
        return "contact"
    elif state["result"] == "limit_reached":
        return "manual_draft"
    elif state["result"] == "problem_O":
        return "auto_draft"
    else:
        return "manual_draft"



# 【コード】手動編成
def manual_draft(state):
    print("手動編成中...")
    # 手動編成のロジックを実装する
    return {"draft_store_shift": ["手動編成されたシフト案"]}


# 【待機】スタッフに LINE で聞いて、返事を待つ[]
def contact(state):
    print("スタッフに連絡中...")
    response = interrupt({"draft_month_shift": state["draft_month_shift"], "ask": "承認|却下"})

    # (分岐)スタッフの返事
    if response == "承認":
        print("スタッフが承認しました。")
        return {"draft": f"{state['staff_name']}の編成案は承認されました。"}, 
    elif response == "却下":
        print("スタッフが却下しました。再度編成を行います。")
        return {"draft": f"{state['staff_name']}の編成案は却下されました。再度編成を行います。"}


# 【待機】店長の承認を待つ
def approve(state):
    print("店長の承認を待っています...")
    decision = interrupt({"draft_store_shift": state["draft_store_shift"], "ask": "承認(True)|却下(False)"})

# 【返信】店長の選択
def route_3(state) -> Command[Literal["finalize", "auto_draft"]]:
    next_node = "finalize" if state["decision"] == True else "auto_draft"
    return Command(goto=next_node, update={"draft_store_shift": state["draft_store_shift"] + ["承認済み"]})


# 【コード】最新データで再チェックして、確定を保存
def finalize(state):
    print("編成案を確定しました。")
    return {"draft": "〇月の編成案を確定しました。"}


# 【コード】最終シフトを送信する
def send_final_shift(state):
    print("最終シフトを送信しました。")
    return {"draft": "〇月の最終シフトを送信しました。"}


# 3) グラフの設計
builder = StateGraph(State)
builder.add_node("collect", collect)
builder.add_node("skill_check", skill_check)
builder.add_node("auto_draft", auto_draft)
builder.add_node("validate", validate)
builder.add_node("manual_draft", manual_draft)
builder.add_node("contact", contact)
builder.add_node("approve", approve)
builder.add_node("finalize", finalize)
builder.add_node("send_final_shift", send_final_shift)


# 4) グラフ連結
builder.add_edge(START, "collect")
builder.add_conditional_edges("collect", route_1, {"skill_check": "skill_check", "auto_draft": "auto_draft"})
builder.add_edge("skill_check", "auto_draft")
builder.add_edge("auto_draft", "validate")
builder.add_conditional_edges("validate", route_2, {"approve": "approve", "contact": "contact", "auto_draft": "auto_draft", "manual_draft": "manual_draft"})
builder.add_edge("approve", "finalize")
builder.add_edge("finalize", "send_final_shift")
builder.add_edge("send_final_shift", END)


# 5) グラフ実行
with PostgresSaver.from_conn_string(DB_URL) as saver:
    saver.setup()
    graph = builder.compile(checkpointer=saver)

    staff_badges = []   # 従業員の情報を入力する箱

    for num in range(1, 6):
        staff_badges.append({"configurable": {
        "thread_id": f"thread_{num}"
    }})





    print(len(list(graph.get_state_history(staff_badges[0]))), "の履歴が保存されました。")
    print("〇月のシフト:" + "draft_store_shift")