try:
    from mcp.server.mcpserver import MCPServer

except ImportError:
    from mcp.server.fastmcp import FastMCP as MCPServer

import json

mcp = MCPServer("staff")

@mcp.tool()
def get_staff_availablility() -> dict:
    """全スタッフのデータ（名前なし）を返す"""
    with open("staff_data.json", encoding="utf-8") as f:
        staff = json.load(f)
        return {
            "staff": [
                {key: value for key, value in staffs.items() if key != "staff_name"} # staff_name以外
                for staffs in staff
            ]
        }


if __name__ == "__main__":
    mcp.run()