# =====================================================================
#  CoverShift 試作 02(整理版)
#  prototype_01.py の中身を、役割ごとに並べ直したもの。
#
#  並び順:
#    0. 設定(店ごとに管理者が決める数字は、ここだけ)
#    1. 道具(時間の計算など)
#    2. データの読み込み(名前をはずす)
#    3. State(グラフの箱)
#    4. LLM に渡す文(固定のルール + 設定から作る文)
#    5. 検査(コードが、LLM の案をチェックする)
#    6. 人手が足りない日の相談の候補
#    7. 休憩を入れる(コード)
#    8. グラフのノード(1つ1つの処理)
#    9. グラフの連結
#   10. 実行
# =====================================================================
import os
import json
import time
import datetime
from typing import TypedDict, Literal
from dotenv import load_dotenv
from langchain_anthropic import ChatAnthropic
from langgraph.graph import StateGraph, START, END
from langgraph.checkpoint.postgres import PostgresSaver
from langgraph.types import Command, interrupt

load_dotenv()


# =====================================================================
# 0. 設定(店ごとに管理者が決める。いまは、コードの定数)
#    [] や None にすると、その機能は「検査」も「LLM への文」もなくなる
# =====================================================================
PERIOD = {"start": "2026-11-01", "days": 30}          # 対象期間(31日の月は days を 31 に)
BUSINESS_HOURS = ("08:00", "22:30")                   # 営業時間(準備と閉店作業をふくむ)

# 資格者を、時間帯ごとに min 人以上置く
QUALIFICATION_RULES = [
    {"qualification": ["登録販売者(管理者)", "薬剤師"], "start": "08:00", "end": "22:30", "min": 1},
]

# 社員の1か月の公休日数(出勤日数 = 期間の日数 - 公休日数)
SHAIN_OFF_DAYS = 9                                    # 仮の値。本物の値は、まだわからない

# 時間帯ごとの最低人数。exclude の資格の人は、その時間帯の人数に数えない
MIN_HEADCOUNT = [
    {"start": "08:00", "end": "09:00", "min": 3, "exclude": ["薬剤師"]},
    {"start": "09:00", "end": "13:00", "min": 4, "want": 5, "exclude": []},
]
# "hard": 守れなかったら作り直し  /  "soft": 守れなかった所を、管理者への知らせにする
MIN_HEADCOUNT_MODE = "soft"

# 休憩のルール
BREAK_RULES = {
    # 勤務(拘束)の長さごとの休憩。当てはまる最後の行を使う
    "lengths": [
        {"over_hours": 6,  "minutes": 45},
        {"over_hours": 8,  "minutes": 60},
        {"over_hours": 10, "minutes": 90, "split": [60, 30]},   # 通し
    ],
    "first_window": ("11:00", "16:00"),    # 1回目の休憩を取れる時間帯
    "later_window": ("11:00", "22:00"),    # 通しの2回目(30分)を取れる時間帯
    "max_same_time": [                     # 同時に休憩できる人数
        {"start": "11:00", "end": "13:00", "max": 1},
        {"start": "13:00", "end": "22:00", "max": 2},
    ],
    "anywhere_if_full": True,              # 上の時間帯に入らないとき、勤務中のどこでもよい(遅番など)
    "margin_start": 60,                    # 出勤から休憩まで、最低あける分(仮定)
    "margin_end": 60,                      # 休憩から退勤まで、最低あける分(仮定)
    "shain_need_other": True,              # 社員(薬剤師を除く)の休憩中は、ほかの社員がいること
}

UPPER_LIMIT = 3                            # 作り直しの上限(LLM は1回で約6〜10分)
MODEL_NAME = "claude-sonnet-5-5"
STAFF_FILE = os.environ.get("STAFF_FILE", "staff_data.json")
DRAFT_FILE = "month_draft.json"            # LLM が返した案の保存先
LLM = None                                 # テストのときは、ここにニセの LLM を入れる


# =====================================================================
# 1. 道具
# =====================================================================
def to_min(t):
    """'13:30' -> 810(分)"""
    h, m = t.split(":")
    return int(h) * 60 + int(m)


