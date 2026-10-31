import json
from staff_data import STAFF

with open("staff_data.json", "w", encoding="utf-8") as f:
    json.dump(STAFF, f, ensure_ascii=False, indent=2)