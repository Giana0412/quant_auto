#!/bin/bash
# 이벤트 알림 — 감시 창에 새로 들어온 것만 팀 그룹으로.
# evening-chain.sh 의 한 단계로 불린다(daily-conclusion 다음).
#
# 매일 떠들지 않는다 — event_alerts.py 가 상태를 기억해서 같은 이벤트의 같은 단계는
# 한 번만 보낸다. 조용한 날은 아무것도 안 나간다.

set -euo pipefail

VAULT_DIR="__HOME__/orca/projects/quant_auto"
LOG_DIR="$VAULT_DIR/.automation/logs"
LOG_FILE="$LOG_DIR/$(date +%Y%m%d).log"

mkdir -p "$LOG_DIR"
cd "$VAULT_DIR"

source "$VAULT_DIR/.automation/lib/net.sh"
if ! wait_for_network >> "$LOG_FILE" 2>&1; then
  echo "=== $(date '+%Y-%m-%d %H:%M:%S') [이벤트알림] 네트워크 없음 — 건너뜀 ===" >> "$LOG_FILE"
  exit 0
fi

# 월요일엔 관제 사이트에서 지표 일정을 다시 긁고 .ics 를 새로 만든다.
# 매일 할 이유가 없다 — 발표 일정은 주 단위로도 거의 안 바뀐다.
if [ "$(date +%u)" = "1" ]; then
  {
    echo "=== $(date '+%Y-%m-%d %H:%M:%S') [이벤트알림] 주간 지표 일정 갱신 ==="
    .automation/.venv/bin/python .automation/econ_calendar.py --merge
    .automation/.venv/bin/python .automation/calendar_export.py
  } >> "$LOG_FILE" 2>&1 || true
fi

{
  echo "=== $(date '+%Y-%m-%d %H:%M:%S') [이벤트알림] 실행 시작 ==="
  .automation/.venv/bin/python .automation/event_alerts.py --send
  echo "=== $(date '+%Y-%m-%d %H:%M:%S') [이벤트알림] 실행 종료 ==="
  echo
} >> "$LOG_FILE" 2>&1
