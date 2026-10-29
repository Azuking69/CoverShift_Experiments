import json

with open("week1_draft.json", encoding="utf-8") as f:
    data = json.load(f)

# # ↓ テスト用（確認したら消す）
# data["assignments"] = [a for a in data["assignments"] if not (a["date"] == "2026-11-03" and a["staff_id"] == 1)]

with open("staff_data.json", encoding="utf-8") as f:
    STAFF = json.load(f)

id_to_emp = {}
for s in STAFF:
    id_to_emp[s["staff_id"]] = s["employment"]      # 社員・パート・バイトの区別が入っているキー

def to_min(t):                                # "13:30" → 810(0時からの分)
    h, m = t.split(":")
    return int(h) * 60 + int(m)

problems = []
for day in range(1, 8):                       # 11/1〜11/7
    date = f"2026-11-{day:02d}"
    for t in range(8 * 60, 22 * 60 + 30, 30): # 08:00, 08:30, ... 22:00(30分ごと)
        count = 0
        for a in data["assignments"]:
            if a["date"] == date and id_to_emp[a["staff_id"]] == "社員" and to_min(a["start"]) <= t < to_min(a["end"]):
                count += 1
        if count == 0:
            problems.append(f"{date} {t // 60:02d}:{t % 60:02d} 社員がいません")

print(problems if problems else "問題なし")