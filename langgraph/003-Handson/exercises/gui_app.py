import time
import streamlit as st
from langgraph.checkpoint.postgres import PostgresSaver
from langgraph.types import Command
from prototype_01 import builder, DB_URL, id_to_name, STAFF


# 雇用の並び順(小さい順に表示する)
SPECIAL_QUAL = "薬剤師"          # 社員の次に出す資格。使わない業種は None
id_to_emp = {s["staff_id"]: s["employment"] for s in STAFF}
id_to_qual = {s["staff_id"]: s.get("qualification") for s in STAFF}

def group_no(staff_id):
    emp = id_to_emp[staff_id]
    if SPECIAL_QUAL and id_to_qual.get(staff_id) == SPECIAL_QUAL:
        if emp == "社員":
            return 1             # 薬剤師(社員)
        return 2                 # 薬剤師(パート・バイト)
    return {"社員": 0, "パート": 3, "バイト": 4}.get(emp, 9)


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
            {"雇用": id_to_emp.get(a["staff_id"]),
             "ID": a["staff_id"], 
             "資格": id_to_qual.get(a["staff_id"]),
             "名前": id_to_name.get(a["staff_id"], a["staff_id"]),
             "日付": a["date"], "開始": a["start"], "終了": a["end"]}
            for a in values["draft_store_shift"]
        ]
        rows.sort(key=lambda r: (group_no(r["ID"]), r["ID"], r["日付"], r["開始"]))        
        st.dataframe(rows)

        if st.button("承認"):
            start = time.time()
            for chunk in graph.stream(Command(resume=True), config, stream_mode="updates"):
                for node_name, update in chunk.items():
                    st.write(f"{node_name} が終わりました（{time.time() - start:.1f}秒）")
            st.session_state["stage"] = "done"
            st.write("確定しました")