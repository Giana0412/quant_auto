#!/bin/bash
# 개인 Gmail(kimgyuh04@gmail.com)에 구독된 뉴스레터를 매일 수집해
# personal/09-newsletters/{소스}/ 에 마크다운으로 아카이브하는 headless Claude 실행 스크립트.
# launchd가 매일 1회 호출한다 (com.giana.newsletter-archive.plist).
#
# 이 스크립트는 개인 Gmail발 콘텐츠만 다룬다 — 회사 Slack 파이프라인(process-slack-docs.sh)과
# 완전히 독립적이며, 저장 대상도 personal/(로컬 전용 repo)로 회사 vault repo와 분리돼 있다.

set -euo pipefail

VAULT_DIR="/Users/gyuhyeongkim/orca/projects/obsidian_test"
CLAUDE_BIN="/Users/gyuhyeongkim/.local/bin/claude"
LOG_DIR="$VAULT_DIR/.automation/logs"
LOG_FILE="$LOG_DIR/$(date +%Y%m%d).log"

# 구독 발신자 목록 — 새 뉴스레터 추가 시 여기와 personal/09-newsletters/_README.md 둘 다 갱신
SENDERS="whatsup@newneek.co,moneyletter@uppity.co.kr,noreply@news.bloomberg.com"

mkdir -p "$LOG_DIR"
cd "$VAULT_DIR"

PROMPT="personal/09-newsletters/_README.md 를 먼저 읽는다.

작업:
1. Gmail search_threads 로 다음 발신자의 메일을 검색한다: ${SENDERS}
   쿼리 예: 'from:whatsup@newneek.co OR from:moneyletter@uppity.co.kr OR from:noreply@news.bloomberg.com'
2. personal/09-newsletters/_state.json 을 읽는다. 스키마: { \"<threadId>\": true, ... } — 이미 처리한 스레드 ID 집합.
3. _state.json에 없는 새 스레드만 get_thread(messageFormat=FULL_CONTENT)로 본문을 가져온다.
4. 구독 확인/환영 메일(제목에 '구독' 확인, 'You've subscribed', 활용법 안내 등 실제 발행물이 아닌 것)은 저장하지 않는다 — 실제 뉴스레터 발행물만 저장한다. 단, 이렇게 건너뛴 스레드 ID도 반드시 _state.json에 기록한다(파일 저장 여부와 무관하게 "이미 판단을 마친 스레드"는 전부 기록 — 그래야 다음 실행에서 같은 웰컴 메일을 매번 재검토하지 않는다).
5. 발신자별로 저장 폴더를 정한다:
   - whatsup@newneek.co → personal/09-newsletters/newneek/
   - moneyletter@uppity.co.kr → personal/09-newsletters/uppity/
   - noreply@news.bloomberg.com → personal/09-newsletters/bloomberg/
6. 각 메일을 'YYMMDD-제목(파일명에 부적합한 문자는 제거).md' 로 저장한다. 형식:
   ---
   date: (메일 날짜 YYYY-MM-DD)
   sender: (보낸사람)
   subject: (제목)
   gmail_thread_id: (스레드 ID)
   ---

   (plaintextBody 또는 htmlBody에서 텍스트만 추출한 본문 그대로 — 광고 트래킹 링크·이미지 태그는 제거해도 되지만 본문 내용/글의 문단 구조는 보존. 요약하지 않는다.)
7. 이번에 판단한 스레드 ID 전부(저장한 것 + 웰컴메일이라 건너뛴 것)를 _state.json에 true로 추가해서 Write로 갱신한다 (기존 항목은 유지, 병합 방식).
8. 마지막에 소스별로 몇 건 새로 저장했는지 한 줄 요약. 새 발행물이 없으면 '신규 뉴스레터 없음'만 출력.

personal/09-newsletters/ 외의 다른 파일은 건드리지 않는다. git commit/push는 하지 않는다."

{
  echo "=== $(date '+%Y-%m-%d %H:%M:%S') [뉴스레터 아카이브] 실행 시작 ==="
  "$CLAUDE_BIN" -p "$PROMPT" --allowedTools "Read Write Glob Grep mcp__claude_ai_Gmail__search_threads mcp__claude_ai_Gmail__get_thread" 2>&1
  echo "=== $(date '+%Y-%m-%d %H:%M:%S') [뉴스레터 아카이브] 실행 종료 ==="
  echo
} >> "$LOG_FILE"
