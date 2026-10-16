"""AWS で確かめる：EventBridge Scheduler と SQS FIFO（CloudShell で実行する）。

使い方（AWS コンソール右上の CloudShell を開いて、このファイルをアップロードしてから）:
    python3 aws_check.py run                      # 作る → 確かめる → 自動で片付ける（約5〜8分）
    python3 aws_check.py run --region ap-northeast-1
    python3 aws_check.py cleanup                  # 途中で止まったときの片付け

作るもの（名前はすべて wq- で始まる。終わると自動で消える）:
    SQS FIFO キュー wq-test.fifo / Scheduler の予約グループ wq-test / IAM ロール wq-scheduler-role

確かめること:
    A. 一回限りの予約（at）は、指定した時刻から、どのくらい遅れて SQS に届くか
    B. SQS FIFO：同じ案件（グループ）は1つずつ、違う案件は並んで届くか
    C. 過ぎた時刻の予約を作ると、どうなるか
費用: Scheduler は月1,400万回、SQS は月100万リクエストまで無料。この確認は数百回未満。
"""
import argparse
import json
import statistics
import sys
import time
import uuid
from datetime import datetime, timedelta, timezone

import boto3
from botocore.exceptions import ClientError

QUEUE = "wq-test.fifo"
GROUP = "wq-test"
ROLE = "wq-scheduler-role"
N_SCHEDULES = 12


def now():
    return datetime.now(timezone.utc)


def hms(dt):
    return dt.strftime("%H:%M:%S") + f".{dt.microsecond // 1000:03d}"


def clients(region):
    return (boto3.client("sqs", region_name=region), boto3.client("scheduler", region_name=region),
            boto3.client("iam", region_name=region))


# ---------------------------------------------------------------- 作る / 片付ける
def setup(region):
    sqs, sch, iam = clients(region)
    q = sqs.create_queue(QueueName=QUEUE, Attributes={
        "FifoQueue": "true", "ContentBasedDeduplication": "true", "VisibilityTimeout": "30"})["QueueUrl"]
    arn = sqs.get_queue_attributes(QueueUrl=q, AttributeNames=["QueueArn"])["Attributes"]["QueueArn"]
    trust = {"Version": "2012-10-17", "Statement": [{"Effect": "Allow",
             "Principal": {"Service": "scheduler.amazonaws.com"}, "Action": "sts:AssumeRole"}]}
    try:
        role_arn = iam.create_role(RoleName=ROLE, AssumeRolePolicyDocument=json.dumps(trust))["Role"]["Arn"]
        fresh = True
    except ClientError as e:
        if e.response["Error"]["Code"] != "EntityAlreadyExists":
            raise
        role_arn = iam.get_role(RoleName=ROLE)["Role"]["Arn"]
        fresh = False
    iam.put_role_policy(RoleName=ROLE, PolicyName="send", PolicyDocument=json.dumps({
        "Version": "2012-10-17",
        "Statement": [{"Effect": "Allow", "Action": "sqs:SendMessage", "Resource": arn}]}))
    try:
        sch.create_schedule_group(Name=GROUP)
    except ClientError as e:
        if e.response["Error"]["Code"] != "ConflictException":
            raise
    if fresh:
        time.sleep(15)  # IAM ロールが使えるようになるまで少し待つ
    return q, arn, role_arn


def cleanup(region):
    sqs, sch, iam = clients(region)
    out = []

    def attempt(label, fn):
        try:
            fn()
            out.append(f"  消した: {label}")
        except ClientError as e:
            code = e.response["Error"]["Code"]
            if code in ("ResourceNotFoundException", "NoSuchEntity", "AWS.SimpleQueueService.NonExistentQueue",
                        "QueueDoesNotExist"):
                out.append(f"  もうない: {label}")
            else:
                out.append(f"  消せなかった: {label} ({code}) ← 手で消してください")

    try:
        names = [s["Name"] for s in sch.list_schedules(GroupName=GROUP).get("Schedules", [])]
    except ClientError:
        names = []
    for n in names:
        attempt(f"予約 {n}", lambda n=n: sch.delete_schedule(Name=n, GroupName=GROUP))
    attempt(f"予約グループ {GROUP}", lambda: sch.delete_schedule_group(Name=GROUP))
    attempt(f"SQS キュー {QUEUE}", lambda: sqs.delete_queue(QueueUrl=sqs.get_queue_url(QueueName=QUEUE)["QueueUrl"]))

    def del_role():
        try:
            iam.delete_role_policy(RoleName=ROLE, PolicyName="send")
        except ClientError:
            pass
        iam.delete_role(RoleName=ROLE)
    attempt(f"IAM ロール {ROLE}", del_role)
    print("\n".join(out))


