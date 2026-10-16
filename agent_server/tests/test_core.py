"""サービスなしで、core（LangGraph＋本物のCP-SAT）を確かめる。  python tests/test_core.py（ルートで実行）"""
import os, sys, tempfile, json
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
os.environ["OUTBOUND_LOG"] = os.path.join(tempfile.mkdtemp(), "outbound.log")
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.types import Command
from core.graph import build_graph
from core.fixtures import STAFF, REQUIREMENTS, DAYS
from core.solver import solve_shift

# 1) ソルバー単体：制約を満たすか
staff = [{"id": s["id"], "name": s["name"], "unpreferred_days": s["unpreferred_days"]} for s in STAFF]
r = solve_shift(staff, REQUIREMENTS, {"respect_wishes": 0.3})
assert r["status"] == "SUCCESS", r
viol = 0
for d in r["schedule"]:
    a = d["assignments"]
    assert len(a["早番"]) >= 2 and len(a["遅番"]) >= 1, f"最低人数を満たさない: {d}"
    both = set(a["早番"]) & set(a["遅番"]); assert not both, f"1人が1日に2シフト: {both}"
    day = d["day"] - 1
    for s in STAFF:
        if day in s["unpreferred_days"] and (s["name"] in a["早番"] or s["name"] in a["遅番"]): viol += 1
print(f"ソルバー: 最低人数OK／二重配置なし／不可希望日に入った件数={viol}")

# 2) グラフ：承認待ち→再開／却下、実名が送信ログに出ない
g = build_graph(InMemorySaver())
c1 = {"configurable": {"thread_id": "t1"}}
g.invoke({"store_id": "S1", "retry_count": 0, "raw_input_names": {}}, c1)
st = g.get_state(c1)
assert st.next == ("manager_review",) and any(t.interrupts for t in st.tasks)
assert st.values["status"] == "S4_説明生成完了" and "スタッフA" in st.values["draft_shift"]
g.invoke(Command(resume=True), c1); assert g.get_state(c1).values["status"] == "S6_確定済み"
c2 = {"configurable": {"thread_id": "t2"}}
g.invoke({"store_id": "S1", "retry_count": 0, "raw_input_names": {}}, c2); g.invoke(Command(resume=False), c2)
assert g.get_state(c2).values["retry_count"] == 1
log = open(os.environ["OUTBOUND_LOG"], encoding="utf-8").read()
assert not any(s["name"] in log for s in STAFF), "実名が送信ログに出ている"
print("グラフ: 承認待ち→再開／却下／実名なし OK")

# 3) 本物のClaude経路：APIは呼ばず、クライアントを差し替えて、送る本文に実名がないことを確かめる
import types, importlib
os.environ["ANTHROPIC_API_KEY"] = "test-key"
import anthropic
class _FakeMsgs:
    def create(self, **req):
        assert not any(s["name"] in json.dumps(req, ensure_ascii=False) for s in STAFF), "送信本文に実名"
        return types.SimpleNamespace(content=[types.SimpleNamespace(type="text", text="説明")],
                                     usage=types.SimpleNamespace(input_tokens=1, output_tokens=1))
anthropic.Anthropic = lambda api_key=None: types.SimpleNamespace(messages=_FakeMsgs())
import json
g2 = build_graph(InMemorySaver()); c3 = {"configurable": {"thread_id": "t3"}}
g2.invoke({"store_id": "S1", "retry_count": 0, "raw_input_names": {}}, c3)
assert "real" in open(os.environ["OUTBOUND_LOG"], encoding="utf-8").read()
print("本物のClaude経路(差し替え): 送信本文に実名なし OK")