def hm(m):
    """810 -> '13:30'"""
    return f"{m // 60:02d}:{m % 60:02d}"


def all_dates():
    """対象期間の日付の一覧(例: ['2026-11-01', ...])"""
    start = datetime.date.fromisoformat(PERIOD["start"])
    return [(start + datetime.timedelta(days=i)).isoformat() for i in range(PERIOD["days"])]


def find_request(staff, date):
    """その人の、その日の requests を返す(なければ None)"""
    for r in staff.get("requests", []):
        if r["date"] == date:
            return r
    return None


def get_llm():
    global LLM
    if LLM is None:
        LLM = ChatAnthropic(model=MODEL_NAME, api_key=os.environ["ANTHROPIC_API_KEY"])
    return LLM


# =====================================================================
# 2. データの読み込み(名前は LLM に渡さない)
# =====================================================================
with open(STAFF_FILE, encoding="utf-8") as f:
    STAFF = json.load(f)

id_to_name = {s["staff_id"]: s["staff_name"] for s in STAFF}
llm_all_staff = [{k: v for k, v in s.items() if k != "staff_name"} for s in STAFF]


# =====================================================================
# 3. State(グラフの箱)
# =====================================================================
class State(TypedDict):
    store_id: int
    llm_all_staff: list        # LLM に渡すスタッフのデータ(名前なし)
    draft_store_shift: list    # 月間シフト案(assignments)
    result: str                # 検査の結果: valid / problem_O / limit_reached ...
    deficiency: str
    return_count: int          # LLM を呼んだ回数
    upper_limit: int
    decision: bool             # 店長の承認(True)・却下(False)
    problems: list             # 検査で見つかった問題(作り直しのとき LLM に返す)
    warnings: list             # 作り直しはしないが、管理者に知らせること
    breaks: list               # 休憩の一覧
    shortage_report: list      # 人が足りない日の、相談の候補
    llm_shortages: list        # LLM が「守れなかった」と申告したこと(コードは未検証)
    llm_notes: list            # LLM のメモ
    final_message: str


# =====================================================================
# 4. LLM に渡す文
#    固定のルール(RULES_TEXT)+ 設定から作る文(make_*_text)+ スタッフのデータ
# =====================================================================
def make_period_text():
    return (f"【対象期間】{PERIOD['start']} から {PERIOD['days']}日間。"
            f"営業時間は {BUSINESS_HOURS[0]}〜{BUSINESS_HOURS[1]}(準備と閉店作業をふくむ)。\n")


RULES_TEXT = """あなたは日本のシフト形式を熟知したシフト編成の補助です。
提案だけを行い、最終確定は人(店長)が行います。

【requests の読み方】
- start と end がある: その時間で出たい(社員の場合は、その時間どおりに入れる)。
- off: 休みたい日。
- paid_leave: true: 1日まるごと有給。その日は店に出ない。
- paid_leave: half(start と end つき): 半休。その時間どおりに入れる。
- 何も書いていない日: パート・バイトは入れない。社員は、あなたが決めてよい。

【必ず守るルール】
1. 営業時間のあいだ、どの30分の区切りにも社員が1人以上いること。開店作業と閉店作業は、この社員が行う。
2. パート・バイトは、start のある申請の日だけ、申請の時間の中で入れること。申請のない日と off の日には入れない。
3. パート・バイトは22:00まで。22:30までは closing_ok が true の人だけ。
4. 時間は30分単位(例: 08:00, 13:30)で書くこと。
5. 出勤の時間は、営業時間のどこから始めてもよい(10時や11時の出勤も可)。

【守れないとき】
必ず守るルール同士が両立しない日は、次の順で、下のほうから諦めること。
  1. 資格者の配置(上ほど守る)
  2. 社員の出勤日数を守る
  3. 社員の希望休と有給・半休
  4. 時間帯ごとの最低人数
  5. パート・バイトの申請を、できるだけ多く入れる
  6. パート・バイトの出勤回数の差を小さくする
諦めた所は、必ず shortages に書くこと。

【できるだけ守る目標】
- パート・バイトは、店の人手が足りる範囲で、申請をできるだけ多く入れる。そのうえで、出勤回数の差は小さくする(目安は3日差まで)。
- 社員の希望休(off)は、できるだけ通す。通さなかった場合は notes に理由を書くこと。

【出力形式】
次のJSONだけを出力すること。説明文は書かない。
{"assignments": [{"staff_id": 1, "date": "2026-11-02", "start": "08:00", "end": "17:00"}],
 "shortages": [{"date": "2026-11-20", "start": "08:00", "end": "09:00", "reason": "出られる人が足りない"}],
 "notes": ["..."]}
"""


