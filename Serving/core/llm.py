"""Claudeの呼び出し。環境変数 ANTHROPIC_API_KEY があれば本物のClaude API、なければ偽物（固定文）。
どちらの場合も、**送る直前の本文**を outbound.log に追記する（E4：実名が出ていないかの確認用）。
書き込めない環境（AgentCore Runtime）では /tmp に書き、標準出力にも「OUTBOUND {json}」の形で出す。
モデル名は環境変数 CLAUDE_MODEL（既定 claude-haiku-5-5。**すべて小文字**。大文字が混ざる（例 claude-Haiku-5-5）とエラーになる）。
APIがエラーを返したときは、原因を outbound.log に kind=real_error で残す。
"""
import json, os, time


def _load_dotenv() -> None:
    """ルートの .env（KEY=VALUE の行）を読む。すでに設定済みの環境変数は上書きしない。"""
    path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), ".env")
    if not os.path.exists(path):
        return
    for line in open(path, encoding="utf-8-sig"):
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        k, v = k.strip(), v.strip().strip('"').strip("'")
        if k and v and k not in os.environ:
            os.environ[k] = v


_load_dotenv()

LOG = os.getenv("OUTBOUND_LOG", os.path.join(os.getcwd(), "outbound.log"))
MODEL = os.getenv("CLAUDE_MODEL", "claude-haiku-5-5")
SYSTEM = ("あなたはドラッグストアのシフト案を、店長向けに短く説明する補助役です。"
          "入力の『スタッフA』などは仮の記号です。実名を推測したり書いたりしないこと。説明は日本語で5行以内。")


def _log(kind: str, body: dict) -> None:
    line = json.dumps({"t": time.time(), "kind": kind, **body}, ensure_ascii=False)
    try:
        with open(LOG, "a", encoding="utf-8") as f:
            f.write(line + "\n")
    except OSError:
        # AgentCore Runtime などは、コードの置き場（/var/task）に書けない（2026-10-14 に確認）。
        # /tmp に書き、標準出力にも出す（CloudWatch のログで、送信内容を確認できるようにする）。
        import tempfile
        with open(os.path.join(tempfile.gettempdir(), "outbound.log"), "a", encoding="utf-8") as f:
            f.write(line + "\n")
        print("OUTBOUND " + line, flush=True)


def call_claude(prompt: str) -> str:
    key = os.getenv("ANTHROPIC_API_KEY")
    if not key:
        _log("fake", {"prompt": prompt})
        return "（偽のClaudeの固定文）シフト案を確認しました。"
    import anthropic
    req = {"model": MODEL, "max_tokens": 400, "system": SYSTEM,
           "messages": [{"role": "user", "content": prompt}]}
    _log("real", {"request": req})            # 送る直前の本文をそのまま記録
    try:
        resp = anthropic.Anthropic(api_key=key).messages.create(**req)
    except Exception as e:  # サーバーは詳細を隠す("An internal error occurred")ので、原因をログに残す（鍵は含めない）
        _log("real_error", {"type": type(e).__name__, "status": getattr(e, "status_code", None),
                            "message": str(e).replace(key, "***")[:400]})
        raise
    text = "".join(b.text for b in resp.content if getattr(b, "type", "") == "text")
    _log("real_usage", {"input_tokens": resp.usage.input_tokens, "output_tokens": resp.usage.output_tokens})
    return text