# ==================================================================
# 共通クライアント
# ==================================================================

import sys, json, asyncio
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client


# 非同期関数: call -> サーバーを呼び出す
async def call(server_file, tool=None, args=None):
    # StdioServerParameters: 標準入出力サーバーのパラメータ
    # command: サーバーを起動するコマンド
    # args: サーバーに渡す引数のリスト
    params = StdioServerParameters(command=sys.executable, args=[server_file])

    # stdio_client: 標準入出力クライアントを作成する非同期コンテキストマネージャ
    async with stdio_client(params) as (read, write):
        # ClientSession: クライアントセッションを作成する非同期コンテキストマネージャ
        async with ClientSession(read, write) as session:
            await session.initialize()

            # list_tools: 利用可能なツールの一覧を取得する
            tools = await session.list_tools()
            print("見えるツール: ", [tool.name for tool in tools.tools])

            if tool:
                # call_tool: 指定されたツールを呼び出す
                res = await session.call_tool(tool, args or {})
                # getattr: この名前の中身を取り出す
                print("エラーかどうか: ", getattr(res, "is_error", getattr(res, "isError", None)))

                for contents in res.content:
                    print("結果: ", getattr(contents, "text", contents))


# 引数の読み方: 2通りに対応する
# ① JSON 1個:  '{"a": 2, "b": 3}'   (PowerShellでは " が消えることがある)
# ② 名前=値:    a=2 b=3              (クォート不要。Windowsではこちらが安全)
def parse_args(words):
    if not words:
        return {}
    # lstrip(): 先頭の空白を削除する
    # startswith(): 文字列が指定した文字列で始まるかどうかを判定する
    if len(words) == 1 and words[0].lstrip().startswith("{"):
        return json.loads(words[0])
    result = {}

    for word in words:
        # partition(): 文字列を指定した区切り文字で分割する
        name, _, value = word.partition("=")
        try:
            # json.loads(): JSON文字列をPythonのデータ構造に変換する
            result[name] = json.loads(value)   # 2 → 数字
        # JSONDecodeError: JSONのデコードに失敗した場合の例外
        except json.JSONDecodeError:
            result[name] = value               # 09:00 など → 文字のまま
    return result


# main -> メイン処理
if __name__ == "__main__":
    # sys.argv: コマンドで打った言葉を、順番に入れたリスト
    file = sys.argv[1]
    tool = sys.argv[2] if len(sys.argv) > 2 else None
    args = parse_args(sys.argv[3:])
    asyncio.run(call(file, tool, args))