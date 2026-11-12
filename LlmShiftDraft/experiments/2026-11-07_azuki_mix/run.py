"""11/07 아즈키 prototype_mcp.py + 우리 방식 섞기 실험 (Sonnet 4.6, 한 달 30일).

아즈키 코드의 프롬프트 · 검사 함수 · 매장 설정 · 데이터를 그대로 불러 쓰고, 아래만 바꾼다.

  mix1 : ① 최소 인원은 경고(재작성 안 보냄) — 기준 문서 「최소 인원 = 경고」
         ② 프롬프트에서 「出力する前に…数えて確かめること」 삭제, 최소 인원 문단을 「できるだけ」로
         ③ 「먼저 내라 · 검사는 코드 · 못 채운 곳은 shortages」 (우리 A_pre2 의 길 주기)
         ④ 구조화 출력(json_schema) — JSON 만 오게. adaptive thinking · effort medium (우리 11/06 하네스와 같음)
         ⑤ 재작성 때 직전 안 + 위반 전부(종류별로 묶음) + 「위반 외는 바꾸지 마라」
  mix1_nothink : mix1 과 같고 생각 끔(thinking disabled) + JSON 고정 (11/08, mix1 · mix2 가 생각으로 한도 소진한 뒤)
  mix1_55 : mix1 과 같은 프롬프트 · 경고 처리 · JSON 고정, 모델만 Sonnet 5.5, 생각 설정 안 줌(아즈키와 같게) (11/08)
  mix1_nothink_order : mix1_nothink + 「解き方の順番」(마감 자격 사원 먼저 → 개점 → 사원 일수 → 파트) (11/08)
  mix2 : mix1 + 날짜별 미리 계산(후보표: 직원별 가능 범위 · 최소 인원 시간대 후보 · 자격자 후보). 원본 데이터는 그대로 둠
  mix2_55 : mix1_55 + 후보표(mix2 와 같은 재료). Sonnet 5.5 · 생각 설정 안 줌 · JSON 고정 · 최소 인원 경고 (11/12)

비교 기준: 아즈키가 같은 코드 · 데이터로 잰 4.6 (위반 42건, 출력 3.1만~7.1만 토큰, 최대 약 14분).
          baseline 은 돈을 아끼려고 다시 돌리지 않는다 → 하네스가 다르다는 한계가 남음 (RESULTS.md).

실행 (handwritten/ 의 venv):
  cd handwritten && caffeinate -i uv run python -I ../experiments/2026-11-07_azuki_mix/run.py --cond mix1
  가짜 LLM (돈 안 씀): --fake ok | --fake bad
키는 루트 .env 의 ANTHROPIC_API_KEY 를 읽는다 (출력하지 않음).
"""
import argparse
import importlib.util
import json
import os
import sys
import time
import types
from collections import Counter
from pathlib import Path

HERE = Path(__file__).resolve().parent
SRC = HERE / "azuki_src"
ROOT = HERE.parents[1]

MODEL = "claude-sonnet-4-6"
MAX_TOKENS = 64000
PRICE_IN, PRICE_OUT = 3.0, 15.0
UPPER = 3                      # 아즈키 UPPER_LIMIT 과 같음: 호출 최대 3번
RUN_CAP = 3.0                  # $ — 넘으면 다음 호출 안 함
TOTAL_CAP = 8.0                # $ — 이 폴더 calls.jsonl 합계가 넘으면 시작 안 함


# ---------- 아즈키 모듈 불러오기 (실험과 관계없는 import 만 대역) ----------
def load_azuki():
    for name in ("langchain_anthropic", "langgraph.checkpoint.postgres", "mcp_call"):
        m = types.ModuleType(name)
        m.ChatAnthropic = m.PostgresSaver = m.call_mcp_tool = object
        sys.modules[name] = m
    os.environ.setdefault("DB_URL", "unused")
    os.environ["STAFF_FILE"] = str(SRC / "staff_data.json")
    spec = importlib.util.spec_from_file_location("azuki", SRC / "prototype_mcp.py")
    az = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(az)
    return az


AZ = load_azuki()
STORE = AZ.STORE_SETTINGS[101]
STAFF = AZ.llm_all_staff            # 이름 뺀 데이터 (아즈키와 같음)
DATES = AZ.all_dates()
TIMES = [AZ.hour_miniute(m) for m in range(8 * 60, 22 * 60 + 31, 30)]


