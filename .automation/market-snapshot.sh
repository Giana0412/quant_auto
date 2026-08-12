#!/bin/bash
# 시장봇: 대표 지수/환율/금 고정 세트 + 오늘 뉴스에 언급된 종목을 yfinance로 스냅샷.
# launchd가 매일 20:15 KST에 호출한다 (com.giana.market-snapshot.plist).
# 뉴스레터 일일 다이제스트(archive-newsletters.sh, 20:00) 이후에 돌도록 스케줄돼 있다.

set -euo pipefail

VAULT_DIR="/Users/gyuhyeongkim/orca/projects/obsidian_test"
CLAUDE_BIN="/Users/gyuhyeongkim/.local/bin/claude"
LOG_DIR="$VAULT_DIR/.automation/logs"
LOG_FILE="$LOG_DIR/$(date +%Y%m%d).log"

mkdir -p "$LOG_DIR"
cd "$VAULT_DIR"

# 네트워크 대기·재시도 — 깨어난 직후 Wi-Fi 가 안 올라온 상태에서 죽는 것을 막는다.
# 대기 기록도 일별 로그에 남긴다 (건너뛴 이유가 어딘가엔 있어야 한다).
source "$VAULT_DIR/.automation/lib/net.sh"
if ! wait_for_network >> "$LOG_FILE" 2>&1; then
  echo "=== $(date '+%Y-%m-%d %H:%M:%S') 네트워크 없음 — 이번 실행 건너뜀 ===" >> "$LOG_FILE"
  exit 0
fi


TODAY_KST=$(TZ=Asia/Seoul date +%y%m%d)
TODAY_ISO_KST=$(TZ=Asia/Seoul date +%Y-%m-%d)

PROMPT="오늘 날짜(KST): ${TODAY_ISO_KST} (YYMMDD: ${TODAY_KST})

personal/10-market/_README.md 를 먼저 읽는다.

작업:
1. 고정 세트 티커: ^KS11 ^KQ11 ^GSPC ^IXIC KRW=X GC=F (README에 있는 것과 동일)
2. personal/09-newsletters/_digests/${TODAY_KST}-일일요약.md 가 있으면 읽어서, 그 안에 언급된 **상장 기업/종목**의 야후 파이낸스 티커를 최대한 정확히 찾아 추가 목록을 만든다 (예: 메타→META, 소프트뱅크→9984.T). 비상장 기업(SpaceX, OpenAI 등)이나 확실하지 않은 것은 넣지 않는다. 다이제스트가 없으면 이 단계는 건너뛴다(고정 세트만 사용).
3. 고정 세트 + 동적 세트를 합쳐서 다음 명령을 Bash로 실행한다 (중복 제거, 공백으로 구분):
   python3 .automation/market_snapshot.py <티커들...> --threshold 3.0
   이 스크립트가 CSV로 등락률과 ALERT/normal 플래그를 계산해서 출력한다 — 이 숫자를 그대로 옮겨 적는다. 절대 직접 계산하거나 추정하지 않는다. stderr에 에러난 티커가 있으면 결과에서 그 사실만 짧게 언급하고 넘어간다.
4. personal/10-market/data/${TODAY_KST}-시장데이터.md 를 작성한다. 형식:
   ---
   date: ${TODAY_ISO_KST}
   ---

   # ${TODAY_KST} 시장 스냅샷

   ## 고정 지수
   | 티커 | 이름 | 종가 | 전일비 | 상태 |
   |---|---|---|---|---|
   (python 출력 그대로 표로)

   ## 뉴스 연계 종목
   (동적 세트가 있으면 같은 형식의 표 + 왜 오늘 뉴스와 연결되는지 한 줄. 없으면 '오늘은 다이제스트에서 뽑을 만한 상장 종목 없음')

   ## 급등락 (ALERT)
   (ALERT 플래그 난 것만 모아서 강조. 없으면 '오늘은 임계치(3%) 넘는 변동 없음')

5. 마지막에 몇 개 티커 중 몇 개가 ALERT인지 한 줄 요약.

personal/10-market/data/ 외의 다른 파일은 건드리지 않는다. git commit/push는 하지 않는다."

{
  echo "=== $(date '+%Y-%m-%d %H:%M:%S') [시장봇] 실행 시작 ==="
  retry 3 60 "$CLAUDE_BIN" -p "$PROMPT" --allowedTools "Read Write Glob Grep Bash(python3 .automation/market_snapshot.py:*)" 2>&1
  echo "=== $(date '+%Y-%m-%d %H:%M:%S') [시장봇] 실행 종료 ==="
  echo
} >> "$LOG_FILE"
