# AgentServer（CoverShift 実験用リポジトリ）

## 目的

教授の10/13フィードバック（DBを仲介しない構造の検討、既製のエージェント基盤の調査）を受けて、
**同じLangGraph（CoverShiftの核心グラフ）を2つの基盤に載せ、同じ項目で動かして比べる**。

- **V1：LangGraph Agent Server**（LangChain社の、グラフを動かすサーバー）
- **V2：AWS AgentCore**（AWSの、エージェントを動かすサービス）
  「どちらが良いか」を決める資料ではなく、「動かしてわかったこと／わからないこと」を残すための実験。

## 構成

```
AgentServer/
├─ core/            LangGraph本体（V1・V2で共通の1か所。サービス固有のコードは入れない）
├─ v1_agentserver/  V1：Agent Serverに載せる入口（entry.py, langgraph.json）と試験スクリプト
├─ v2_aws/          V2：AgentCore Runtimeに載せる入口（app.py）と試験スクリプト
├─ tests/           送信ログに実名が出ていないかの確認（check_outbound.py）
├─ EXPERIMENTS.md   共通の実験項目 E1〜E5（変えないこと）
└─ RESULTS.md       V1・V2の結果を並べた表（結果はここに書く）
```

`core/graph.py` の流れ：solver（本物のCP-SAT）→ explain（仮名化→偽のClaude→実名に戻す）→ manager_review（承認待ち interrupt）→ finalize。
今のv6_gen（API→DB→ワーカー）の「グラフの部分」と同じ流れ。ただしv6_genでは、本物のソルバーは未接続でダミーだった。ここでは接続した。DB・世代番号（fencing）は外してある。

## 前提・注意（正直に）

- **Claude APIは、環境変数 `ANTHROPIC_API_KEY` があれば本物、なければ偽物（固定文）。**（`core/llm.py`）どちらでも、**送る直前の本文**を `outbound.log` に追記する。
  - 本物を使うとき：`.env.example` を、**ルート（`AgentServer/`）に `.env` という名前でコピー**して、鍵を入れる（`.env` はgitに入れない。鍵をチャットやコードに貼らない）。V1は `langgraph.json` の `env` 設定で、V2・テストは `core/llm.py` が、この `.env` を読む。環境変数が先に設定されていれば、そちらが優先。
  - 本物が使われているかは、`outbound.log` の `"kind"` で確かめる（`real`＝本物、`fake`＝偽物）。
  - モデル名は `CLAUDE_MODEL`（既定 `claude-haiku-5-5`）。**すべて小文字**で書く（`claude-Haiku-5-5` のように大文字が混ざるとエラー）。使えないときもエラーになるので、その場合は変える。
  - APIがエラーを返したときは、原因が `outbound.log` に `"kind": "real_error"` で残る（サーバーの画面には「An internal error occurred」としか出ないため）。
  - 費用：トークン数は `outbound.log` の `real_usage` に残る（E5用）。**APIの利用が、どの支払い・クレジットに乗るかは、わかりません**（Consoleの請求画面で確認すること）。
- **ソルバーは本物のCP-SAT（OR-Tools）。** v6_genの `solver/main_solver.py` をそのままコピーした（`core/solver.py`）。入力は `core/fixtures.py` のダミーの6人×7日。
  - 限界：早番・遅番の2種類のみ。制約は「1人1日1シフト」「最低人数」、目的は「不可希望日のペナルティ」だけ。経験者優先・教育配置・公平性は、まだ入っていない。
  - この入力（6人×7日）では、1回の計算は約0.005〜0.009秒（この環境、5回計測）。実運用の規模・制約では、もっとかかる（わかりません）。
  - E2用に、環境変数 `SOLVER_EXTRA_WAIT_SEC` で、計算の前に人工的な待ちを入れられる（計算中に落とす試験用。ソルバーの時間とは別）。
- 仮名化は、`core/graph.py` の自前コード。「実名が出ない」という結果は、このコードの結果で、基盤が守ったわけではない。
- v6_gen本体のリポジトリとは別。ここは実験用で、本番コードではない。
- 動作確認した環境：Python 3.13（Linux）、langgraph 1.2.15、langgraph-api 0.16.0、bedrock-agentcore 1.24.1、langgraph-checkpoint-aws 1.2.5（2026-10-14）。
- V2は、AWS（シドニー）上でも動かした（2026-10-14）。結果は RESULTS.md。**作ったAWSのリソース（Runtime・Memory・IAMロール・S3のzip・CloudWatchログ）は、実験後にすべて削除した。**

## coreだけの確認（サービスなし）

```
pip install langgraph ortools anthropic
python tests/test_core.py     # ルートで実行。ソルバーの制約・承認待ち・実名なし
```

## V1：AgentServer（手元）

```
python -m venv .venv && . .venv/bin/activate     # Windowsは .venv\Scripts\activate
# 本物のClaudeを使う場合：export ANTHROPIC_API_KEY=...（Windows PowerShell: $env:ANTHROPIC_API_KEY="..."）
cd v1_agentserver && pip install -r requirements.txt
# Windows（PowerShell）では、先に：  $env:PYTHONUTF8="1"
langgraph dev --no-browser --no-reload --port 2024
python tests/e1_e3_e4.py http://127.0.0.1:2024     # 別の端末で
python ../tests/check_outbound.py outbound.log
```

