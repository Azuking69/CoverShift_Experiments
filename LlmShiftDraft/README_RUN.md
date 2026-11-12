# mix2_55 experiment kit (11/12) — 実行手順

승혁さんの「5.5 후보표 실험」を、アズキのPC（Windows）で回すための一式です。
`run.py` は승혁さんのものに、次の2点だけ足しました（それ以外は同じ）。

1. `first_user()` の条件を `cond == "mix2"` から `cond.startswith("mix2")` に変更（後補表が mix2_55 にも付く）
2. `--cond` の選択肢に `mix2_55` を追加（＋説明文を1行）

## フォルダの置き方
```
LlmShiftDraft\                 ← この一番上のフォルダ（ここに .env を置く。名前は何でもよい）
  .env                         ← あなたが作る。中身は ANTHROPIC_API_KEY=... の1行だけ
  experiments\2026-11-07_azuki_mix\
    run.py
    azuki_src\prototype_mcp.py     ← 11/07 の写し（変えない）
    azuki_src\staff_data.json      ← MD5 ed45762a3636f52ba87692c7c067d5c3
    calls.jsonl / results.jsonl / RESULTS.md   ← これまでの記録（ここに続けて書く）
```
キーはチャットやGitに出さないこと（.env は git に入れない）。

## 準備（PowerShell・最初の1回）
```powershell
cd C:\Users\User\Programming\CoverShift_Experiments\<置いたフォルダ名>   # 場所は推測です。VS Codeでフォルダを右クリック→「統合ターミナルで開く」でもよい
py -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install "anthropic>=1.9.0" python-dotenv langgraph
```
Python 3.13 以上。`-X utf8` は、日本語をファイルに書くときの文字化け防止です（必ずつける）。

## 手順
1. 配線確認（お金はかからない）
```powershell
python -X utf8 -I experiments\2026-11-07_azuki_mix\run.py --cond mix2_55 --fake bad
```
   期待する出力: 「호출 1〜3 … 반드시 위반 1385 · 경고 57」の3行で終わる（このコンテナでの確認結果と同じ）。
2. 確認で作られたニセの記録を消す（これを忘れると、本物の結果と混ざる）
```powershell
Remove-Item experiments\2026-11-07_azuki_mix\draft_mix2_55_*.json, experiments\2026-11-07_azuki_mix\results_fake.jsonl
```
3. 本番を1回だけ回す（PCをスリープさせない。5〜15分かかるかもしれない）
```powershell
python -X utf8 -I experiments\2026-11-07_azuki_mix\run.py --cond mix2_55
```
   出力の上限（max_tokens）に達したり失敗したら、そこで止まる。やり直さない。
4. できたファイルを、この会話に添付する
   `calls.jsonl` / `results.jsonl` / `draft_mix2_55_*.json`（あれば）
   → RESULTS.md への追記と、数字の照合は、こちらでやります。

## 費用の目安
1回あたり約 $0.4（승혁さんの推定）。1回の上限は、出力 64,000 トークン分で $0.64、入力分を足して約 $0.7。
`run.py` 側の安全装置: 1回の実行で $3.0、`calls.jsonl` の合計で $8.0 を超えると止まる（今の合計は約 $3.56）。