# ---------- 프롬프트 ----------
def base_prompt_parts():
    rules = AZ.rules.split("【出力形式】")[0]   # 출력 형식은 구조화 출력이 맡음
    days = AZ.make_days_text(STORE["shain_off_days"])
    days = "\n".join(l for l in days.split("\n") if "出力する前に" not in l) + "\n"
    head = AZ.make_headcount_text(STORE["min_headcount"])
    head = (head.replace("(必ず守る)", "(できるだけ守る目標。検査では警告だけ)")
                .replace("- 出られる人が足りなくて、どうしても守れない日は、守れなくてよい。その日は notes に書くこと。\n",
                         "- 出られる人が足りない時間帯は、無理に合わせず shortages に書くこと。\n"))
    way = ("\n【進め方】\n"
           "- まず案を出すこと。完璧に合わせようと長く考えない。検査はコードが行い、見つかった問題は次の回に伝える。\n"
           "- 埋められない所(人数・資格者が足りない時間帯)は、無理に埋めず shortages に書くこと。\n"
           "- 出力は指定の JSON の形だけ。説明文・下書きは書かない。\n")
    if ARGS.cond.endswith("_order"):  # 11/08: 막힌 곳(마감 자격 사원 × 정확히 21일)에 푸는 순서를 줌
        way += ("\n【解き方の順番】\n"
                "1. まず30日分の閉店(22:00〜22:30)を決める。資格者(上の資格のルールの qualification)の社員を、毎日1人ずつ入れる。資格者の社員どうしで回数がほぼ同じになるように分ける。\n"
                "2. 次に30日分の開店(08:00〜)を決める。社員1人以上・資格者1人以上にする。\n"
                "3. 社員それぞれの出勤日がちょうど決まりの日数になるように、残りの日と時間を決める。昼の時間帯に資格者の穴がないかもここで見る。\n"
                "4. 最後に、パート・バイトを申請どおりに入れる。\n")
    return rules + AZ.make_qualification_text(STORE["qualification_rules"]) + days + head + way


def precompute():
    """mix2 用: コードが計算した参考の事実。元の requests はそのまま渡す。"""
    out = {}
    for d in DATES:
        opts, qual = {}, []
        for s in STAFF:
            req = AZ.find_request(s, d)
            if s["employment"] == "社員":
                if req and (req.get("off") or req.get("paid_leave") is True):
                    continue
                win = f"{req['start']}~{req['end']}" if req and "start" in req else "08:00~22:30(自由)"
            else:
                if not (req and "start" in req):
                    continue
                win = f"{req['start']}~{req['end']}"
            opts[str(s["staff_id"])] = win
            if s.get("qualification") in STORE["qualification_rules"][0]["qualification"]:
                qual.append(s["staff_id"])
        bands = []
        for r in STORE["min_headcount"]:
            slots = range(AZ.to_min(r["start"]), AZ.to_min(r["end"]), 30)
            best = min(AZ.max_headcount(d, t, STAFF, r.get("exclude", [])) for t in slots)
            bands.append({"band": f"{r['start']}~{r['end']}", "min": r["min"], "max_possible": best})
        out[d] = {"出られる人と範囲": opts, "資格者で出られる人": qual, "最低人数の時間帯": bands}
    return out


def first_user(cond):
    data = "\n【スタッフのデータ(JSON)】\n" + json.dumps(STAFF, ensure_ascii=False)
    if cond.startswith("mix2"):  # mix2 · mix2_55 (11/12). mix1_nothink 은 mix1 과 같은 재료
        data += ("\n\n【コードが計算した参考(元のデータが基準)】\n"
                 "日付ごと: 出られる人と範囲(社員の自由は時間をあなたが決めてよい) / 資格者で出られる人 / "
                 "最低人数の時間帯で理論上いちばん多く出られる人数(max_possible < min なら埋められない)\n"
                 + json.dumps(precompute(), ensure_ascii=False))
    return data


