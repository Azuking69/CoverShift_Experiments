import json
from prototype_01 import STAFF

d = json.load(open("month_draft.json", encoding="utf-8"))
a = d["assignments"]

for s in STAFF:
    if s["employment"] != "社員":
        continue
    mine = [x for x in a if x["staff_id"] == s["staff_id"]]
    days = sorted({x["date"] for x in mine})
    full = [r["date"] for r in s["requests"] if r.get("paid_leave") is True]
    half = [r for r in s["requests"] if r.get("paid_leave") == "half"]
    print(f"ID{s['staff_id']} 出た日={len(days)}日 / 全休の有給={full} / 全休の日に出た日={[x for x in days if x in full]}")
    for r in half:
        got = [(x["start"], x["end"]) for x in mine if x["date"] == r["date"]]
        print(f"   半休 {r['date']}: 申請={r['start']}〜{r['end']} / 実際={got}")

print("--- パート・バイトの半休 ---")
for s in STAFF:
    if s["employment"] == "社員":
        continue
    for r in s["requests"]:
        if r.get("paid_leave") == "half":
            got = [(x["start"], x["end"]) for x in a if x["staff_id"] == s["staff_id"] and x["date"] == r["date"]]
            print(f"ID{s['staff_id']} {r['date']}: 申請={r['start']}〜{r['end']} / 実際={got}")

print("--- LLM の notes ---")
for n in d.get("notes", []):
    print("-", n)