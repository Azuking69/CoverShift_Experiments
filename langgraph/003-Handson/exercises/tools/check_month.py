import json
from collections import Counter

with open("staff_data.json", encoding="utf-8") as f:
    STAFF = json.load(f)
with open("month_draft.json", encoding="utf-8") as f:
    data = json.load(f)

by_id = {s["staff_id"]: s for s in STAFF}

# 1) 希望（requests）の日付の範囲
dates = sorted({r["date"] for s in STAFF for r in s["requests"]})
print("希望の日付:", dates[0], "〜", dates[-1], f"（{len(dates)}日分）")

# 2) 編成案の日付の範囲
cnt = Counter(a["date"] for a in data["assignments"])
print("編成案の日数:", len(cnt), "／最初:", min(cnt), "／最後:", max(cnt))

# 3) パート・バイトが、希望のない日に入っていないか（ルール3）
bad = []
for a in data["assignments"]:
    s = by_id[a["staff_id"]]
    if s["employment"] != "社員":
        req_days = {r["date"] for r in s["requests"] if not r.get("off")}
        if a["date"] not in req_days:
            bad.append((s["staff_name"], a["date"]))

# 4) 社員の希望（休み・時間）が守られているか
for s in STAFF:
    if s["employment"] != "社員":
        continue
    for r in s["requests"]:
        mine = [a for a in data["assignments"] if a["staff_id"] == s["staff_id"] and a["date"] == r["date"]]
        if r.get("off") and mine:
            print("希望休が通っていない:", s["staff_name"], r["date"])
        elif not r.get("off") and not any(a["start"] == r["start"] and a["end"] == r["end"] for a in mine):
            print("希望の時間と違う:", s["staff_name"], r["date"], r["start"], r["end"], [(a["start"], a["end"]) for a in mine])
print("ルール3の違反:", len(bad), "件")
print(bad[:10])