def retry_user(cond, prev, problems):
    shown = problems[:100]           # 너무 길면 프롬프트가 불어남 — 100건까지 + 남은 수
    more = f"\n- (ほか{len(problems) - 100}件)" if len(problems) > 100 else ""
    return (first_user(cond) + "\n\n【前回の案】\n" + json.dumps(prev, ensure_ascii=False)
            + f"\n\n【前回の案の問題(全{len(problems)}件、今回は必ず直すこと)】\n" + "\n".join(f"- {p}" for p in shown) + more
            + "\n\n問題のある所以外は変えないこと。案全体をもう一度出すこと。")


def schema():
    item = {"type": "object", "additionalProperties": False,
            "properties": {"staff_id": {"type": "integer", "enum": [s["staff_id"] for s in STAFF]},
                           "date": {"type": "string", "enum": DATES},
                           "start": {"type": "string", "enum": TIMES}, "end": {"type": "string", "enum": TIMES}},
            "required": ["staff_id", "date", "start", "end"]}
    short = {"type": "object", "additionalProperties": False,
             "properties": {"date": {"type": "string"}, "start": {"type": "string"}, "end": {"type": "string"},
                            "reason": {"type": "string"}},
             "required": ["date", "start", "end", "reason"]}
    return {"type": "object", "additionalProperties": False,
            "properties": {"assignments": {"type": "array", "items": item},
                           "shortages": {"type": "array", "items": short},
                           "notes": {"type": "array", "items": {"type": "string"}}},
            "required": ["assignments", "shortages", "notes"]}


# ---------- 검사: 아즈키 함수 그대로, 최소 인원만 경고로 ----------
def check(draft):
    must = []
    must += AZ.check_coverage(draft, STAFF)
    must += AZ.check_qualification(draft, STAFF, STORE["qualification_rules"])
    must += AZ.check_requests(draft, STAFF)
    must += AZ.check_closing(draft, STAFF)
    must += AZ.check_shain_days(draft, STAFF, STORE["shain_off_days"])
    warn = AZ.check_headcount(draft, STAFF, STORE["min_headcount"])
    return must, warn


# ---------- 호출 ----------
_client = None


def model_price():
    # 11/08 mix1_55: 5.5 가격은 아즈키 11/07 자료(공식 요금표 인용) 입력 $2 · 출력 $10 — 이 세션에서 직접 확인 안 함
    return ("claude-sonnet-5-5", 2.0, 10.0) if "_55" in ARGS.cond else (MODEL, PRICE_IN, PRICE_OUT)


def cost_of(u):
    _, pin, pout = model_price()
    return (u["in"] + u["cache_read"] + u["cache_write"]) / 1e6 * pin + u["out"] / 1e6 * pout


def call(system, user, fake):
    if fake:
        a = [{"staff_id": s["staff_id"], "date": d, "start": "08:00", "end": "17:00"}
             for s in STAFF if s["employment"] == "社員" for d in DATES[:21]]
        if fake == "bad":
            a = a[:10]
        return {"assignments": a, "shortages": [], "notes": ["fake"]}, {"in": 0, "out": 0, "cache_read": 0, "cache_write": 0}, "fake", 0.0
    global _client
    if _client is None:
        import anthropic
        from dotenv import load_dotenv
        load_dotenv(ROOT / ".env")
        _client = anthropic.Anthropic()
    t0 = time.time()
    live = HERE / "thinking_live" / f"{ARGS.cond}_{os.getpid()}_{int(t0)}.txt"
    live.parent.mkdir(exist_ok=True)
    extra = ({"output_config": {"format": {"type": "json_schema", "schema": schema()}}}  # 5.5: 생각 설정 안 줌 = 아즈키(ChatAnthropic 기본)와 같게
             if "_55" in ARGS.cond else
             {"thinking": {"type": "disabled"}, "output_config": {"format": {"type": "json_schema", "schema": schema()}}}
             if "_nothink" in ARGS.cond else
             {"thinking": {"type": "adaptive"}, "output_config": {"effort": "medium", "format": {"type": "json_schema", "schema": schema()}}})
    with _client.messages.stream(model=model_price()[0], max_tokens=MAX_TOKENS, system=system,
                                 messages=[{"role": "user", "content": user}], **extra) as s, live.open("a") as lf:
        for ev in s:
            if ev.type == "content_block_delta" and getattr(ev.delta, "type", "") == "thinking_delta":
                lf.write(ev.delta.thinking); lf.flush()
        resp = s.get_final_message()
    sec = round(time.time() - t0, 1)
    u = resp.usage
    usage = {"in": u.input_tokens, "out": u.output_tokens,
             "cache_read": getattr(u, "cache_read_input_tokens", 0) or 0,
             "cache_write": getattr(u, "cache_creation_input_tokens", 0) or 0}
    with (HERE / "calls.jsonl").open("a") as f:
        f.write(json.dumps({"cond": ARGS.cond, "pid": os.getpid(), "stop": resp.stop_reason, "sec": sec, **usage,
                            "cost_usd": round(cost_of(usage), 4)}, ensure_ascii=False) + "\n")
    text = next((b.text for b in resp.content if b.type == "text"), None)
    if text is None or resp.stop_reason == "max_tokens":
        return None, usage, f"NO_OUTPUT:{resp.stop_reason}", sec
    try:
        return json.loads(text), usage, resp.stop_reason, sec
    except Exception as e:
        return None, usage, f"PARSE:{type(e).__name__}", sec


