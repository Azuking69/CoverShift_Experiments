import asyncio, json, sys
from langgraph_sdk import get_client
from langgraph_sdk.schema import Command
URL=sys.argv[1]
async def main():
    c=get_client(url=URL)
    th=await c.threads.create()
    tid=th["thread_id"]
    # --- 項目1: interrupt → resume
    r=await c.runs.wait(tid,"covershift",input={"store_id":"S1","retry_count":0,"raw_input_names":{}})
    st=await c.threads.get_state(tid)
    print("[1] after run: next=",st["next"]," interrupts=",[i.get("value",{}).get("message") for t in st["tasks"] for i in t.get("interrupts",[])], " status=",st["values"].get("status"))
    r2=await c.runs.wait(tid,"covershift",command=Command(resume=True))
    st=await c.threads.get_state(tid)
    print("[1] after resume(True): next=",st["next"]," status=",st["values"].get("status"), " approved=",st["values"].get("manager_approved"))
    # 却下ルート
    th=await c.threads.create(); t2=th["thread_id"]
    await c.runs.wait(t2,"covershift",input={"store_id":"S1","retry_count":0,"raw_input_names":{}})
    await c.runs.wait(t2,"covershift",command=Command(resume=False))
    st=await c.threads.get_state(t2)
    print("[1] after resume(False): next=",st["next"]," status=",st["values"].get("status")," retry=",st["values"].get("retry_count"))
    # --- 項目3: 同じスレッドに同時に2本
    th=await c.threads.create(); t3=th["thread_id"]
    inp={"store_id":"S1","retry_count":0,"raw_input_names":{}}
    a=await c.runs.create(t3,"covershift",input=inp)
    try:
        b=await c.runs.create(t3,"covershift",input=inp)  # 既定の multitask_strategy
        print("[3] 2本目(既定): 受け付けられた id=",b["run_id"]," status=",b["status"])
    except Exception as e:
        print("[3] 2本目(既定): エラー:",type(e).__name__,str(e)[:200])
    try:
        b=await c.runs.create(t3,"covershift",input=inp,multitask_strategy="reject")
        print("[3] 2本目(reject): 受け付けられた status=",b["status"])
    except Exception as e:
        print("[3] 2本目(reject): エラー:",type(e).__name__,str(e)[:200])
    await asyncio.sleep(2)
    runs=await c.runs.list(t3)
    print("[3] runs:",[(r["run_id"][:8],r["status"]) for r in runs])
asyncio.run(main())
