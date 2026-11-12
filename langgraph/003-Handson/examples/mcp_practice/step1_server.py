try:
    from mcp.server.mcpserver import MCPServer

except ImportError:
    from mcp.server.fastmcp import FastMCP as MCPServer

# 1) MCPServer: サーバーを作成する
mcp = MCPServer("step1") 


# 2) ツールの登録
@mcp.tool()
def add(a: int, b:int) -> int:
    """2つの整数を足す"""
    return a + b


# 3) サーバーの起動
if __name__ == "__main__":
    mcp.run(transport="stdio")  # 標準入出力で通信する