def make_qualification_text(qual_rules):
    if not qual_rules:
        return ""
    text = "\n【資格のルール(必ず守る)】\n"
    for r in qual_rules:
        names = "、".join(r["qualification"])
        text += f"- {r['start']}〜{r['end']}は、qualification が「{names}」のどれかの人が、どの30分の区切りにも{r['min']}人以上いること。\n"
    return text


def make_days_text(off_days):
    if off_days is None:
        return ""
    work_days = PERIOD["days"] - off_days
    return (f"\n【社員の出勤日数(必ず守る)】\n"
            f"- 社員は、1か月の公休(休み)が{off_days}日です。出勤は、ちょうど{work_days}日にすること。\n"
            f"- 有給(全休)の日は、店に出ないが、出勤日数には1日として数える(例: 有給が2日なら、実際に出る日は{work_days - 2}日)。\n"
            f"- 半休の日も、出勤日数に1日として数える。\n"
            f"- 出力する前に、社員1人ずつ、出勤した日と有給の日を合わせて数えて、{work_days}日であることを確かめること。\n")


def make_headcount_text(rules):
    if not rules:
        return ""
    text = "\n【時間帯ごとの最低人数】\n"
    for r in rules:
        text += f"- {r['start']}〜{r['end']}は、同時にいる人数を{r['min']}人以上にすること。\n"
        if r.get("exclude"):
            text += f"  (qualification が{'・'.join(r['exclude'])}の人は、この時間帯の人数に数えない)\n"
        if r.get("want"):
            text += f"  できれば{r['want']}人にする。\n"
    text += "- 出られる人が足りなくて守れない日は、守れなくてよい。その日は shortages に書くこと。\n"
    return text


def make_problem_text(problems):
    if not problems:
        return ""
    text = "\n【前回の案の問題(今回は必ず直すこと)】\n"
    for p in problems[:20]:
        text += f"- {p}\n"
    if len(problems) > 20:
        text += f"- (ほか{len(problems) - 20}件)\n"
    return text


def build_prompt(state):
    return (make_period_text() + RULES_TEXT
            + make_qualification_text(QUALIFICATION_RULES)
            + make_days_text(SHAIN_OFF_DAYS)
            + make_headcount_text(MIN_HEADCOUNT)
            + make_problem_text(state.get("problems", []))
            + "\n【スタッフのデータ(JSON)】\n"
            + json.dumps(state["llm_all_staff"], ensure_ascii=False))


# =====================================================================
# 5. 検査(コードが、LLM の案をチェックする)
#    どれも「問題の文章のリスト」を返す。空なら問題なし
# =====================================================================
def check_coverage(assignments, all_staff):
    """営業時間のあいだ、どの30分にも社員が1人以上いるか"""
    emp = {s["staff_id"]: s["employment"] for s in all_staff}
    problems = []
    for date in all_dates():
        for t in range(to_min(BUSINESS_HOURS[0]), to_min(BUSINESS_HOURS[1]), 30):
            n = sum(1 for a in assignments
                    if a["date"] == date and emp[a["staff_id"]] == "社員"
                    and to_min(a["start"]) <= t < to_min(a["end"]))
            if n == 0:
                problems.append(f"{date} {hm(t)} 社員がいません")
    return problems


