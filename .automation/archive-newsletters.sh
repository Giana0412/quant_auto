#!/bin/bash
# 개인 Gmail(kimgyuh04@gmail.com)에 구독된 뉴스레터를 매일 수집해
# personal/09-newsletters/{소스}/ 에 마크다운으로 아카이브한다.
# 1단계 수집은 IMAP(순수 코드), 2단계 다이제스트는 headless Claude.
# launchd가 매일 1회 호출한다 (com.giana.newsletter-archive.plist).
#
# 이 스크립트는 개인 Gmail발 콘텐츠만 다룬다 — 회사 Slack 파이프라인(process-slack-docs.sh)과
# 완전히 독립적이며, 저장 대상도 personal/(로컬 전용 repo)로 회사 vault repo와 분리돼 있다.

set -euo pipefail

VAULT_DIR="/Users/gyuhyeongkim/orca/projects/obsidian_test"
CLAUDE_BIN="/Users/gyuhyeongkim/.local/bin/claude"
LOG_DIR="$VAULT_DIR/.automation/logs"
LOG_FILE="$LOG_DIR/$(date +%Y%m%d).log"

# 구독 발신자 목록은 .automation/newsletter_fetch.py 의 SENDERS 에 있다
# (발신자 : 저장폴더 매핑이라 코드 쪽에 두는 게 맞다). 추가 시 _README.md 도 함께 갱신.

mkdir -p "$LOG_DIR"
cd "$VAULT_DIR"

# 네트워크 대기·재시도 — 깨어난 직후 Wi-Fi 가 안 올라온 상태에서 죽는 것을 막는다.
# 대기 기록도 일별 로그에 남긴다 (건너뛴 이유가 어딘가엔 있어야 한다).
source "$VAULT_DIR/.automation/lib/net.sh"
if ! wait_for_network >> "$LOG_FILE" 2>&1; then
  echo "=== $(date '+%Y-%m-%d %H:%M:%S') 네트워크 없음 — 이번 실행 건너뜀 ===" >> "$LOG_FILE"
  exit 0
fi


# --- 1단계: Gmail 수집 (IMAP, 순수 코드) ---
# 예전에는 headless Claude 가 Gmail 커넥터로 가져왔으나, 그 커넥터는 대화형 인증에
# 묶여 있어 launchd 헤드리스 실행에서 붙지 않았다 (2026-08-10 실행 통째로 실패).
# 메일을 가져오는 일은 기계적이라 에이전트가 필요 없다 — 표준 라이브러리 IMAP 으로 옮겼다.
# 요약은 2단계에서 계속 에이전트가 한다 (그건 실제로 판단이 필요한 일이다).

{
  echo "=== $(date '+%Y-%m-%d %H:%M:%S') [뉴스레터 아카이브] 실행 시작 ==="
  python3 "$VAULT_DIR/.automation/newsletter_fetch.py" 2>&1 \
    || echo "⚠️ 수집 실패 — 다이제스트는 계속 진행한다"
  echo "=== $(date '+%Y-%m-%d %H:%M:%S') [뉴스레터 아카이브] 실행 종료 ==="
  echo
} >> "$LOG_FILE"

# --- 2단계: 일일 교차 다이제스트 ---
# 오늘 새로 아카이브된 뉴스레터가 있으면, 소스 간 공통 주제를 뽑아 한국어로 요약한다.
# 원본 아카이브(1단계)는 원문 그대로 보존하는 게 원칙이라 요약하지 않지만,
# 이 다이제스트는 분석 보조용 별도 산출물이라 요약·번역이 목적에 맞다.
# 체인이 자정을 넘겨도 단계들이 같은 날짜를 쓰도록 CHAIN_DATE 를 우선한다
TODAY_KST="${CHAIN_DATE:-$(TZ=Asia/Seoul date +%y%m%d)}"

PROMPT_DIGEST="오늘 날짜(KST, YYMMDD): ${TODAY_KST}

작업:
1. personal/09-newsletters/{newneek,uppity,bloomberg}/ 에서 파일명이 '${TODAY_KST}-'로 시작하는 파일을 Glob으로 찾는다.
2. 하나도 없으면 '오늘 발행물 없음 — 다이제스트 생략'만 출력하고 끝낸다.
3. 있으면 각 파일을 읽는다. 영문(주로 bloomberg)은 한국어로 번역해서 이해한다.
4. personal/09-newsletters/_digests/${TODAY_KST}-일일요약.md 를 작성한다. 형식:
   ---
   date: (오늘 날짜 YYYY-MM-DD)
   sources: (오늘 포함된 소스 목록)
   ---

   # ${TODAY_KST} 뉴스레터 일일 요약

   ## 소스별 핵심 (한국어, 영문 원문은 번역)
   - **뉴닉**: (있으면 2-3문장 요약)
   - **어피티**: (있으면 2-3문장 요약)
   - **블룸버그**: (있으면 2-3문장 요약, 영문 원문 번역 포함)

   ## 오늘의 교차 주제
   (2개 이상 소스에서 공통으로 다룬 주제가 있으면 짚는다. 없으면 '오늘은 소스 간 겹치는 주제 없음'이라고 명시한다 — 없는 걸 억지로 만들지 않는다.)

personal/09-newsletters/_digests/ 외의 다른 파일은 건드리지 않는다. git commit/push는 하지 않는다."

{
  echo "=== $(date '+%Y-%m-%d %H:%M:%S') [뉴스레터 일일다이제스트] 실행 시작 ==="
  retry 3 60 "$CLAUDE_BIN" -p "$PROMPT_DIGEST" --allowedTools "Read Write Glob Grep" 2>&1
  echo "=== $(date '+%Y-%m-%d %H:%M:%S') [뉴스레터 일일다이제스트] 실행 종료 ==="
  echo
} >> "$LOG_FILE"
