try:
    from mcp.server.mcpserver import MCPServer

except ImportError:
    from mcp.server.fastmcp import FastMCP as MCPServer

# 1) MCPServer: サーバーを作成する
mcp = MCPServer("step1") 


# 2) ツールの登録
@mcp.tool()
def shift_hours(start: str, end: str, break_minutes: int = 60) -> float:
    """シフトの時間を計算する"""
    # map(): 反復可能なオブジェクトの各要素に関数を適用する
    start_hour, start_minute = map(int, start.split(":"))
    end_hour, end_minute = map(int, end.split(":"))
    total = (end_hour * 60 + end_minute) - (start_hour * 60 + start_minute) - break_minutes
    return total / 60


# 3) サーバーの起動
if __name__ == "__main__":
    mcp.run(transport="stdio")  # 標準入出力で通信する