# ---------------------------------------------------------------- A. 締切の発火
def test_a(region, q, arn, role_arn, wait=True):
    sqs, sch, _ = clients(region)
    base = (now() + timedelta(minutes=3)).replace(second=0, microsecond=0)  # 3分後あたりの「ちょうど分」
    planned = {}
    for i in range(N_SCHEDULES):
        t = base + timedelta(seconds=20 * i)  # :00 :20 :40 を交ぜる
        name = f"wq-t{i:02d}"
        create_sched(sch, sched_args(name, t, arn, role_arn, f"case-{i % 4 + 1}", i))
        planned[name] = t
    print(f"  予約を{N_SCHEDULES}件作った（{hms(base)}〜{hms(base + timedelta(seconds=20 * (N_SCHEDULES - 1)))} UTC）")

    past = None
    pt = now() - timedelta(minutes=2)
    try:
        create_sched(sch, sched_args("wq-past", pt, arn, role_arn, "case-1", 99))
        past = {"created": True, "planned": pt}
        planned["wq-past"] = pt
        print("  過ぎた時刻の予約: 作成できた（届くかどうかは、このあと見る）")
    except ClientError as e:
        past = {"created": False, "error": f'{e.response["Error"]["Code"]}: {e.response["Error"]["Message"]}'}
        print(f"  過ぎた時刻の予約: 作成できなかった → {past['error']}")

    got = {}
    if wait:
        deadline = base + timedelta(seconds=20 * N_SCHEDULES) + timedelta(seconds=150)
        print(f"  届くのを待つ（最長 {hms(deadline)} UTC まで。キュー待ち受け中…）")
        while len(got) < len(planned) and now() < deadline:
            r = sqs.receive_message(QueueUrl=q, MaxNumberOfMessages=10, WaitTimeSeconds=20,
                                    AttributeNames=["SentTimestamp"])
            for m in r.get("Messages", []):
                body = json.loads(m["Body"])
                sent = datetime.fromtimestamp(int(m["Attributes"]["SentTimestamp"]) / 1000, timezone.utc)
                got[body["name"]] = {"sent": sent, "body": body}
                sqs.delete_message(QueueUrl=q, ReceiptHandle=m["ReceiptHandle"])
    rows, delays = [], []
    for name, t in planned.items():
        g = got.get(name)
        d = (g["sent"] - t).total_seconds() if g else None
        if g and name != "wq-past":
            delays.append(d)
        rows.append({"name": name, "planned": hms(t), "arrived": hms(g["sent"]) if g else None,
                     "delay_sec": round(d, 2) if d is not None else None})
    return {"rows": rows, "delays": delays, "past": past,
            "missing": [n for n in planned if n not in got]}


def create_sched(sch, args):
    try:
        return sch.create_schedule(**args)
    except Exception as e:  # boto3 が古くて ActionAfterCompletion を知らない場合は、付けずに作る（終了後は cleanup が消す）
        if "ActionAfterCompletion" in str(e) and "Unknown parameter" in str(e):
            args = {k: v for k, v in args.items() if k != "ActionAfterCompletion"}
            return sch.create_schedule(**args)
        raise


def sched_args(name, t, arn, role_arn, group, i):
    args = dict(Name=name, GroupName=GROUP,
                ScheduleExpression="at(" + t.strftime("%Y-%m-%dT%H:%M:%S") + ")",
                ScheduleExpressionTimezone="UTC", FlexibleTimeWindow={"Mode": "OFF"},
                Target={"Arn": arn, "RoleArn": role_arn,
                        "Input": json.dumps({"name": name, "case": group, "n": i}),
                        "SqsParameters": {"MessageGroupId": group}})
    args["ActionAfterCompletion"] = "DELETE"
    return args