def check_qualification(assignments, all_staff, rules):
    """資格者が、時間帯ごとに min 人以上いるか"""
    qual = {s["staff_id"]: s.get("qualification") for s in all_staff}
    problems = []
    for rule in rules:
        for date in all_dates():
            for t in range(to_min(rule["start"]), to_min(rule["end"]), 30):
                n = sum(1 for a in assignments
                        if a["date"] == date and qual.get(a["staff_id"]) in rule["qualification"]
                        and to_min(a["start"]) <= t < to_min(a["end"]))
                if n < rule["min"]:
                    problems.append(f"{date} {hm(t)} 資格者が{rule['min']}人未満です({n}人)")
    return problems


def check_requests(assignments, all_staff):
    """パート・バイトが、申請の日の、申請の時間の中だけで入っているか"""
    staff = {s["staff_id"]: s for s in all_staff}
    problems = []
    for a in assignments:
        s = staff[a["staff_id"]]
        if s["employment"] not in ("パート", "バイト"):
            continue
        req = find_request(s, a["date"])
        if not req or "start" not in req:
            problems.append(f"{a['date']} ID{a['staff_id']}は申請のない日です")
        elif to_min(a["start"]) < to_min(req["start"]) or to_min(a["end"]) > to_min(req["end"]):
            problems.append(f"{a['date']} ID{a['staff_id']}は申請の時間({req['start']}〜{req['end']})の外です")
    return problems


def check_closing(assignments, all_staff):
    """22:30まで残るのは、closing_ok の人だけか"""
    staff = {s["staff_id"]: s for s in all_staff}
    problems = []
    for a in assignments:
        s = staff[a["staff_id"]]
        if s["employment"] in ("パート", "バイト") and a["end"] > "22:00" and not s.get("closing_ok"):
            problems.append(f"{a['date']} ID{a['staff_id']}は22:30まで残れません")
    return problems


def check_shain_days(assignments, all_staff, off_days):
    """社員の出勤日数が、決まりどおりか(有給の全休も、1日として数える)"""
    if off_days is None:
        return []
    work_days = PERIOD["days"] - off_days
    problems = []
    for s in all_staff:
        if s["employment"] != "社員":
            continue
        dates = []
        for a in assignments:
            if a["staff_id"] == s["staff_id"] and a["date"] not in dates:
                dates.append(a["date"])
        for r in s.get("requests", []):
            if r.get("paid_leave") is True and r["date"] not in dates:
                dates.append(r["date"])
        if len(dates) != work_days:
            problems.append(f"ID{s['staff_id']}の出勤日数が{len(dates)}日です(決まりは{work_days}日)")
    return problems


def max_headcount(date, t, all_staff, exclude):
    """その日その時刻に、理論上いちばん多く何人出られるか(社員の日数の決まりは見ない)"""
    n = 0
    for s in all_staff:
        if s.get("qualification") in exclude:
            continue
        req = find_request(s, date)
        if s["employment"] == "社員":
            if req and (req.get("off") or req.get("paid_leave") is True):
                continue
            if req and "start" in req and not (to_min(req["start"]) <= t < to_min(req["end"])):
                continue
            n += 1
        elif req and "start" in req and to_min(req["start"]) <= t < to_min(req["end"]):
            n += 1
    return n


def impossible_cases(rules, all_staff):
    """理論上、最低人数に届かない (日付, ルール, 最大人数) の一覧"""
    out = []
    for date in all_dates():
        for r in rules:
            slots = range(to_min(r["start"]), to_min(r["end"]), 30)
            best = min(max_headcount(date, t, all_staff, r.get("exclude", [])) for t in slots)
            if best < r["min"]:
                out.append((date, r, best))
    return out


def check_headcount(assignments, all_staff, rules):
    """最低人数を守れているか。理論上守れない日は、ここでは見ない(相談の表示に回す)"""
    skip = {(d, r["start"]) for d, r, _ in impossible_cases(rules, all_staff)}
    qual = {s["staff_id"]: s.get("qualification") for s in all_staff}
    problems = []
    for date in all_dates():
        for r in rules:
            if (date, r["start"]) in skip:
                continue
            low = None
            for t in range(to_min(r["start"]), to_min(r["end"]), 30):
                n = sum(1 for a in assignments
                        if a["date"] == date and qual.get(a["staff_id"]) not in r.get("exclude", [])
                        and to_min(a["start"]) <= t < to_min(a["end"]))
                low = n if low is None else min(low, n)
            if low is not None and low < r["min"]:
                problems.append(f"{date} {r['start']}〜{r['end']}の人数が{low}人です。{r['min']}人以上にしてください")
    return problems


