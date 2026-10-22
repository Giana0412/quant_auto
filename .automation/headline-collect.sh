#!/bin/bash
# 헤드라인 수집 — ml/headline-sentiment 의 학습 데이터를 매일 쌓는다.
#
# ── 왜 체인 맨 뒤인가 ─────────────────────────────────────────────────────
# 이건 **개인 연구용이지 브리핑 본체가 아니다.** 브리핑은 한국장 개장(09:00) 전에
# 도착해야 하는데, 앞에 끼우면 그만큼 뒤로 민다. 맨 뒤에 두면 느려져도 자기만
# 늦는다. 실패해도 브리핑은 이미 나간 뒤다.
#
# ── 왜 파이프라인 venv 인가 ──────────────────────────────────────────────
# collect.py 는 torch 를 임포트하지 않는다(yfinance·pandas·bridge 뿐). 운영
# 머신에 2GB 짜리 torch 를 또 깔 이유가 없다. 학습은 사람이 개발 클론에서 돌린다.
#
# 🔴 데이터는 personal/10-market/_headlines/ 한 곳에만 쌓인다(§collect.py).
# 어느 클론에서 돌리든 같은 파일에 들어간다 — 두 벌로 갈라지면 학습이 망가진다.

set -uo pipefail

VAULT_DIR="/Users/gyuhyeongkim/orca/projects/quant_auto"
SCRIPT="$VAULT_DIR/ml/headline-sentiment/collect.py"
PY="$VAULT_DIR/.automation/.venv/bin/python"
LOG_DIR="$VAULT_DIR/.automation/logs"
LOG_FILE="$LOG_DIR/$(date +%Y%m%d).log"

mkdir -p "$LOG_DIR"

if [ ! -f "$SCRIPT" ]; then
  echo "=== $(date '+%Y-%m-%d %H:%M:%S') [헤드라인] 스크립트 없음 — 건너뜀 ===" >> "$LOG_FILE"
  exit 0
fi

cd "$VAULT_DIR/ml/headline-sentiment" || exit 0
out=$("$PY" collect.py 2>&1)
rc=$?

# 요약 두 줄만 남긴다 — 로그에 209줄 진행상황을 흘리지 않는다
summary=$(echo "$out" | grep -E '^\[(수집|라벨)\]' | tr '\n' ' ')
echo "=== $(date '+%Y-%m-%d %H:%M:%S') [헤드라인] rc=$rc ${summary:-출력없음} ===" >> "$LOG_FILE"
exit 0   # 🔴 실패해도 체인을 세우지 않는다 — 개인 연구용이다
