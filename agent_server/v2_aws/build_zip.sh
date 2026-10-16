#!/usr/bin/env bash
# AgentCore Runtime 用の zip を作る（リポジトリのルートで実行：  bash v2_aws/build_zip.sh）
# 公式（直接コードデプロイ・Python）の手順に沿う。違い：Python 3.12 にしている。
# 理由：ortools の最新版は、公式指定の manylinux2014 向けの wheel が Python 3.13 に無く、
#       Python 3.12 なら ortools 9.11 が入ることを、2026-10-14 に確認した。
# 必要：uv（https://docs.astral.sh/uv/）、zip。Windows は WSL か Git Bash で実行する。
set -euo pipefail
OUT=build_agentcore
rm -rf "$OUT" && mkdir -p "$OUT/pkg"
grep -v colorama v2_aws/requirements.txt > "$OUT/req.txt"
uv pip install --python-platform aarch64-manylinux2014 --python-version 3.12 \
  --target="$OUT/pkg" --only-binary=:all: -r "$OUT/req.txt"
cp v2_aws/app.py "$OUT/pkg/app.py"
cp -r core "$OUT/pkg/core"
find "$OUT/pkg" -name __pycache__ -prune -exec rm -rf {} +
find "$OUT/pkg" -type d -exec chmod 755 {} + ; find "$OUT/pkg" -type f -exec chmod 644 {} +
(cd "$OUT/pkg" && zip -qr ../deployment_package.zip .)
ls -lh "$OUT/deployment_package.zip"
echo "上限：zip 250MB / 展開後 750MB（公式）"