def run_checks(assignments, all_staff):
    """全部の検査をまとめて動かす。返すのは (問題, 知らせ)。
       問題 = 作り直しの理由 / 知らせ = 管理者に見せるだけ"""
    problems = []
    problems += check_coverage(assignments, all_staff)
    problems += check_qualification(assignments, all_staff, QUALIFICATION_RULES)
    problems += check_requests(assignments, all_staff)
    problems += check_closing(assignments, all_staff)
    problems += check_shain_days(assignments, all_staff, SHAIN_OFF_DAYS)
    headcount = check_headcount(assignments, all_staff, MIN_HEADCOUNT)
    warnings = []
    if MIN_HEADCOUNT_MODE == "hard":
        problems += headcount
    else:
        warnings += headcount
    return problems, warnings


# =====================================================================
# 6. 人手が足りない日の、相談の候補(管理者に見せる)
# =====================================================================
def make_shortage_report(rules, all_staff):
    lines = []
    for date, r, best in impossible_cases(rules, all_staff):
        lines.append(f"{date} {r['start']}〜{r['end']}：最大でも{best}人(最低{r['min']}人)")
        part, shain = [], []
        for s in all_staff:
            if s.get("qualification") in r.get("exclude", []):
                continue
            req = find_request(s, date)
            if s["employment"] == "社員":
                if req and req.get("off"):
                    shain.append(str(s["staff_id"]))
            elif not req:
                part.append(str(s["staff_id"]))
        if part:
            lines.append(f"  → パート・バイトに出られるか聞く候補(ID): {', '.join(part)}")
        if shain:
            lines.append(f"  → 希望休を変えられるか相談する社員(ID): {', '.join(shain)}")
    return lines


# =====================================================================
# 7. 休憩を入れる(コード。LLM は使わない)
# =====================================================================
def break_chunks(start, end, rules):
    """この勤務で必要な休憩を、分割した長さ(分)のリストで返す。なければ []"""
    hours = (to_min(end) - to_min(start)) / 60
    chosen = None
    for r in rules["lengths"]:
        if hours > r["over_hours"]:
            chosen = r
    if chosen is None:
        return []
    return chosen.get("split", [chosen["minutes"]])


def max_at(t, rules):
    for r in rules["max_same_time"]:
        if to_min(r["start"]) <= t < to_min(r["end"]):
            return r["max"]
    return 0


