"""Agent Server の入口。LangGraph本体は core/graph.py。保存先(checkpointer)は Agent Server が差し込む。"""
import os, sys
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
from core.graph import build_graph

graph = build_graph()
