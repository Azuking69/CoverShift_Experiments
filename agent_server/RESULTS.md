# RESULTS（V1＝AgentServer、V2＝AWS AgentCore）

- ソルバー：本物のCP-SAT（6人×7日のダミー入力）。Claude：偽物（固定文）。実験日：2026-10-14。
- 環境：Linux（Claudeの作業環境）と Windows（アズキPC、Python 3.13）。**どちらも同じ結果**。
- 表の「V2」列は、手元（AWSなし）の結果。**AWS上の結果は、下の「V2：AWS AgentCore での結果」にある。**
- 実験後、AWSに作ったものは**すべて削除済み**（下の「AWSの後片付け」）。

| #                     | V1 AgentServer（開発用サーバー）                                                                                                                                                                                                                                                              | V2 AWS AgentCore（手元・仮の保存先）                                                                                                                                                                    |
| --------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| E1 承認待ち→再開      | ○ 止まる→再開でS6（確定済み）／却下でretry=1、再び承認待ち                                                                                                                                                                                                                                    | 手元で ○（同じ結果）。**AWS上でも ○**（下記）                                                                                                                                                           |
| E2 途中で落とす       | △ 判定できない。**PostgreSQL版（`langgraph up`、Docker）は、ライセンス確認で起動できなかった（下記「V1 PostgreSQL版」）**。開発用サーバー（メモリ保存）では、計算中に落とすと再起動後に最初からやり直し／承認待ちで落とすと状態が消えた。**PostgreSQL版は未実施**（ライセンス条件の確認が先） | △ AWS＋Memoryで一部：停止後の状態は残った（`next: solver`）が、自動では再開されず、続きの実行は未試験（下記）                                                                                           |
| E3 同じ案件の同時実行 | ○ 既定は待ち行列（enqueue）、`multitask_strategy="reject"` で拒否（409）                                                                                                                                                                                                                      | 手元アプリでは、**両方とも実行された**（同時実行を防ぐ仕組みなし）。**AWS上でも2本とも実行された**（重複実行、下記）                                                                                    |
| E4 送信内容           | ○ 送信5回、実名の漏れなし（Windows・Linux）                                                                                                                                                                                                                                                   | 手元で ○ 送信5回、実名の漏れなし。AWS上でも ○（CloudWatchのログで確認、下記）                                                                                                                           |
| E5 費用の目安         | ソルバー1回 約0.005〜0.009秒（この入力・Linux）。費用は未実施                                                                                                                                                                                                                                 | **未測定**。請求画面は、実験の直後（2026-10-14 23:03）に見たが、残り$100.00・使用サービス0で、**まだ反映されていなかった**（推測です）。明日以降に Cost Explorer（今月・サービス別）と Free Tier を見る |

## V1 PostgreSQL版（`langgraph up`、Docker Desktop・Windows、2026-10-14）

- イメージの作成：成功（ルートに本物の `pyproject.toml` と `.dockerignore` が必要だった。`v1_agentserver/README.md` に詳細）。PostgreSQL（pgvector/pg16）・Redisのコンテナも起動し、Healthy。
- APIコンテナ：**起動直後に終了（exit 3）**。ログ：PostgreSQLのマイグレーション（version 27〜63）は適用されたあと、`No enterprise license key or LangSmith API key found` → `ValueError: License verification failed`（開発用：「LangGraph Cloudの権限があるアカウントの `LANGSMITH_API_KEY`」、本番用：`LANGGRAPH_CLOUD_LICENSE_KEY`）。
- つまり、**PostgreSQL保存のAgent Serverは、キーなしでは動かない**（メモリ版の `langgraph dev` は、キーなしで動いた）。
- 料金（LangSmith公式の料金ページ、2026-10-14閲覧）：Developer（$0/seat/月）の「Deployment」は N/A。Plus（$39/seat/月）は「1 free Serverless (Small) deployment」を含む。ハイブリッド・自前運用（self-hosted）は Enterprise のみ（Custom pricing）。無料の自前運用（lite）の記載はなかった。
- わからないこと：Plusの `LANGSMITH_API_KEY` で、手元の `langgraph up` が起動するか（料金ページに `langgraph up` の記載がない）。未試験。
- Agent ServerのPostgreSQLには、自前のスキーマ（マイグレーション約60個）が作られた。＝ **Agent Serverを使うと、DBの中身は、Agent Server側が持つ**。
- → V1のE2（PostgreSQL保存で、落ちても残るか）は、**有料プランなしでは試せなかった**。

## V0（基準）：PostgresSaver＋PostgreSQL（Agent Serverなし）