# ---------------------------------------------------------------- B. FIFO の順番と並行
def test_b(region, q):
    sqs = boto3.client("sqs", region_name=region)
    for g, items in (("case-A", ["a1", "a2", "a3"]), ("case-B", ["b1", "b2"])):
        for it in items:
            sqs.send_message(QueueUrl=q, MessageBody=json.dumps({"id": it}), MessageGroupId=g,
                             MessageDeduplicationId=f"{it}-{uuid.uuid4().hex}")
    obs = {}

    def one():
        r = sqs.receive_message(QueueUrl=q, MaxNumberOfMessages=1, WaitTimeSeconds=3, VisibilityTimeout=20)
        ms = r.get("Messages", [])
        return (json.loads(ms[0]["Body"])["id"], ms[0]["ReceiptHandle"]) if ms else (None, None)

    first, rh1 = one()          # 1回目：案件Aの先頭 a1 のはず
    second, rh2 = one()         # 2回目：a1 を処理中なので、a2 ではなく別の案件 b1 のはず
    third, _ = one()            # 3回目：A も B も処理中。何も来ないはず
    obs["1回目に届いた"] = first
    obs["2回目に届いた（1回目が処理中のまま）"] = second
    obs["3回目に届いた（A・B とも処理中のまま）"] = third
    if rh1:
        sqs.delete_message(QueueUrl=q, ReceiptHandle=rh1)   # a1 を完了
    after, rh3 = one()
    obs["a1 を完了したあとに届いた"] = after
    # 後片付け：残りを全部消費
    for rh in (rh2, rh3):
        if rh:
            sqs.delete_message(QueueUrl=q, ReceiptHandle=rh)
    for _ in range(6):
        x, rh = one()
        if rh:
            sqs.delete_message(QueueUrl=q, ReceiptHandle=rh)
    ok = (first == "a1" and second == "b1" and third is None and after == "a2")
    return {"obs": obs, "expected_pattern": ok}


# ---------------------------------------------------------------- 実行
def report(a, b, region):
    print("\n==================== 結果 ====================")
    print(f"リージョン: {region}")
    print("\n[A] 一回限りの予約が SQS に届いた時刻（UTC）")
    print(f"  {'予約':<9}{'指定した時刻':<14}{'届いた時刻':<15}遅れ(秒)")
    for r in a["rows"]:
        print(f"  {r['name']:<9}{r['planned']:<14}{(r['arrived'] or '届かなかった'):<15}"
              f"{'' if r['delay_sec'] is None else r['delay_sec']}")
    d = a["delays"]
    if d:
        print(f"  → 遅れ：最小 {min(d):.1f} 秒 / 中央値 {statistics.median(d):.1f} 秒 / 最大 {max(d):.1f} 秒"
              f"（{len(d)}件。1件でも早く届いたら、負の値）")
    if a["missing"]:
        print(f"  → 届かなかった予約: {a['missing']}")
    print("\n[C] 過ぎた時刻の予約")
    p = a["past"]
    print("  " + (f"作成できなかった: {p['error']}" if not p["created"] else "作成できた。結果は上の wq-past の行を見る"))
    print("\n[B] SQS FIFO：同じ案件は1つずつ、違う案件は並んで")
    for k, v in b["obs"].items():
        print(f"  {k}: {v}")
    print("  → 期待どおり（a1 → b1 → なし → a2）" if b["expected_pattern"] else "  → 期待と違う。上の値を送ってください")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=["run", "cleanup"])
    ap.add_argument("--region", default="ap-southeast-2")
    ap.add_argument("--keep", action="store_true", help="終わっても片付けない")
    ap.add_argument("--no-wait", action="store_true", help=argparse.SUPPRESS)
    a = ap.parse_args()
    if a.cmd == "cleanup":
        cleanup(a.region)
        return
    print(f"リージョン {a.region} で作ります（wq- で始まるもの。終わると消します）")
    try:
        q, arn, role_arn = setup(a.region)
        print("  作った: SQS FIFO キュー / Scheduler の予約グループ / IAM ロール")
        ra = test_a(a.region, q, arn, role_arn, wait=not a.no_wait)
        rb = test_b(a.region, q)
        report(ra, rb, a.region)
        with open("wq_aws_result.json", "w", encoding="utf-8") as f:
            json.dump({"region": a.region, "A": ra, "B": rb}, f, ensure_ascii=False, indent=2, default=str)
        print("\n結果を wq_aws_result.json にも保存しました")
    finally:
        if not a.keep:
            print("\n片付け:")
            cleanup(a.region)


if __name__ == "__main__":
    sys.exit(main())