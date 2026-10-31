from langgraph.checkpoint.postgres import PostgresSaver
from langgraph.types import Command
from prototype_01 import builder, DB_URL

with PostgresSaver.from_conn_string(DB_URL) as saver:
    graph = builder.compile(checkpointer=saver)
    config = {"configurable": {"thread_id": "test_14"}}

    for chunk in graph.stream(Command(resume=True), config, stream_mode="updates"):
        print(chunk)