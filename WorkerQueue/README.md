# WorkerQueue — ワーカー・キュー・スケジューラーの最小コード（課題4）

**目的**：3人が、「ワーカー」「キュー」「スケジューラー」がそれぞれ何をする係かを、動かして理解する。
LangGraph・LINE・AWS・Claude API は**入れていない**。役割の理解だけに絞っている。

## 3つの係

| 係 | ファイル | やること | 折衷案での対応（推測を含む） |
|---|---|---|---|
| キュー | `db.sql` の `queue` テーブル | 「やる仕事」を順番に並べておく仕事リスト | SQS FIFO |
| スケジューラー | `scheduler.py` | 時刻を見張って、締切が来たら仕事リストへ足す。仕事の中身は知らない | EventBridge Scheduler |
| ワーカー | `worker.py` + `states.py` | 仕事リストから1件取り、状態遷移表で案件の状態を進める | consumer Lambda |
| 窓口 | `api.py` | 案件を作る・締切を登録する・様子を見る（仕事そのものはしない） | — |

案件の状態：`collecting`（集計中）→（締切）→ `reviewing`（検討中）→（review_done）→ `waiting_approval`（承認待ち）→（approved）→ `finished`（終了）

## 動かし方（Windows / PowerShell）

ターミナルを**4つ**開く。すべて `WorkerQueue` フォルダで実行。

```powershell
# 最初の1回だけ
pip install -r requirements.txt
docker compose up -d          # PostgreSQL（ポート5433）が起動し、テーブルが自動で作られる

# ターミナル1：窓口
uvicorn api:app --port 8000
# ターミナル2：スケジューラー
python scheduler.py
# ターミナル3：ワーカー
python worker.py
# ターミナル4：確認スクリプト
python try_it.py
```

`try_it.py` が ①基本の流れ ②順番 ③二重 の3つを確かめて、OK / NG を表示する。
ターミナル2・3のログを見ると、「誰が・いつ・何をしたか」が分かる。

## 手で確かめること（学習の中心）

1. **ワーカーを2つにする**：ターミナルをもう1つ開いて `python worker.py` を足し、`python try_it.py` を再実行。
   同じ仕事を2回やらない／同じ案件は順番どおり、をログで見る。
   （仕事を取るときの `FOR UPDATE SKIP LOCKED` が、二重に取らない仕組み）
2. **処理中に落とす**：ワーカーのログに「仕事を取った」と出たら、すぐ `Ctrl+C`。
   約10秒後、別のワーカーが「止まっていたので待ちに戻した」と出して、やり直す。
   （`worker.py` 内の `sleep` が、重い処理のまね。時間は `WORK_SECONDS`、`STUCK_SECONDS` で変えられる）
3. **スケジューラーを止める**：スケジューラーを止めて、締切（`/cases/{id}/deadline`）を登録し、時刻が過ぎてから再開。
   過ぎた締切の合図が、再開後に出る。
4. **同じ合図を2回送る**：2回目は「状態に不要 → 無視して完了」とログに出る（`states.py` の表にない組み合わせは無視）。

## 動作確認の状況

作成者の環境（PostgreSQL 16 を手元で起動）で、次を確認した：
- `try_it.py` の ①②③ がすべて OK（ワーカー2つで実行）
- 処理中のワーカーを強制終了 → 約12秒後に別のワーカーがやり直して `reviewing` になった
- スケジューラー停止中に過ぎた締切が、再開の約3秒後に出た

**まだ確認していないこと**
- Windows + Docker での動作（`docker-compose.yml` は未実行）
- 本番想定の SQS / Lambda / EventBridge の実際の動き。上の対応表は考え方の対応であり、細かい挙動（再試行・順番の保証の範囲など）は同じとは限らない

## 次の段階（まだやっていない）
- `states.py` の表を、LangGraph のグラフに差し替えられるか試す
- LINE の送信と返信待ちを、画面出力の偽物で足す
