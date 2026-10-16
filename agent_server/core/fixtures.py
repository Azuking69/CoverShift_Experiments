"""試験用のダミー入力（実在の人物ではない）。名前は、ソルバーとAIには渡さず、記号(スタッフA…)に置き換える。"""
STAFF = [
    {"id": 1, "name": "山田太郎", "unpreferred_days": [0, 1]},
    {"id": 2, "name": "佐藤花子", "unpreferred_days": [2]},
    {"id": 3, "name": "鈴木一郎", "unpreferred_days": [3, 4]},
    {"id": 4, "name": "高橋美咲", "unpreferred_days": []},
    {"id": 5, "name": "田中健",   "unpreferred_days": [5, 6]},
    {"id": 6, "name": "伊藤さくら", "unpreferred_days": [0]},
]
DAYS = 7
REQUIREMENTS = [{"早番": 2, "遅番": 1} for _ in range(DAYS)]   # 日ごとの最低人数
WEIGHTS = {"respect_wishes": 0.3}