条件：同じグラフ、偽のClaude、PostgreSQL 16、プロセスをコードで強制終了（SIGKILL相当）。**Linux（この作業環境、PostgreSQL 16）と、Windows＋Docker（postgres:16、アズキPC）の両方で、同じ結果**。
| 項目 | 結果 |
|---|---|
| E2 A 計算中（人工的な待ち20秒の8秒後）に強制終了 | 別プロセスから見た状態＝`next: ["solver"]`、`status: null`（入力まで保存済み・途中結果なし）。`graph.invoke(None, config)` で**続きを実行でき**、承認待ちまで進み、承認でS6まで進んだ |
| E2 B 承認待ちでプロセス終了 | 別プロセスから、承認待ち（`interrupted: true`）が見え、承認でS6まで進んだ |
| E3 同じ案件に同時に2本 start | 2本とも成功終了（待たされない・断られない）。1本は途中の状態（`next: explain`）を返した。最終は承認待ち |
Windowsでの補足：強制終了の終了コードは `1`（Linuxは `-9`）。最初の版の試験は、起動（部品の読み込み・DB接続）に8秒以上かかり、計算の開始前に殺してしまい `state` が空になった（試験側の問題）。ワーカーの `STARTED` 表示のあとから数える形に直して、解決した。
注意：**自動では再開されない**。「続きを実行する」操作（`continue`）は、呼ぶ側のコードが用意する必要がある（v6_genでは、ワーカー＋キューの役目）。

## V2：AWS AgentCore での結果（シドニー ap-southeast-2、2026-10-14）

条件：zip（Python 3.12・arm64）＋直接コードデプロイ、コンソールの「テスト」から呼び出し、**Memoryなし（Runtimeのメモリの中に保存）**、偽のClaude。
| 項目 | 結果 |
|---|---|
| ortools（CP-SAT）がAWS上で動くか | ○ 動いた（arm64・manylinux2014・Python 3.12。ortools 9.11） |
| E1 承認待ち→再開 | ○ `interrupt` で止まった（`next: manager_review`、`interrupted: true`）→ `state` で確認 → `resume` で S6（確定済み）。**同じセッション・Runtimeのメモリ保存**での結果。Memory（外部保存）での結果ではない |
| E4 送信内容（AWS） | ○ CloudWatchの `OUTBOUND` ログ（偽Claudeへの送信本文）に、「スタッフA〜F」のみ。`山田` で検索して一致なし（`スタッフ` では1件ヒット＝日本語検索は有効）。確認範囲：1ログストリーム・直近1時間・`start` 1回。他5名の名前は未検索 |
| E3 同じ案件の同時実行 | 断られなかった。同じthread_id・同じセッションIDで2本を同時に呼ぶと、**2本とも成功**し、どちらも承認待ちの状態を返した。CloudWatchの `OUTBOUND` は2行（12:46:47.35 と 12:46:48.97 UTC、1.6秒差）＝**explainまで2回実行された（重複実行）**。1.6秒差が「直列」か「並列」かは、わかりません。AgentCore標準には、同じスレッドへの同時実行を断る/待たせる仕組みは見えなかった（V1のAgent Serverは既定で待ち行列、`reject`で409）。v6_genのadvisory lock＋世代番号に当たる部分は、自前で持つ必要があるように見える（推測です） |
| Memory保存（AgentCore Memory、短期イベントのみ・戦略なし） | ○ `AgentCoreMemorySaver` 経由で、承認待ちの状態が**別セッションから見え、再開できた**。セッションAで `start`（`backend: agentcore-memory`、承認待ち）→ **セッションBで `state`**（同じ承認待ちが見えた）→ **セッションBで `resume`** → S6（確定済み）→ セッションAで `state`（S6）。Runtimeのメモリ内保存では起きない動き。注意：「別セッション＝別の実行環境」と見ているが、別のmicroVMだったことまでは確認していない（推測です）。強制停止（StopRuntimeSession等）を挟む試験は未実施 |
| E2 計算中に落とす（V2・Memoryあり） | △ 一部わかった。条件：計算の人工的な待ち40秒（`SOLVER_EXTRA_WAIT_SEC=40`、solverノード内）の10秒後に `StopRuntimeSession`（HTTP 200）。**停止の3秒後に別セッションから見た状態＝`next: ["solver"]`、`status: null`**（入力まで保存済み・solver未完了。途中の結果は残らない）。停止したセッションAの呼び出しは、31.4秒後に `RuntimeClientError: Runtime initialization time exceeded. Please make sure that initialization completes in 30s.` で失敗（停止後の再起動が30秒に収まらなかった、と見える。推測です）。31秒後も状態は `next: ["solver"]` のまま＝**自動では再開されなかった**。補足：SDKの自動再試行が有効だった1回目は、101秒かかって承認待ちで成功（再試行の仕組みでやり直されたと見えるが、続きからか最初からかは区別できない）。**未実施：Memoryに残った状態から、続きを実行する操作（`graph.invoke(None, config)` 相当）。app.py に、その操作が無い** |