- Windowsで `UnicodeDecodeError: 'cp949' codec can't decode byte …`（`langgraph_api\validation.py`）と出たら：Pythonの文字コードがcp949（韓国語Windowsの既定）になっているのが原因。`$env:PYTHONUTF8="1"`（PowerShell）を設定してから、起動し直す。
- Windowsで `ConsoleRenderer with colors=True on Windows requires the colorama package` と出たら：`pip install colorama`（requirementsにも追加済み）。それでも出るときは、`$env:LOG_COLOR="false"`（PowerShell）を設定して起動する。
- ポートが使われていると別の番号になる。起動ログの「API: http://…」を見る。
- 開発用サーバーは「メモリ＋ときどきファイル保存」。**E2（落とす実験）の答えにはならない**。本番相当（PostgreSQL＋Redis、`langgraph up`）で試す。ライセンス条件は、先に公式で確認する。
- 手元の開発用サーバーは、ライセンスキーなしで起動した（2026-10-14）。

## V2：AWS AgentCore

```
cd v2_aws && pip install -r requirements.txt
python app.py                                    # 手元 http://localhost:8080/invocations（仮の保存先）
python tests/run_experiments.py local            # 別の端末で
python ../tests/check_outbound.py outbound.log
```

AWSで試す（リージョン：シドニー `ap-southeast-2`。無料プランは、住所の国でリージョンが固定される。東京は選べない）：

1. zipを作る：`bash v2_aws/build_zip.sh`（Python **3.12**、arm64向け。約83MB。公式の例は3.13だが、ortoolsが入らないため）
2. IAMロール・S3バケット・AgentCore Memoryを作る（手順は、AWSの画面を見ながら確認する）
3. Runtimeを作る（実際は、コンソールの「S3にアップロード」から作成。boto3の `create_agent_runtime` ＋ `codeConfiguration`・`entryPoint: ["app.py"]` でも作れるはずだが、今回は試していない）
4. `python v2_aws/tests/run_experiments.py aws <agentRuntimeArn>`
5. 終わったら、Runtime・S3のzip・Memoryを削除する

- 環境変数は `AGENTCORE_MEMORY_ID` を渡した。実行ロールには、Memory用に `bedrock-agentcore:CreateEvent, GetEvent, ListEvents, DeleteEvent, ListSessions, ListActors` を足した（最小限かは、わかりません）。`ANTHROPIC_API_KEY` は、AWSには渡していない（偽のClaudeで実験）。
- 作ったものを消した記録：Runtime、Memory、IAMのロール・ポリシー、S3のバケット（zipが3つ）、CloudWatchのロググループ。**再実験するときは、作り直しが必要**（このリポジトリにAWSのリソースは残っていない）。
- `AGENTCORE_MEMORY_ID` が無いときは、仮の保存先（InMemorySaver）で動く。

## V0（基準）：PostgresSaver＋PostgreSQL（Agent Serverなし・ライセンス不要）

今のv6_genと同じ形（LangGraph OSS＋PostgresSaver）。V1のPostgreSQL版がライセンスで動かなかったため、E2・E3の基準として追加した。

```
docker compose -f v0_postgres/docker-compose.yml up -d --wait
pip install -r v0_postgres/requirements.txt
python v0_postgres/e2.py
docker compose -f v0_postgres/docker-compose.yml down -v      # 終わったら削除
```

## 実験項目（詳細は EXPERIMENTS.md）

E1 承認待ち→再開／E2 途中で落とす／E3 同じ案件の同時実行／E4 Claudeへの送信内容／E5 費用の目安

## 現在の結果（詳細は RESULTS.md）

- V0（PostgresSaver＋PostgreSQL、基準）：E2（計算中に強制終了→`continue`で続き）・承認待ちの保存・E3（同時2本は両方実行）。Windows・Linuxで同じ。
- V1のPostgreSQL版（`langgraph up`）：ライセンス確認で起動できず（E2は未実施）。
- V1：E1・E3・E4 は手元で動いた。E2は判定できず（開発用サーバーのため）。
- V2（AWS、シドニー）：E1・E3・E4 とMemory保存（別セッションからの再開）は動いた。E3は2本とも実行された（重複）。E2は、停止後の状態（`next: solver`）までは確認したが、続きの実行は未確認。詳細は RESULTS.md

## 次にやること

1. **E5（費用）**：AWSの請求画面（Cost Explorer・Free Tier）の反映は、1日ほど後（推測です）。明日以降に金額を確認して、RESULTS.md に書く。
2. V2のE2の残り：Memoryに残った状態から続きを実行する操作（`app.py` に `continue` を追加）。AWSのリソースが消えているので、作り直しが必要。
3. V1のE2を、PostgreSQL版で試す（ライセンス条件の確認が先。有料プランが必要な可能性）。
4. システム設計構造の比較（V1資料）の「まだわからないこと」を、RESULTS.md に合わせて更新する。
