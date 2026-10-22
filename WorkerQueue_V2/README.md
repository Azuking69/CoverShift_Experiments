# WorkerQueue V2（LangGraph 再開つき）

課題4の WorkerQueue に、LangGraph の「途中保存と再開」を載せた小さな実験。PoC であり、本番の設計ではない。

## V1 との違い
| | V1（課題4） | V2 |
|---|---|---|
| 仕事の中身 | states.py の状態表で、次の状態を引く | graph.py の LangGraph（step_a → step_b → 承認待ち → finish） |
| 途中経過の保存 | cases.state の1列 | LangGraph の checkpoint（PostgreSQL） |
| 承認待ち | 状態が変わるだけ | interrupt() で止まり、Command(resume=...) で再開 |
| 追加ファイル | - | graph.py, try_v2.py, node_runs 表 |

api.py / scheduler.py / キュー（SKIP LOCKED・案件ごとのFIFO・止まった仕事の戻し）は V1 と同じ。

## 動かし方（ローカル）
    docker compose up -d
    pip install -r requirements.txt
    python try_v2.py 1    # 承認待ちで止めて、全ワーカーを止めてから再開
    python try_v2.py 2    # 処理の途中で落として、続きから再開
    python try_v2.py 3    # 1ステップが10秒を超える（弱点の確認）
    python try_v2.py 4    # 順番・二重取り・同じ合図が2回

## 実行結果（Claude の環境、PostgreSQL 16、langgraph 1.2.16 / langgraph-checkpoint-postgres 3.2.0）
- ① 承認待ちの間、processing の仕事は0件。全ワーカーを止めたあと別ワーカーが再開し、step_a・step_b は1回ずつ
- ② step_b の最中に kill -9 → 別ワーカーが続きから。step_a は1回、step_b は2回（落ちた回＋再開した回）
- ③ 1ステップ8秒×2（STUCK_SECONDS=10）→ step_b の最中に別ワーカーが取り直し、step_b が A と B で二重に動いた（❌）
- ④ 先に来た approved は無視、deadline の二重は1回、2案件×2ワーカーでも step_a は1回

Windows（チームの環境）では未実行。
