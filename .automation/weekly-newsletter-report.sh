#!/bin/bash
# 지난 7일간 아카이브된 뉴스레터(personal/09-newsletters/)를 종합해
# 한국어 주간 리포트를 만드는 headless Claude 실행 스크립트.
# launchd가 매주 월요일 아침에 호출한다 (com.giana.newsletter-weekly-report.plist).
#
# archive-newsletters.sh(원본 아카이브 + 일일 다이제스트)와 독립적으로 실행되며,
# 그 산출물(원본 + 일일 다이제스트)을 입력으로만 읽는다.

set -euo pipefail

VAULT_DIR="/Users/gyuhyeongkim/orca/projects/quant_auto"
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
WEEK_START_KST=$(TZ=Asia/Seoul date -v-7d +%Y-%m-%d 2>/dev/null || TZ=Asia/Seoul date -d '7 days ago' +%Y-%m-%d)
TODAY_ISO_KST=$(TZ=Asia/Seoul date +%Y-%m-%d)

PROMPT="지난 7일 범위: ${WEEK_START_KST} ~ ${TODAY_ISO_KST} (KST)

작업:
1. personal/09-newsletters/{newneek,uppity,bloomberg}/ 의 파일들을 Glob으로 나열하고, 파일명 앞 6자리(YYMMDD)를 날짜로 해석해서 위 7일 범위 안에 있는 것만 골라 읽는다.
2. personal/09-newsletters/_digests/ 에 같은 기간의 일일 요약이 있으면 참고용으로 같이 읽는다(있으면 재활용, 없어도 문제없다 — 원본에서 직접 종합해도 된다).
3. 영문(주로 bloomberg)은 한국어로 번역해서 이해하고 리포트도 전부 한국어로 작성한다.
4. 이번 주 분량이 하나도 없으면 '이번 주 아카이브된 뉴스레터 없음 — 리포트 생략'만 출력하고 끝낸다.
5. personal/09-newsletters/_weekly/${TODAY_KST}-주간리포트.md 를 작성한다. 형식:
   ---
   date: ${TODAY_ISO_KST}
   week_range: ${WEEK_START_KST} ~ ${TODAY_ISO_KST}
   ---

   # ${WEEK_START_KST} ~ ${TODAY_ISO_KST} 뉴스레터 주간 리포트

   ## 이번 주 한눈에
   (3-5문장, 이번 주 전체를 관통하는 흐름이 있으면 짚는다)

   ## 주요 이슈 (소스 무관, 주제별로 묶어서)
   (여러 날/여러 소스에 걸쳐 반복되거나 비중 있게 다뤄진 주제를 주제별 소제목으로 정리. 날짜·출처를 괄호로 표기)

   ## 소스별 특이사항
   - **뉴닉**: (이번 주 특징적인 것)
   - **어피티**: (이번 주 특징적인 것)
   - **블룸버그**: (이번 주 특징적인 것, 영문 원문은 번역해서 반영)

   ## 참고 원문
   (이번 주에 포함된 원본 파일 경로를 소스별로 나열 — 나중에 원문 확인용)

personal/09-newsletters/_weekly/ 외의 다른 파일은 건드리지 않는다. git commit/push는 하지 않는다."

{
  echo "=== $(date '+%Y-%m-%d %H:%M:%S') [뉴스레터 주간리포트] 실행 시작 ==="
  retry 3 60 "$CLAUDE_BIN" -p "$PROMPT" --allowedTools "Read Write Glob Grep" 2>&1
  echo "=== $(date '+%Y-%m-%d %H:%M:%S') [뉴스레터 주간리포트] 실행 종료 ==="
  echo
} >> "$LOG_FILE"
