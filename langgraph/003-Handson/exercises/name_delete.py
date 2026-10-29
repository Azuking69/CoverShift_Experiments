from staff_data import STAFF

# 名前とIDの対応表を作成する
id_to_name = {}

for s in STAFF:
    id_to_name[s["staff_id"]] = s["staff_name"]
print(id_to_name)


# 名前からIDを削除する関数
no_name = []

for s in STAFF:
    item = {}
    for key, value in s.items():
        if key != "staff_name":
            item[key] = value

    no_name.append(item)
print(no_name)