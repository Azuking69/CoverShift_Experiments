import os
import json
import time
from typing import TypedDict, Literal
from langchain_anthropic import ChatAnthropic
from langgraph.graph import StateGraph, START, END
from langgraph.checkpoint.postgres import PostgresSaver
from langgraph.types import Command, interrupt
from dotenv import load_dotenv


# 0) 初期設定
# jsonファイルからスタッフデータを読み込む
with open("staff_data.json", encoding="utf-8") as f:
    STAFF = json.load(f)

# 環境変数をロードする
load_dotenv()     

# DBの接続URL                        
DB_URL = os.environ["DB_URL"]

# 名前とIDの対応表を作成する                    
id_to_name = {}                                  
for s in STAFF:
    id_to_name[s["staff_id"]] = s["staff_name"]  # IDから名前を取得する

# 名前からIDを削除する関数
llm_all_staff = []                                     
for s in STAFF:                                  
    item = {}                                    # 名前を削除したデータを作成する
    for key, value in s.items():
        if key != "staff_name":                  # 名前がある場合
            item[key] = value                    # 名前を削除して、IDだけを残す
    llm_all_staff.append(item)                   # 名前を削除したデータをリストに追加する


# 1) 箱作成
class State(TypedDict):
    store_id: int              # 店舗ID
    llm_all_staff: list        # 全員のLLMに渡すデータ
    draft_store_shift: list    # 店全体の月間シフト案
    result: str                # 検査の結果
    deficiency: str            # 不足の有無
    return_count: int          # 戻り値の数
    upper_limit: int           # 上限値
    decision: bool             # 店長の承認(True)・却下(False)
    problems: list             # 検査で見つかった問題の一覧(作り直しのとき LLM に返す)    


# 2) グラフ作成
# 【コード】希望・スキル・指示を読む
def collect(state):
    print("希望シフトを収集中...")
    print("スキルを評価中...")
    return {"llm_all_staff": llm_all_staff, "draft_store_shift": [], "result": "", "deficiency": "", "return_count": 0, "upper_limit": 3, "problems": []}


# 【分岐】スキルチェックが必要かどうかを判断する
def route_1(state) -> Literal["skill_check", "auto_draft"]:
    for s in state["llm_all_staff"]:                # 全員のデータを一人ずつ確認する
        if s["staff_skill"] != s["admin_rate"]:     # スキルと管理者評価が一致しない場合は、スキルチェックが必要
            return "skill_check"
    return "auto_draft"                             # スキルと管理者評価が一致する場合は、自動編成に進む


# 【コード】未確認を「要指導」とみなして、店長に知らせる(止まらない)
def skill_check(state):
    print("スキルチェック中...")
    for s in state["llm_all_staff"]:                 
        if s["staff_skill"] != s["admin_rate"]:  
            print(f"{id_to_name[s['staff_id']]}のスキルが違います。店長に知らせます。") 
    return {}


# 【LLM】AIが編成案を作る
llm = ChatAnthropic(model="claude-sonnet-5-5", api_key=os.environ["ANTHROPIC_API_KEY"])
# llm = FakeLLM()  # 実験用のLLMを使用する場合は、こちらを有効にしてください。

# rules: LLMが編成案を作る際のルール
rules = """あなたは日本のシフト形式を熟知したシフト編成の補助です。
提案だけを行い、最終確定は人(店長)が行います。

【対象期間】2026-11-01 から 一か月分。

【必ず守るルール】
1. 営業準備と閉店作業を含め、毎日 08:00〜22:30 の間、どの30分の区切りにも社員が1人以上いること。
2. 開店作業(08:00)と閉店作業(22:00〜22:30)を担当する人が、毎日いること。
3. パート・バイトは、requests に書かれていない日には入れないこと。22:00 までが基本。closing_ok が true の人だけ 22:30 まで可。
4. 時間は30分単位(例: 08:00, 13:30)で書くこと。

【できるだけ守る目標】
5. 社員の希望休(off)は、できるだけ通す。ただし、ルール1を守れないときは、希望休を通さなくてよい。通さなかった場合は notes に理由を書くこと。
6. 社員で requests に時間のない日は、あなたが決めてよい。
7. パート・バイトの出勤回数は、人のあいだでほぼ同じになるようにする。

【出力形式】
次のJSONだけを出力すること。説明文は書かない。
{"assignments": [{"staff_id": 1, "date": "2026-11-02", "start": "08:00", "end": "17:00"}], "notes": ["..."]}
"""

