# CoverShift_Experiments

CoverShift のための、個人の実験用リポジトリ。
チームに共有するコードは、チームのリポジトリの `experiments/` に上げる。

## フォルダ

| フォルダ | 何の実験か |
|---|---|
| `LangGraph/` | 【LangGraph でグラフを動かす実験。E9 対照試験（DB停止なしの C 対 V6）など】 |
| `Serving/` | 【LangGraph Agent Server と AWS での動かし方の実験。README と RESULT に結果あり】 |
| `WorkerQueue/` | （これから追加）ワーカー・キュー・スケジューラーの最小コード（課題4） |

## ルール
- 実験ごとにフォルダを分け、`requirements.txt` もフォルダごとに持つ。
- `.env` と API キーは上げない（`.env.example` だけ上げる）。
- 結果が出たら、各フォルダの README か RESULT に書く。