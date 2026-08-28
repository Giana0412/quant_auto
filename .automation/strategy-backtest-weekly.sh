#!/bin/bash
# 전략 백테스트 주간 갱신 — "지역·섹터·스타일 로테이션" 규칙이 과거 몇 달 실제로
# 벤치마크를 이겼는지 personal/10-market/_backtest/latest.json 에 남긴다.
#
# 다른 잡들과 달리 Claude 를 부르지 않는다 — 순수 계산(strategy_backtest.py)이라
# 텍스트 생성이 필요 없다. 매일 돌 필요도 없다 — 회당 리밸런스가 21거래일이라
# 결과가 하루 단위로 바뀌지 않는다. market_metrics.py 가 이 캐시를 읽어 매일
# 아침 브리핑에 한 줄로 인용한다 ([백테스트] 절, age_days 로 오래된 캐시는 버림).
#
# launchd가 매주 월요일 06:30 KST에 호출한다 (com.giana.strategy-backtest-weekly.plist,
# 템플릿만 저장소에 있고 설치는 손으로 한다 — .automation/launchd/ 참고).

set -euo pipefail

VAULT_DIR="/Users/gyuhyeongkim/orca/projects/quant_auto"
LOG_DIR="$VAULT_DIR/.automation/logs"
LOG_FILE="$LOG_DIR/$(date +%Y%m%d).log"

mkdir -p "$LOG_DIR"
cd "$VAULT_DIR"

# 네트워크 대기·재시도 — 깨어난 직후 Wi-Fi 가 안 올라온 상태에서 죽는 것을 막는다.
source "$VAULT_DIR/.automation/lib/net.sh"
if ! wait_for_network >> "$LOG_FILE" 2>&1; then
  echo "=== $(date '+%Y-%m-%d %H:%M:%S') [전략백테스트] 네트워크 없음 — 건너뜀 ===" >> "$LOG_FILE"
  exit 0
fi

{
  echo "=== $(date '+%Y-%m-%d %H:%M:%S') [전략백테스트] 실행 시작 ==="
  .automation/.venv/bin/python .automation/strategy_backtest.py
  echo "=== $(date '+%Y-%m-%d %H:%M:%S') [전략백테스트] 실행 종료 ==="
  echo
} >> "$LOG_FILE"
