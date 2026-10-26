# 13-3 ~ 4

from langchain_anthropic import ChatAnthropic
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage
from langchain_core.outputs import ChatGeneration, ChatResult
from langchain_core.tools import tool
from langgraph.graph import StateGraph, START, END, MessagesState
from langgraph.prebuilt import ToolNode, tools_condition
from dotenv import load_dotenv

load_dotenv()  # .env ファイルから ANTHROPIC_API_KEY を読み込む

# 0) 도구 정의
def get_staff_count(store_id: str) -> str:
    """가게 직원 수를 반환하는 도구"""
    return f"가게:{store_id}의 직원 수는 5명입니다."


# 1) 箱作成
class FakeLLM(ChatAnthropic):
    """練習用の LLM。
    道具を使うときは、ToolMessage が送られてくるので、それを受け取って結果を返す。"""

    @property
    def _llm_type(self):
        return "fake"

    def bind_tools(self, tools, **kw):  # 道具を実際に動かす
        return self                     # 本物は使える道具一覧を覚える

    def _generate(self, messages, stop=None, run_manager=None, **kw):
        if any(isinstance(msg, ToolMessage) for msg in messages):
            msg = AIMessage("결과를 확인했습니다: " + messages[-1].content)

        else:
            msg = AIMessage("", tool_calls=[{
                "name": "get_staff_count",
                "args": {
                    "store_id": "101"
                }, 
                "id": "c1"
            }])
        return ChatResult(generations=[ChatGeneration(message=msg)])

llm = ChatAnthropic(model_name="claude-haiku-5-5", timeout=None, stop=None) # 本物の LLM を使う場合はこちら
llm = llm.bind_tools([get_staff_count])  # 道具を使えるようにする


# 2) ノード作成
def agent(state: MessagesState):
    return {"messages": [llm.invoke(state["messages"])]} # LLM を1回呼ぶだけ


# 3) グラフ作成
builder = StateGraph(MessagesState)
builder.add_node("agent", agent)
builder.add_node("tools", ToolNode([get_staff_count]))


# 4) グラフ連結
builder.add_edge(START, "agent")
builder.add_conditional_edges("agent", tools_condition) # 既成の分岐：tool_calls があれば "tools"、なければ END
builder.add_edge("tools", "agent")                     # 道具を使ったら、結果を持って agent へ戻る


# 5) グラフ実行
graph = builder.compile()
result = graph.invoke({"messages": [HumanMessage("가게 101의 직원 수를 알려줘")]})
for msg in result["messages"]:
    print(type(msg).__name__, "|", repr(msg.content), getattr(msg, "tool_calls", ""))