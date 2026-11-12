try:
    from mcp.server.mcpserver import MCPServer

except ImportError:
    from mcp.server.fastmcp import FastMCP as MCPServer

import json

mcp = MCPServer("staff")

@mcp.tool()
def get_staff(staff_id: int) -> dict:
    """指定されたIDのスタッフのデータ（名前なし）を返す"""
    with open("staff_data.json", encoding="utf-8") as f:
        for staff in json.load(f):
            if staff ["staff_id"] == staff_id:
                return {key: value for key, value in staff.items() if key != "staff_name"} # staff_name以外
    raise ValueError(f"staff_id={staff_id} のスタッフは存在しません")


if __name__ == "__main__":
    mcp.run()