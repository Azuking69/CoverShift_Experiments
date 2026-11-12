try:
    from mcp.server.mcpserver import MCPServer

except ImportError:
    from mcp.server.fastmcp import FastMCP as MCPServer

import json


# 1) MCPServer: サーバーを作成する
mcp = MCPServer("step3")  


# 2) ツールの登録
@mcp.tool()
def get_staff_count() -> int:
    """スタッフの人数を返す"""
    # open(): ファイルを開く
    with open("staff_data.json", encoding="utf-8") as file:
        # json.load(): JSON文字列をPythonのデータ構造に変換する
        return len(json.load(file))

@mcp.tool()
def get_staff_list() -> list:
    """スタッフのリストを返す"""
    with open("staff_data.json", encoding="utf-8") as file:
        return json.load(file)


# 3) サーバーの起動
if __name__ == "__main__":
    mcp.run(transport="stdio")  # 標準入出力で通信する