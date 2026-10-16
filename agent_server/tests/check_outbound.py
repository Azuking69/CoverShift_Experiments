"""E4: 送信ログに、ダミー入力の実名が出ていないか確認する。 python tests/check_outbound.py outbound.log"""
import os, sys
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
from core.fixtures import STAFF
log = open(sys.argv[1] if len(sys.argv) > 1 else "outbound.log", encoding="utf-8").read()
lines = [l for l in log.splitlines() if l.strip()]
bad = [s["name"] for s in STAFF if s["name"] in log]
print(f"送信 {len(lines)} 回 / 実名の漏れ: {'あり ' + str(bad) if bad else 'なし'}")
sys.exit(1 if bad else 0)
