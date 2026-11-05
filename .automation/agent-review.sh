#!/bin/bash
# 에이전트 리뷰 — 모델 북 종목에 TradingAgents 세컨드 오피니언을 붙인다 (§agent_review.py).
# evening-chain.sh 에서 market-snapshot 다음, daily-conclusion 앞에 돈다 —
# 북은 market-snapshot 이 기록하고, 결론이 이 단계의 산출물을 읽기 때문이다.
#
# ── 실패해도 브리핑은 나간다 ───────────────────────────────────────────────
# 결론 프롬프트는 에이전트의견.md 가 없으면 그 절을 통째로 생략한다. 그래서 이
# 단계가 죽어도 브리핑 본체는 영향이 없다. 다만 **조용히 죽지는 않는다** —
# 한 종목도 못 냈으면 0 이 아닌 코드로 끝나 체인 로그에 🔴 가 찍힌다.

set -uo pipefail

VAULT_DIR="${VAULT_DIR:-$HOME/orca/projects/quant_auto}"
PY="$VAULT_DIR/.automation/.venv-ta/bin/python"
BASE_PY="$VAULT_DIR/.automation/.venv/bin/python"
SCRIPT="$VAULT_DIR/.automation/agent_review.py"
KEY_FILE="$VAULT_DIR/.automation/.anthropic.env"
LOG_DIR="$VAULT_DIR/.automation/logs"
LOG_FILE="$LOG_DIR/$(date +%Y%m%d).log"

mkdir -p "$LOG_DIR"
cd "$VAULT_DIR" || exit 1

log() { echo "=== $(date '+%Y-%m-%d %H:%M:%S') [에이전트] $* ===" >> "$LOG_FILE"; }

# 기본은 구독(claude -p) — 키가 필요 없다(§claude_cli_llm.py). TA_BACKEND=anthropic 일 때만 키를 본다.
TA_BACKEND="${TA_BACKEND:-claude_cli}"; export TA_BACKEND
if [ "$TA_BACKEND" = "anthropic" ]; then
  if [ ! -s "$KEY_FILE" ]; then
    log "키 없음 ($(basename "$KEY_FILE")) — 건너뜀"
    exit 0
  fi
  set -a; source "$KEY_FILE"; set +a
fi
if [ ! -x "$PY" ]; then
  log "🔴 .venv-ta 없음 — README 의 설치 절 참고"
  exit 1
fi

"$PY" "$SCRIPT" run >> "$LOG_FILE" 2>&1
rc=$?

# 3 = 오늘 북이 기록되지 않았다. 북 기록은 market-snapshot 의 LLM 이 paper_track 을
# 부르는 방식이라 빠질 수 있다 — 그러면 여기서 직접 기록하고 한 번만 다시 돈다.
if [ "$rc" -eq 3 ] && [ -x "$BASE_PY" ]; then
  log "오늘 북 기록 없음 — paper_track record 를 직접 돌린다"
  (cd "$VAULT_DIR" && "$BASE_PY" .automation/paper_track.py record) >> "$LOG_FILE" 2>&1
  "$PY" "$SCRIPT" run >> "$LOG_FILE" 2>&1
  rc=$?
fi

log "rc=$rc"
exit "$rc"
