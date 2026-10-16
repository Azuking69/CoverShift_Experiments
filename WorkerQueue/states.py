"""状態遷移表。「いまの状態」＋「届いた合図」→「次の状態」。

折衷案の consumer Lambda が持つ「状態遷移表」に当たる。
表にない組み合わせ（古い合図・二重に届いた合図）は、無視される。
"""

TRANSITIONS = {
    ("collecting", "deadline"): "reviewing",         # 締切が来た → 検討へ
    ("reviewing", "review_done"): "waiting_approval",  # 検討が終わった → 承認待ちへ
    ("waiting_approval", "approved"): "finished",    # 管理者が承認 → 終了
}


def next_state(state: str, event: str):
    """次の状態を返す。表にない組み合わせなら None（＝何もしない）。"""
    return TRANSITIONS.get((state, event))
