import os
from typing import TypedDict
from langgraph.graph import StateGraph, START, END
from langgraph.checkpoint.postgres import PostgresSaver
from dotenv import load_dotenv



# 0) 初期設定
load_dotenv()                 # 環境変数をロードする
DB_URL = os.environ["DB_URL"] # DBの接続URL
