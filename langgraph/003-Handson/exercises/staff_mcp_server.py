try:
    from mcp.server.mcpserver import MCPServer            # mcp 2.x
except ImportError:
    from mcp.server.fastmcp import FastMCP as MCPServer   # mcp 1.x

import json
from pathlib import Path

STAFF_FILE = Path(__file__).parent / "staff_data.json"   # このファイルと同じフォルダのJSON

mcp = MCPServer("covershift-staff")                       # ① サーバーに名前をつける


def load_staff_without_names() -> list:
    """② 名前(staff_name)を落としたスタッフのリストを返す"""
    with open(STAFF_FILE, encoding="utf-8") as f:
        staff = json.load(f)
    return [{key: value for key, value in s.items() if key != "staff_name"} for s in staff]


@mcp.tool()                                               # ③ 付けると「道具」として公開される
def get_staff_availability() -> dict:                     # ④ 関数名＝道具名
    """全スタッフのデータ（名前なし）を返す"""
    return {"staff": load_staff_without_names()}


if __name__ == "__main__":
    mcp.run()                                             # ⑤ stdioで待ち受ける