import time
import streamlit as st
from langgraph.checkpoint.postgres import PostgresSaver
from langgraph.types import Command
from prototype_01 import builder, DB_URL, id_to_name

st.title("CoverShift シフト編成")

with PostgresSaver.from_conn_string(DB_URL) as saver:
    saver.setup()
    graph = builder.compile(checkpointer=saver)

    # --- 作成ボタン：グラフを最初から動かす ---
    if st.button("作成"):
        st.session_state["thread_id"] = f"gui_{int(time.time())}"
        st.session_state["stage"] = "waiting"
        config = {"configurable": {"thread_id": st.session_state["thread_id"]}}
        start = time.time()
        for chunk in graph.stream({"store_id": 101}, config, stream_mode="updates"):
            for node_name, update in chunk.items():
                st.write(f"{node_name} が終わりました（{time.time() - start:.1f}秒）")

    # --- 承認待ちのとき：シフト表と承認ボタンを出す ---
    if st.session_state.get("stage") == "waiting":
        config = {"configurable": {"thread_id": st.session_state["thread_id"]}}
        values = graph.get_state(config).values
        rows = [
            {"名前": id_to_name.get(a["staff_id"], a["staff_id"]),
             "日付": a["date"], "開始": a["start"], "終了": a["end"]}
            for a in values["draft_store_shift"]
        ]
        rows.sort(key=lambda r: (r["日付"], r["開始"]))
        st.dataframe(rows)

        if st.button("承認"):
            start = time.time()
            for chunk in graph.stream(Command(resume=True), config, stream_mode="updates"):
                for node_name, update in chunk.items():
                    st.write(f"{node_name} が終わりました（{time.time() - start:.1f}秒）")
            st.session_state["stage"] = "done"
            st.write("確定しました")