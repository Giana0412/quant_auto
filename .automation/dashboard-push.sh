#!/bin/bash
# 아침 브리핑을 팀 대시보드(Streamlit) 브리핑 탭으로 올린다 (§push_briefing.py).
# daily-conclusion 다음에 돈다 — 결론 파일을 재료로 쓴다. 텔레그램과 독립이라
# 여기가 실패해도 그룹 발송은 이미 끝난 뒤다.
set -uo pipefail

VAULT_DIR="${VAULT_DIR:-$HOME/orca/projects/quant_auto}"
LOG_DIR="$VAULT_DIR/.automation/logs"
LOG_FILE="$LOG_DIR/$(date +%Y%m%d).log"
mkdir -p "$LOG_DIR"
cd "$VAULT_DIR" || exit 1

out=$(python3 "$VAULT_DIR/.automation/push_briefing.py" 2>&1)
rc=$?
echo "=== $(date '+%Y-%m-%d %H:%M:%S') [대시보드] rc=$rc $(echo "$out" | tail -1) ===" >> "$LOG_FILE"
exit "$rc"
