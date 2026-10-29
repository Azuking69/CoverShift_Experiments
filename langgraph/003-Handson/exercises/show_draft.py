import json

with open("week1_draft.json", encoding="utf-8") as f:
    data = json.load(f)

with open("staff_data.json", encoding="utf-8") as f:
    STAFF = json.load(f)

id_to_name = {}
for s in STAFF:
    id_to_name[s["staff_id"]] = s["staff_name"]

for a in data["assignments"]:
    print(a["date"], id_to_name[a["staff_id"]], a["start"], a["end"])