def plan_breaks(assignments, all_staff, rules):
    """休憩を入れる。返すのは (休憩の一覧, 入れられなかった所の一覧)。
       順番: パート・バイトの早番から → 社員(薬剤師を除く)→ 薬剤師"""
    info = {s["staff_id"]: s for s in all_staff}

    def is_shain(sid):
        return info[sid]["employment"] == "社員" and info[sid].get("qualification") != "薬剤師"

    def order(a):
        if info[a["staff_id"]]["employment"] != "社員":
            group = 0
        else:
            group = 1 if is_shain(a["staff_id"]) else 2
        return (group, to_min(a["start"]), a["staff_id"])

    breaks, problems = [], []
    for date in sorted({a["date"] for a in assignments}):
        today = [a for a in assignments if a["date"] == date]
        busy = {}       # 15分ごとの休憩中の人数
        on_break = {}   # 15分ごとの休憩中の人のID
        for a in sorted(today, key=order):
            sid = a["staff_id"]
            s0, e0 = to_min(a["start"]), to_min(a["end"])
            for k, length in enumerate(break_chunks(a["start"], a["end"], rules)):
                win = rules["first_window"] if k == 0 else rules["later_window"]
                windows = [(max(to_min(win[0]), s0 + rules["margin_start"]),
                            min(to_min(win[1]), e0 - rules["margin_end"]))]
                if rules.get("anywhere_if_full"):
                    windows.append((s0 + rules["margin_start"], e0 - rules["margin_end"]))
                placed = False
                for lo, hi in windows:
                    t = lo
                    while t + length <= hi and not placed:
                        slots = range(t, t + length, 15)
                        ok = True
                        for x in slots:
                            if busy.get(x, 0) >= max_at(x - x % 30, rules) or sid in on_break.get(x, []):
                                ok = False
                                break
                            if rules["shain_need_other"] and is_shain(sid):
                                others = [b for b in today
                                          if b["staff_id"] != sid and is_shain(b["staff_id"])
                                          and to_min(b["start"]) <= x < to_min(b["end"])
                                          and b["staff_id"] not in on_break.get(x, [])]
                                if not others:
                                    ok = False
                                    break
                        if ok:
                            for x in slots:
                                busy[x] = busy.get(x, 0) + 1
                                on_break.setdefault(x, []).append(sid)
                            breaks.append({"staff_id": sid, "date": date, "start": hm(t), "end": hm(t + length)})
                            placed = True
                        t += 15
                    if placed:
                        break
                if not placed:
                    problems.append(f"{date} ID{sid}の休憩({length}分)を入れられません")
    return breaks, problems


# =====================================================================
# 8. グラフのノード(1つ1つの処理)
# =====================================================================
def collect(state):
    print("希望シフトを収集中...")
    return {"llm_all_staff": llm_all_staff, "draft_store_shift": [], "result": "", "deficiency": "",
            "return_count": 0, "upper_limit": UPPER_LIMIT, "problems": [], "warnings": [],
            "breaks": [], "shortage_report": [], "llm_shortages": [], "llm_notes": [], "final_message": ""}


def route_1(state) -> Literal["skill_check", "auto_draft"]:
    for s in state["llm_all_staff"]:
        if s["staff_skill"] != s["admin_rate"]:
            return "skill_check"
    return "auto_draft"


def skill_check(state):
    print("スキルチェック中...")
    for s in state["llm_all_staff"]:
        if s["staff_skill"] != s["admin_rate"]:
            print(f"{id_to_name[s['staff_id']]}のスキルが違います。店長に知らせます。")
    return {}


def auto_draft(state: State):
    """LLM が月間シフト案を作る。読めなかったときは、問題として返して作り直す"""
    print("自動編成中...")
    count = state["return_count"] + 1
    res = get_llm().invoke(build_prompt(state))
    print(res.usage_metadata)
    print(res.response_metadata.get("stop_reason"))
    text = ""
    for block in res.content:
        if block["type"] == "text":
            text = block["text"]
    try:
        data = json.loads(text)
        assignments = data["assignments"]
    except (json.JSONDecodeError, KeyError, TypeError):
        print("LLM の返事を JSON として読めませんでした。")
        return {"draft_store_shift": [], "return_count": count,
                "problems": ["前回の出力は JSON として読めませんでした。JSON だけを出力してください"]}
    print(f"編成の件数: {len(assignments)}")
    with open(DRAFT_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False)
    return {"draft_store_shift": assignments, "return_count": count,
            "llm_shortages": data.get("shortages", []), "llm_notes": data.get("notes", [])}


def validate(state: State):
    """コードが案を検査する。通れば valid、問題があれば problem_O(作り直し)"""
    print("編成案を検査中...")
    print(f"検査回数: {state['return_count']}/{state['upper_limit']}")
    if state["return_count"] > state["upper_limit"]:
        print("作り直しの上限に達しました。手動編成を行います。")
        return {"result": "limit_reached"}
    if not state["draft_store_shift"]:
        return {"result": "problem_O"}      # 空のときは、auto_draft が入れた problems をそのまま使う
    problems, warnings = run_checks(state["draft_store_shift"], state["llm_all_staff"])
    if problems:
        print(problems)
        return {"result": "problem_O", "problems": problems, "warnings": warnings}
    print("編成案は有効です。")
    report = make_shortage_report(MIN_HEADCOUNT, state["llm_all_staff"])
    if report:
        print("【人が足りない日(管理者に相談してください)】")
        print("\n".join(report))
    if warnings:
        print(f"【最低人数を守れていない所: {len(warnings)}件】")
        print("\n".join(warnings[:10]))
    return {"result": "valid", "problems": [], "warnings": warnings, "shortage_report": report}