def auto_draft(state: State):
    """
    希望のシフト・スキル・管理者評価をもとに、LLMが自動で編成案を作る。
    1) アルバイト・パートの希望シフト(llm_all_staff: list)を確認する
    2) 社員の希望休暇(llm_all_staff: list)を確認する
    3) スキル・管理者評価をもとに、シフトの組み合わせを考える
    4) 可能な限り希望シフトを尊重しつつ、必要なスキルを確保する
    5) 編成案(draft_store_shift: list)を作成する
    """
    print("自動編成中...")
    state["return_count"] += 1
    prompt = rules + make_qualification_text(QUALIFICATION_RULES) + make_days_text(SHAIN_OFF_DAYS) + make_headcount_text(MIN_HEADCOUNT) + make_problem_text(state.get("problems", [])) + "\n【スタッフのデータ(JSON)】\n" + json.dumps(state["llm_all_staff"], ensure_ascii=False)
    res = llm.invoke(prompt)    
    print(res.usage_metadata)
    print(res.response_metadata.get("stop_reason"))
    text = ""
    for block in res.content:
        if block["type"] == "text":
            text = block["text"]
    data = json.loads(text)
    print(f"編成の件数: {len(data['assignments'])}")
    with open("month_draft.json", "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False)

    return {"draft_store_shift": data["assignments"], "return_count": state["return_count"]}

# 店ごとの設定(管理者が決める)。資格が要らない業種は [] にする
QUALIFICATION_RULES = [
    {"qualification": ["登録販売者(管理者)", "薬剤師"], "start": "08:00", "end": "22:30", "min": 1},
]
SHAIN_OFF_DAYS = 9
MIN_HEADCOUNT = [
    {"start": "08:00", "end": "09:00", "min": 3, "exclude": ["薬剤師"]},
    {"start": "09:00", "end": "13:00", "min": 4, "want": 5, "exclude": []},
]


# 【コード】資格ルールの文章を作る
def make_qualification_text(qual_rules):
    if not qual_rules:                       # [] のときは、文を作らない(スイッチOFF)
        return ""
    text = "\n【資格のルール(必ず守る)】\n"
    for r in qual_rules:
        names = "、".join(r["qualification"])
        text += f"- {r['start']}〜{r['end']}は、qualification が「{names}」のどれかの人が、どの30分の区切りにも{r['min']}人以上いること。\n"
    return text


# 【コード】社員の出勤日数の文章を作る
def make_days_text(off_days):
    if off_days is None:                     # None のときは、文を作らない(スイッチOFF)
        return ""
    work_days = 30 - off_days
    return (f"\n【社員の出勤日数(必ず守る)】\n"
            f"- 社員(employment が 社員 の人)は、1か月の公休(休み)が{off_days}日です。出勤は、ちょうど{work_days}日にすること。\n"
            f"- requests に off と書かれた日は、公休にあててよい。\n"
            f"- requests に paid_leave: true と書かれた日は、1日まるごと有給で、その日は店に出ない。ただし、出勤日数には1日として数える(例: 有給が2日なら、実際に出る日は{work_days - 2}日)。\n"
            f"- requests に paid_leave: half と書かれた日は、半休。start と end の時間どおりに入れる。この日も、出勤日数に1日として数える。\n"
            f"- 有給と半休の日は、できるだけ守る。守れなかったときは、notes に理由を書くこと。\n"
            f"- 出力する前に、社員1人ずつ、出勤した日と有給の日を合わせて数えて、{work_days}日であることを確かめること。\n")


# 【コード】問題の一覧を、LLM に渡す文にする関数
def make_problem_text(problems):
    if not problems:                          # 問題がないとき(1回目)は、文を作らない
        return ""
    text = "\n【前回の案の問題(今回は必ず直すこと)】\n"
    for p in problems[:20]:                   # 長くなりすぎないよう、20件まで
        text += f"- {p}\n"
    if len(problems) > 20:
        text += f"- (ほか{len(problems) - 20}件)\n"
    return text


# 【コード】最低人数の文章を作る
def make_headcount_text(rules):
    if not rules:                            # [] のときは、文を作らない(スイッチOFF)
        return ""
    text = "\n【時間帯ごとの最低人数(必ず守る)】\n"
    for r in rules:
        text += f"- {r['start']}〜{r['end']}は、同時にいる人数を{r['min']}人以上にすること。\n"
        if r.get("exclude"):
            text += f"  (qualification が{'・'.join(r['exclude'])}の人は、この時間帯の人数に数えない)\n"
        if r.get("want"):
            text += f"  できれば{r['want']}人にする。\n"
    text += "- 出られる人が足りなくて、どうしても守れない日は、守れなくてよい。その日は notes に書くこと。\n"
    return text


#  【コード】編成案をチェックする(社員が毎回1人以上いるか)
def check_coverage(assignments, all_staff):
    id_to_emp = {}
    for s in all_staff:
        id_to_emp[s["staff_id"]] = s["employment"]

    def to_min(t):
        h, m = t.split(":")
        return int(h) * 60 + int(m)

    problems = []
    for day in range(1, 31):
        date = f"2026-11-{day:02d}"
        for t in range(8 * 60, 22 * 60 + 30, 30):
            count = 0
            for a in assignments:
                if a["date"] == date and id_to_emp[a["staff_id"]] == "社員" and to_min(a["start"]) <= t < to_min(a["end"]):
                    count += 1
            if count == 0:
                problems.append(f"{date} {t // 60:02d}:{t % 60:02d} 社員がいません")
    return problems


#  【コード】編成案をチェックする(資格者が足りているか)
def check_qualification(assignments, all_staff, rules):
    id_to_qual = {}
    for s in all_staff:
        id_to_qual[s["staff_id"]] = s.get("qualification")   # 資格がない人は None

    def to_min(t):
        h, m = t.split(":")
        return int(h) * 60 + int(m)

    problems = []
    for rule in rules:                                        # ルールが [] なら何もしない(スイッチOFF)
        for day in range(1, 31):
            date = f"2026-11-{day:02d}"
            for t in range(to_min(rule["start"]), to_min(rule["end"]), 30):
                count = 0
                for a in assignments:
                    if a["date"] == date and id_to_qual.get(a["staff_id"]) in rule["qualification"] and to_min(a["start"]) <= t < to_min(a["end"]):
                        count += 1
                if count < rule["min"]:
                    problems.append(f"{date} {t // 60:02d}:{t % 60:02d} 資格者が{rule['min']}人未満です({count}人)")
    return problems


#  【コード】編成案をチェックする(パート・バイトが、申請のない日に入っていないか)
def check_requests(assignments, all_staff):
    id_to_staff = {}
    for s in all_staff:
        id_to_staff[s["staff_id"]] = s

    problems = []
    for a in assignments:
        s = id_to_staff[a["staff_id"]]
        if s["employment"] not in ("パート", "バイト"):
            continue                                         # 社員はここでは見ない
        ok_dates = []
        for r in s["requests"]:
            if "start" in r:                                 # 出たい日だけ(off の日は入れない)
                ok_dates.append(r["date"])
        if a["date"] not in ok_dates:
            problems.append(f"{a['date']} ID{a['staff_id']}は申請のない日です")
    return problems


#  【コード】編成案をチェックする(22:30まで残るのは closing_ok の人だけ)
def check_closing(assignments, all_staff):
    id_to_staff = {}
    for s in all_staff:
        id_to_staff[s["staff_id"]] = s

    problems = []
    for a in assignments:
        s = id_to_staff[a["staff_id"]]
        if s["employment"] not in ("パート", "バイト"):
            continue
        if a["end"] > "22:00" and not s.get("closing_ok"):
            problems.append(f"{a['date']} ID{a['staff_id']}は22:30まで残れません")
    return problems


#  【コード】編成案をチェックする(社員の出勤日数が、決まりどおりか)
def check_shain_days(assignments, all_staff, off_days):
    if off_days is None:                                     # None のときは何も見ない(スイッチOFF)
        return []
    work_days = 30 - off_days                                # 出勤日数 = 月の日数 - 公休日数
    problems = []
    for s in all_staff:
        if s["employment"] != "社員":
            continue
        dates = []
        for a in assignments:
            if a["staff_id"] == s["staff_id"] and a["date"] not in dates:
                dates.append(a["date"])                      # 同じ日は1回だけ数える
        for r in s["requests"]:
            if r.get("paid_leave") is True and r["date"] not in dates:   # 1日まるごと有給の日も、出勤日数に数える
                dates.append(r["date"])
        if len(dates) != work_days:
            problems.append(f"ID{s['staff_id']}の出勤日数が{len(dates)}日です(決まりは{work_days}日)")
    return problems


def to_min(t):
    h, m = t.split(":")
    return int(h) * 60 + int(m)

def _req(staff, date):
    for r in staff.get("requests", []):
        if r["date"] == date:
            return r
    return None

def max_headcount(date, t, all_staff, exclude):
    """その日その時刻に、理論上いちばん多く何人出られるか"""
    n = 0
    for s in all_staff:
        if s.get("qualification") in exclude:
            continue
        req = _req(s, date)
        if s["employment"] == "社員":
            if req and (req.get("off") or req.get("paid_leave") is True):
                continue
            if req and "start" in req and not (to_min(req["start"]) <= t < to_min(req["end"])):
                continue
            n += 1
        else:  # パート・バイトは、申請した時間だけ
            if req and "start" in req and to_min(req["start"]) <= t < to_min(req["end"]):
                n += 1
    return n

def impossible_cases(rules, all_staff):
    """理論上、最低人数に届かない (日付, ルール, 最大人数) の一覧"""
    out = []
    for day in range(1, 31):
        date = f"2026-11-{day:02d}"
        for r in rules:
            slots = range(to_min(r["start"]), to_min(r["end"]), 30)
            best = min(max_headcount(date, t, all_staff, r.get("exclude", [])) for t in slots)
            if best < r["min"]:
                out.append((date, r, best))
    return out

def make_shortage_report(rules, all_staff):
    """管理者に見せる『人が足りない日』と、相談の候補"""
    lines = []
    for date, r, best in impossible_cases(rules, all_staff):
        lines.append(f"{date} {r['start']}〜{r['end']}：最大でも{best}人(最低{r['min']}人)")
        part, shain = [], []
        for s in all_staff:
            if s.get("qualification") in r.get("exclude", []):
                continue
            req = _req(s, date)
            if s["employment"] == "社員":
                if req and req.get("off"):
                    shain.append(str(s["staff_id"]))
            elif not req:   # 申請も休みの連絡もない人
                part.append(str(s["staff_id"]))
        if part:
            lines.append(f"  → パート・バイトに出られるか聞く候補(ID): {', '.join(part)}")
        if shain:
            lines.append(f"  → 希望休を変えられるか相談する社員(ID): {', '.join(shain)}")
    return lines

def check_headcount(assignments, all_staff, rules):
    skip = {(d, r["start"]) for d, r, _ in impossible_cases(rules, all_staff)}
    qual = {s["staff_id"]: s.get("qualification") for s in all_staff}
    problems = []
    for day in range(1, 31):
        date = f"2026-11-{day:02d}"
        for r in rules:
            if (date, r["start"]) in skip:
                continue
            low = None
            for t in range(to_min(r["start"]), to_min(r["end"]), 30):
                n = sum(1 for a in assignments
                        if a["date"] == date
                        and qual.get(a["staff_id"]) not in r.get("exclude", [])
                        and to_min(a["start"]) <= t < to_min(a["end"]))
                low = n if low is None else min(low, n)
            if low is not None and low < r["min"]:
                problems.append(f"{date} {r['start']}〜{r['end']}の人数が{low}人です。{r['min']}人以上にしてください")
    return problems


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
        problems = check_coverage(state["draft_store_shift"], state["llm_all_staff"])
        problems = problems + check_qualification(state["draft_store_shift"], state["llm_all_staff"], QUALIFICATION_RULES)   
        problems = problems + check_requests(state["draft_store_shift"], state["llm_all_staff"])
        problems = problems + check_closing(state["draft_store_shift"], state["llm_all_staff"])
        problems = problems + check_shain_days(state["draft_store_shift"], state["llm_all_staff"], SHAIN_OFF_DAYS)
        problems += check_headcount(state["draft_store_shift"], state["llm_all_staff"], MIN_HEADCOUNT)

        if state["draft_store_shift"] == []:
            state["result"] = "problem_O"
        elif problems:
            print(problems)
            state["result"] = "problem_O"
            return {"result": state['result'], "problems": problems}
        else:
            state["result"] = "valid"

        # 【分岐】検査結果
        if state["result"] == "valid":
            print("編成案は有効です。")
            shortage = make_shortage_report(MIN_HEADCOUNT, state["llm_all_staff"])
            if shortage:
                print("【人が足りない日(管理者に相談してください)】")
                print("\n".join(shortage))
            return {"result": state['result'], "problems": []}
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
    decision = interrupt({"draft_store_shift": state["draft_store_shift"], "ask": "承認 | 却下"})
    return {"decision": decision}


# 【返信】店長の選択
def route_3(state) -> Command[Literal["finalize", "auto_draft"]]:
    if state["decision"] == True:
        return Command(goto="finalize", update={
            "draft_store_shift": state["draft_store_shift"] + ["承認済み"]})   # 承認のときだけ「承認済み」を足す
    else:
        return Command(goto="auto_draft")                                     


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
builder.add_node("route_3", route_3)
builder.add_node("finalize", finalize)
builder.add_node("send_final_shift", send_final_shift)


# 4) グラフ連結
builder.add_edge(START, "collect")
builder.add_conditional_edges("collect", route_1, {"skill_check": "skill_check", "auto_draft": "auto_draft"})
builder.add_edge("skill_check", "auto_draft")
builder.add_edge("auto_draft", "validate")
builder.add_conditional_edges("validate", route_2, {"approve": "approve", "contact": "contact", "auto_draft": "auto_draft", "manual_draft": "manual_draft"})
builder.add_edge("approve", "route_3")
builder.add_edge("finalize", "send_final_shift")
builder.add_edge("send_final_shift", END)


# 5) グラフ実行
if __name__ == "__main__":
    with PostgresSaver.from_conn_string(DB_URL) as saver:
        saver.setup()
        graph = builder.compile(checkpointer=saver)

        config = {"configurable": {"thread_id": "test_qual_4"}}        
        start = time.time()

        for chunk in graph.stream({"store_id": 101}, config, stream_mode="updates"):
            for node_name, update in chunk.items():
                print(f"--- {node_name} が終わりました（{time.time() - start:.1f}秒）")

        print("ストリーム終了")