運用上の観察：停止後の再起動（約86MBのzip、展開後266MB）で「初期化30秒超え」が起きた。コールドスタートが30秒の上限に近い可能性がある（わかりません。測定していない）。

Memoryをつなぐのに必要だったこと：Memory作成（名前・有効期限7日・戦略なし）／実行ロールへの権限追加（`bedrock-agentcore:CreateEvent, GetEvent, ListEvents, DeleteEvent, ListSessions, ListActors`。公式の資料にあった `RetrieveMemories` は、IAMに存在しない名前でエラー。最小限の権限は、わかりません）／環境変数 `AGENTCORE_MEMORY_ID`。

起きた問題（運用上の注意）

- 無料プラン（新方式の登録）は、リージョンが住所の国で固定。日本・韓国の住所はシドニー。東京は選べない（公式「AWS Regions for your projects」）。
- zipにPython 3.13向けの部品を入れたが、ortoolsの最新版が公式指定の形式（manylinux2014）に3.13の部品を持たず、**Python 3.12に統一**した。
- 実行環境はコードの置き場（/var/task）に書き込めない。`outbound.log` への書き込みで `PermissionError`（500）。`/tmp`と標準出力に出すよう修正した。
- 更新画面では「Python 3.12」に見えたが、保存されたバージョンは **3.14** になっていた。3.12用の `.so` が読み込めず `ImportError`（起動が失敗し、「初期化が30秒を超えた」と表示された）。バージョンを選び直して解決した（原因の細部は、わかりません）。
- ランタイム作成から呼び出せるまで、約1分。

## AWSの後片付け（2026-10-14 23:01 までに確認）

画面で確認できたもの（すべてシドニー ap-southeast-2）：

- Runtime：削除済み（一覧が0）
- Memory：削除済み（一覧が `(0)`、「見つかりません」）
- IAM：実行ロール `BedrockAgentCoreRuntimeServiceRole` と、Memory用のインライン権限を削除（ロール一覧に、私たちのものはない。残りはアカウント標準のロール）
- S3：コンソールが自動で作ったバケットを、中のzip 3つ（計246.1MB）ごと削除（一覧が `(0)`）
- CloudWatch：`/aws/bedrock-agentcore/runtimes/…-DEFAULT` を削除（一覧が `(0)`）
- 確認していないもの：シドニー以外のリージョン（使っていないはずだが、見ていない。推測です）、CloudShellに置いたファイル。
- 注意：CloudWatchのログを消したので、E4（AWS）の送信ログは、もう見直せない。

## 本物のClaude APIについて（2026-10-14）

- リクエストは実際に送られた（`kind: real`）。送信本文は「スタッフA〜F」の記号だけで、実名なし（本物の経路でもE4は通った）。
- ただし、API側が断った：`Your credit balance is too low`（400）。Consoleの組織クレジットが$0.00のため。「クラウドセッションクレジット」（$100）は、このAPIとは別の口座。
- 決済（残高の追加）は、できなかった（理由は未確認）。以降は偽のClaudeで実験した。
- 鍵・モデル名（`claude-sonnet-5-5`）は、APIに受け付けられた。

## 環境ごとの注意

- Windows（韓国語環境）：`pip install colorama` と、`$env:PYTHONUTF8="1"` が必要だった（cp949で、langgraph_apiの設定ファイルを読めないため）。
- `.env` は、ルート（`AgentServer/`）に置く。動いているサーバーは、起動時の `.env` を読んだままなので、変えたら、サーバーを再起動する。
- 開発用サーバーは、ライセンスキーもLangSmithのAPIキーも設定せずに起動した。

## まだわからないこと

- AgentCoreで、計算中に落としたときの復旧（E2）。interrupt・Memory保存・別セッションからの再開は、動いた。落としたあとの「続きの実行」は未試験（V0では `invoke(None)` で続きが動いたので、同じ形で動く見込みだが、AgentCoreでは確認していない）。
- E5（費用）：請求画面への反映待ち。今回のAWSの使用で、クレジットがいくら減ったかは、わかりません。
- AgentCore Memoryは、同じ地域内の別リージョンでデータを処理することがある（コンソールの表示）。どのリージョンかは、わかりません。
- AgentServerの、PostgreSQL保存での「落ちても残るか」（E2の本題）。
- 実運用の規模・制約でのソルバーの計算時間。
