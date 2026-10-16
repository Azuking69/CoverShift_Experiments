import asyncio, sys
from langgraph_sdk import get_client
async def main():
    c=get_client(url=(sys.argv[1] if len(sys.argv)>1 else "http://127.0.0.1:2024"))
    # B: 承認待ちまで進める
    tb=(await c.threads.create())["thread_id"]
    await c.runs.wait(tb,"covershift",input={"store_id":"S1","retry_count":0,"raw_input_names":{}})
    open("tid_int.txt","w").write(tb)
    # A: 計算の途中(solverのsleep中)
    ta=(await c.threads.create())["thread_id"]
    r=await c.runs.create(ta,"covershift",input={"store_id":"S1","retry_count":0,"raw_input_names":{}})
    open("tid_mid.txt","w").write(ta); open("rid_mid.txt","w").write(r["run_id"])
    print("A started",r["status"])
asyncio.run(main())