def spent_total():
    p = HERE / "calls.jsonl"
    return sum(json.loads(l)["cost_usd"] for l in p.read_text().splitlines() if l.strip()) if p.exists() else 0.0


def main():
    if not ARGS.fake and spent_total() >= TOTAL_CAP:
        sys.exit(f"TOTAL_CAP ${TOTAL_CAP} 도달 — 시작하지 않음")
    system = base_prompt_parts()
    attempts, usage, prev, spent = [], [], None, 0.0
    t_run = time.time()
    for n in range(UPPER):
        if spent >= RUN_CAP:
            attempts.append({"n": n, "stop": "RUN_CAP"}); break
        user = first_user(ARGS.cond) if prev is None else retry_user(ARGS.cond, prev, attempts[-1]["must_list"])
        out, u, note, sec = call(system, user, ARGS.fake)
        usage.append(u); spent += cost_of(u)
        if out is None:
            attempts.append({"n": n, "stop": note, "sec": sec}); break
        must, warn = check(out["assignments"])
        attempts.append({"n": n, "sec": sec, "out_tokens": u["out"], "cost": round(cost_of(u), 4), "note": note,
                         "n_assign": len(out["assignments"]), "n_must": len(must), "n_warn": len(warn),
                         "n_llm_shortages": len(out.get("shortages", [])), "must_list": must, "warn_list": warn})
        prev = out["assignments"]
        print(f"[{ARGS.cond}] 호출 {n + 1}: {sec}s · 출력 {u['out']} · ${cost_of(u):.3f} · 반드시 위반 {len(must)} · 경고 {len(warn)} · LLM shortages {len(out.get('shortages', []))}", flush=True)
        (HERE / f"draft_{ARGS.cond}_{n + 1}.json").write_text(json.dumps(out, ensure_ascii=False, indent=1))
        if not must:
            break
    ok = bool(attempts) and attempts[-1].get("n_must") == 0
    rec = {"cond": ARGS.cond, "fake": ARGS.fake, "ok": ok, "calls": len(usage), "total_sec": round(time.time() - t_run, 1),
           "cost_usd": round(sum(cost_of(u) for u in usage), 4),
           "attempts": [{k: v for k, v in a.items() if not k.endswith("_list")} for a in attempts],
           "last_must": attempts[-1].get("must_list", [])[:50], "last_warn": attempts[-1].get("warn_list", []),
           "impossible_by_code": [f"{d} {r['start']}~{r['end']} max {b}<{r['min']}" for d, r, b in AZ.impossible_cases(STORE["min_headcount"], STAFF)]}
    name = "results_fake.jsonl" if ARGS.fake else "results.jsonl"
    with (HERE / name).open("a") as f:
        f.write(json.dumps(rec, ensure_ascii=False) + "\n")
    print(json.dumps({k: rec[k] for k in ("cond", "ok", "calls", "total_sec", "cost_usd")}, ensure_ascii=False))


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--cond", choices=["mix1", "mix2", "mix1_nothink", "mix1_55", "mix1_nothink_order", "mix2_55"], required=True)
    ap.add_argument("--fake", choices=["ok", "bad"])
    ARGS = ap.parse_args()
    main()
