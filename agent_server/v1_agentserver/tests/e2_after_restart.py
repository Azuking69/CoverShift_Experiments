import asyncio, sys
from langgraph_sdk import get_client
from langgraph_sdk.schema import Command
async def main():
    c=get_client(url=(sys.argv[1] if len(sys.argv)>1 else "http://127.0.0.1:2024"))
    tb=open("tid_int.txt").read(); ta=open("tid_mid.txt").read(); ra=open("rid_mid.txt").read()
    for name,t in (("B(承認待ちで落とした)",tb),("A(計算中に落とした)",ta)):
        try:
            th=await c.threads.get(t); st=await c.threads.get_state(t)
            print(name,"thread status=",th["status"]," next=",st["next"]," status値=",st["values"].get("status"))
        except Exception as e:
            print(name,"取得エラー:",type(e).__name__,str(e)[:150])
    try:
        r=await c.runs.get(ta,ra); print("A run status=",r["status"])
    except Exception as e: print("A run取得エラー:",type(e).__name__,str(e)[:150])
    # B を再開できるか
    try:
        await c.runs.wait(tb,"covershift",command=Command(resume=True))
        st=await c.threads.get_state(tb); print("B 再開後: status値=",st["values"].get("status"))
    except Exception as e: print("B再開エラー:",type(e).__name__,str(e)[:150])
    # A をもう一度走らせたら?
    try:
        await c.runs.wait(ta,"covershift",input=None)
        st=await c.threads.get_state(ta); print("A input=Noneで再走: next=",st["next"]," status値=",st["values"].get("status"))
    except Exception as e: print("A再走エラー:",type(e).__name__,str(e)[:150])
asyncio.run(main())