def route_2(state) -> Literal["plan_break", "contact", "auto_draft", "manual_draft"]:
    if state["result"] == "valid":
        return "plan_break"
    elif state["result"] == "no_staff":
        return "contact"
    elif state["result"] == "problem_O":
        return "auto_draft"
    return "manual_draft"                   # limit_reached など


def plan_break(state):
    """案が通ったあとに、休憩を入れる(コード)"""
    print("休憩を入れています...")
    breaks, problems = plan_breaks(state["draft_store_shift"], state["llm_all_staff"], BREAK_RULES)
    print(f"休憩: {len(breaks)}件 / 入れられなかった所: {len(problems)}件")
    return {"breaks": breaks, "warnings": state.get("warnings", []) + problems}


def manual_draft(state):
    print("手動編成中...")
    # TODO: 手動編成のロジック。いまは、ここで終わる
    return {"draft_store_shift": state.get("draft_store_shift", [])}


def contact(state):
    print("スタッフに連絡中...")
    # TODO: 連絡ループ。route_2 の no_staff は、いまは使っていない
    return {}


def approve(state):
    print("店長の承認を待っています...")
    decision = interrupt({"draft_store_shift": state["draft_store_shift"], "breaks": state["breaks"],
                          "warnings": state["warnings"], "shortage_report": state["shortage_report"],
                          "ask": "承認 | 却下"})
    return {"decision": decision}


def route_3(state) -> Command[Literal["finalize", "auto_draft"]]:
    if state["decision"] is True:
        return Command(goto="finalize", update={"result": "approved"})
    return Command(goto="auto_draft")


def finalize(state):
    print("編成案を確定しました。")
    return {"final_message": "編成案を確定しました。"}


def send_final_shift(state):
    print("最終シフトを送信しました。")
    return {"final_message": "最終シフトを送信しました。"}


# =====================================================================
# 9. グラフの連結
# =====================================================================
builder = StateGraph(State)
for name, fn in [("collect", collect), ("skill_check", skill_check), ("auto_draft", auto_draft),
                 ("validate", validate), ("plan_break", plan_break), ("manual_draft", manual_draft),
                 ("contact", contact), ("approve", approve), ("route_3", route_3),
                 ("finalize", finalize), ("send_final_shift", send_final_shift)]:
    builder.add_node(name, fn)

builder.add_edge(START, "collect")
builder.add_conditional_edges("collect", route_1, {"skill_check": "skill_check", "auto_draft": "auto_draft"})
builder.add_edge("skill_check", "auto_draft")
builder.add_edge("auto_draft", "validate")
builder.add_conditional_edges("validate", route_2, {"plan_break": "plan_break", "contact": "contact",
                                                    "auto_draft": "auto_draft", "manual_draft": "manual_draft"})
builder.add_edge("plan_break", "approve")
builder.add_edge("approve", "route_3")
builder.add_edge("finalize", "send_final_shift")
builder.add_edge("send_final_shift", END)
builder.add_edge("manual_draft", END)
builder.add_edge("contact", END)


# =====================================================================
# 10. 実行
# =====================================================================
if __name__ == "__main__":
    DB_URL = os.environ["DB_URL"]
    with PostgresSaver.from_conn_string(DB_URL) as saver:
        saver.setup()
        graph = builder.compile(checkpointer=saver)
        config = {"configurable": {"thread_id": "test_clean_1"}}     # 実行のたびに新しい名前にする
        start = time.time()
        for chunk in graph.stream({"store_id": 101}, config, stream_mode="updates"):
            for node_name, update in chunk.items():
                print(f"--- {node_name} が終わりました({time.time() - start:.1f}秒)")
        print("ストリーム終了")