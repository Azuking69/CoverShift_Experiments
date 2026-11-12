import sys, json
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client


# MCPサーバーのツールを呼び出す
# async: 非同期関数を定義するためのキーワード
async def call_mcp_tool(server_file: str, tool: str, args: dict | None = None) -> dict:
    """MCPサーバーのツールを呼び出す"""
    params = StdioServerParameters(
        command = sys.executable,  # Pythonの実行ファイルのパス
        args = [server_file],  # サーバーのファイルパス
    )
    async with stdio_client(params) as (read, write):            # ① サーバーを子プロセスで起動
        async with ClientSession(read, write) as session:        # ② 会話の場を作る
            await session.initialize()                           # ③ 最初のあいさつ
            res = await session.call_tool(tool, args or {})      # ④ ツールを呼ぶ

            if getattr(res, "is_error", False):
                raise RuntimeError(f"MCPツール{tool}が失敗")

            if len(res.content) != 1:
                raise RuntimeError(f"結果が１個のテキストデータではありません")
            return json.loads(res.content[0].text)            