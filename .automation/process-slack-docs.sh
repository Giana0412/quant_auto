#!/bin/bash
# slack-collect.sh 가 vault/raw/slack 에 모아둔 원본을 읽어서
# 3종 문서로 정리하는 headless Claude 실행 스크립트.
#   전사본   → vault/raw/transcripts          (원본 보존 계층)
#   정리본   → vault/wiki/05-meetings/정리본
#   결정사항 → vault/wiki/05-meetings/결정사항
# launchd가 1시간마다 호출한다 (com.giana.obsidian-slack-docs-sync.plist).

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


PROMPT='vault/schema/템플릿-가이드.md 파일을 먼저 읽고 그 형식을 그대로 따른다.

작업:
1. vault/raw/slack/*.md 를 전부 확인한다.
2. 각 파일에 실질적인 내용(파일 첨부 📎 코드블록, 또는 의미 있는 회의/문서 텍스트)이 있는지 확인한다. "채널에 참여함" 같은 시스템 메시지나 멘션만 있는 빈 메시지는 건너뛴다.
3. 내용이 있는 파일에 대해, 그 안의 실제 날짜(문서/회의 내용에서 추론, 없으면 slack_url이나 created 필드 사용)와 주제로 파일명을 만들어서 vault/raw/transcripts/, vault/wiki/05-meetings/정리본/, vault/wiki/05-meetings/결정사항/ 에 이미 같은 이름(YYMMDD-주제-*.md)의 결과물이 있는지 Glob으로 확인한다.
4. 이미 3종 다 있으면 건너뛴다 (중복 생성 금지). 하나라도 없으면 템플릿 가이드 형식대로 전사본/정리본/결정사항 3종을 새로 작성한다.
   - 전사본: 원문 보존, 요약 금지, 오탈자 교정 최소화
   - 정리본: 한줄요약/핵심논의(소주제별)/맥락배경/미결정사항/액션아이템(표) 구조
   - 결정사항: 결정사항/미결정보류/액션아이템 구조 (짧고 명확하게, 공식 결정이 없으면 "없음"으로 명시)
5. 처리한 원본과 새로 만든 문서 목록을 마지막에 요약해서 출력한다. 처리할 새 원본이 없으면 "처리할 새 원본 없음"이라고만 출력하고 끝낸다.

git commit/push는 하지 않는다 (obsidian-git이 별도로 자동 커밋한다). vault/raw/, vault/wiki/05-meetings/ 외의 파일은 건드리지 않는다.'

# --- 0단계: Slack 원본 수집 ---
# 예전에는 slack-sync 플러그인이 했으나 Obsidian 앱이 켜져 있어야만 동작해서
# 조용히 멈췄다. 이제 스크립트가 직접 한다. 수집이 실패해도 아래 문서화는
# 계속 진행한다 (이미 들어와 있는 원본은 처리할 수 있어야 하므로).
{
  echo "=== $(date '+%Y-%m-%d %H:%M:%S') [1/3 수집] 실행 시작 ==="
  bash "$VAULT_DIR/.automation/slack-collect.sh" 2>&1 || echo "⚠️ 수집 실패 — 문서화는 계속 진행한다"
  echo "=== $(date '+%Y-%m-%d %H:%M:%S') [1/3 수집] 실행 종료 ==="
  echo
} >> "$LOG_FILE"

{
  echo "=== $(date '+%Y-%m-%d %H:%M:%S') [2/3 문서화] 실행 시작 ==="
  retry 3 60 "$CLAUDE_BIN" -p "$PROMPT" --allowedTools "Read Write Edit Glob Grep" 2>&1
  # 문서가 늘거나 줄었으면 목차를 다시 만든다. 파일에서 유도되는 것만 만들므로
  # 매번 통째로 덮어써도 안전하다 (사람이 손댈 파일이 아니다).
  python3 "$VAULT_DIR/.automation/wiki_index.py" 2>&1 || echo "⚠️ 목차 생성 실패"
  # 무엇이 언제 위키에 들어왔는지 append-only 로 남긴다 (카파시 원문의 log.md)
  # grep 은 결과가 없으면 1을 반환한다. set -euo pipefail 아래에서 그대로 두면
  # "새 문서가 없다"는 정상 상황에 스크립트가 죽는다 — || true 로 막는다.
  NEW_DOCS=$( (cd "$VAULT_DIR" && git status --porcelain vault/wiki/05-meetings vault/raw/transcripts \
              | grep -c '^??') || true )
  if [ "${NEW_DOCS:-0}" -gt 0 ]; then
    python3 "$VAULT_DIR/.automation/wiki_log.py" ingest "Slack 원본" \
      --detail "새 문서 ${NEW_DOCS}건 생성" 2>&1 || true
  fi
  echo "=== $(date '+%Y-%m-%d %H:%M:%S') [2/3 문서화] 실행 종료 ==="
  echo
} >> "$LOG_FILE"

# --- 2단계: 액션 아이템 → Slack 기한 문의 / 답장 파싱 / 캘린더 등록 / 당일 알림 ---
# 준비 상태(TODO)가 남아있으면 조용히 건너뛴다:
#   - Slack Bot Token에 chat:write, im:write 스코프가 추가돼야 함
#   - Google Calendar MCP 연결(claude.ai/customize/connectors)이 돼 있어야 함
#   둘 다 준비되면 이 스크립트의 STAGE2_ENABLED를 true로 바꾸고,
#   --allowedTools 에 정확한 캘린더 MCP 도구 이름을 추가해야 한다 (연결 후 `claude mcp list`로 확인).
#
# 캘린더 계정 분리 (중요, 절대 섞이면 안 됨):
#   - 이 스크립트가 다루는 소스(vault/wiki/05-meetings/결정사항)는 전부 회사 Slack(#test_ob, OAO
#     워크스페이스)에서 나온 회의 결정사항이다 → 회사 캘린더(gkimam@oao-corp.com, mcp__claude_ai_Google_Calendar__*)에만 등록한다.
#   - 카카오톡/왓츠앱 등 personal/08-imports발 개인 일정은 절대 이 경로로 만들지 않는다.
#     개인 일정은 별도 계정 캘린더(kimgyuh04@gmail.com, mcp__google-calendar-personal__* MCP 서버,
#     `~/.config/google-calendar-mcp/`에 로컬 OAuth 토큰)를 쓴다 — 필요해지면 별도 스크립트로 분리할 것.
#   - allowedTools에 mcp__claude_ai_Google_Calendar__* 외의 캘린더 도구를 추가하지 말 것.
# 2026-08-12: 일부러 false 로 둔다.
#   이 단계는 회사 Slack #test_ob 에 "기한을 정해주세요" 메시지를 자동 게시한다.
#   2026-08-06 16:22 의 따옴표 버그로 6일간 죽어 있다가 오늘 고쳐졌는데, 그 사이
#   밀린 결정사항이 한꺼번에 처리되면 Slack에 여러 건이 몰려 게시된다.
#   밖으로 나가는 동작이라 자동 재개하지 않고, 사람이 확인한 뒤 true 로 바꾼다.
STAGE2_ENABLED=false
STAGE2_CALENDAR_ID="gkimam@oao-corp.com"  # 회사 캘린더 고정 — "기본/primary"에 의존하지 않는다

if [ "$STAGE2_ENABLED" = "true" ]; then
  SLACK_CHANNEL="test_ob"
  TODAY_KST=$(TZ=Asia/Seoul date +%Y-%m-%d)

  # 자격증명 처리는 lib/slack-auth.sh 로 일원화했다 (slack-collect.sh 와 공용).
  # 토큰 출처가 slack-sync 플러그인의 data.json 이었으나 .automation/.slack.env 로 옮겼다 —
  # 플러그인을 제거해도 STAGE2 가 깨지지 않게 하기 위해서다.
  # shellcheck source=lib/slack-auth.sh
  source "$VAULT_DIR/.automation/lib/slack-auth.sh"
  slack_auth_begin || exit 1

  PROMPT2="오늘 날짜(KST): ${TODAY_KST}. Slack 채널: #${SLACK_CHANNEL}.

중요: 이 작업에서 다루는 액션 아이템은 전부 회사 업무(회사 Slack 워크스페이스 결정사항)다. Google Calendar 도구를 호출할 때는 반드시 calendarId 파라미터에 '${STAGE2_CALENDAR_ID}'를 명시적으로 넣는다 ('기본/primary 캘린더' 같은 암묵적 대상에 의존하지 않는다). 이 값 외의 캘린더(특히 개인 Gmail 계정)에는 절대 일정을 만들지 않는다.

중요: Slack API를 호출할 때는 반드시 'curl -K .automation/.slack-auth.curlrc <나머지 옵션/URL>' 형태로 호출한다. 이 설정 파일에 Authorization 헤더가 이미 들어있다. 토큰 값 자체를 알아내거나, cat으로 읽거나, curl 명령 인자·Authorization 헤더에 직접 타이핑하지 않는다 (이 파일 경로를 참조하는 것만으로 충분하다).

.automation/action-items.json 을 상태 저장소로 쓴다. 스키마: [{id, source_doc, owner, task, status(awaiting_due_date|scheduled|reminded), due_date(YYYY-MM-DD|null), due_time(HH:MM, 24시간제, KST, 시각 언급 없었으면 null), slack_prompt_ts(string|null), calendar_event_id(string|null)}]

3단계로 처리한다:

[A] 신규 액션 아이템 발견
- vault/wiki/05-meetings/결정사항/*.md 를 훑어서, action-items.json에 아직 없는(source_doc 기준) 문서의 '## 액션 아이템'을 파싱해 새 항목들을 status=awaiting_due_date로 추가한다.
- 새로 추가된 항목이 있는 문서마다, curl -K .automation/.slack-auth.curlrc 로 https://slack.com/api/chat.postMessage 를 호출해 #${SLACK_CHANNEL}에 아래 형식으로 게시하고, 응답의 message ts를 그 문서의 모든 신규 항목의 slack_prompt_ts에 저장한다:
  '📋 <문서명> 액션 아이템 기한을 정해주세요:\n1) [담당자] 항목\n2) ...\n\n각 번호에 날짜로 답장해주세요 (예: 1) 8/10  2) 8/8). 스레드 답장이든 채널에 그냥 타이핑이든 상관없습니다.'

[B] 답장 확인
- status=awaiting_due_date 이고 slack_prompt_ts가 있는 항목들에 대해 답장을 찾는다. 두 가지 다 확인할 것:
  1) curl -K .automation/.slack-auth.curlrc 로 conversations.replies?channel=<채널ID>&ts=<slack_prompt_ts> (스레드로 답장한 경우)
  2) curl -K .automation/.slack-auth.curlrc 로 conversations.history?channel=<채널ID>&oldest=<slack_prompt_ts> (채널에 그냥 새 메시지로 타이핑한 경우 — ts가 slack_prompt_ts보다 크고 봇이 아닌 사람이 보낸 가장 가까운 메시지)
  (채널ID는 conversations.list?types=public_channel,private_channel 로 이름→ID 변환)
- 둘 중 어느 쪽이든 사람이 남긴 답장(봇 메시지 제외)을 찾으면 그 텍스트에서 번호별 날짜와 시각을 모두 파싱한다 (자연어 날짜/시각 허용 — 예: '8/10 오후 2시' → 날짜 2026-08-10, 시각 14:00. 연도 없으면 올해로 간주, KST 기준).
- 매칭된 항목은 status=scheduled, due_date(및 시각이 있으면 due_time)를 채우고, curl -K .automation/.slack-auth.curlrc 로 users.list 에서 owner 이름과 매칭되는 사용자를 찾아 Slack user id를 얻는다. 그 다음 사용 가능한 Google Calendar MCP 도구로 일정을 만든다:
  - due_time이 있으면 그 날짜·시각에 시작하는 1시간짜리 일정 (Asia/Seoul 타임존)
  - due_time이 없으면 그 날짜의 종일 일정
  제목: '[담당자] task 내용', 설명에 source_doc 경로 포함. 생성된 이벤트 id를 calendar_event_id에 저장한다.

[C] 당일 알림
- status=scheduled 이고 due_date == ${TODAY_KST} 인 항목에 대해, curl -K .automation/.slack-auth.curlrc 로 chat.postMessage 를 호출해 #${SLACK_CHANNEL}에 '<@SLACK_USER_ID>님, 오늘 이거 해야 함: <task>' 를 게시하고 status=reminded로 바꾼다. owner의 Slack user id를 못 찾으면 이름을 그대로 쓴다.

마지막에 A/B/C 각각 몇 건 처리했는지 한 줄로 요약 출력. 할 일이 전혀 없으면 '처리할 액션 아이템 없음'만 출력.

action-items.json 과 Slack API 호출 외의 다른 파일/서비스는 건드리지 않는다."

  {
    echo "=== $(date '+%Y-%m-%d %H:%M:%S') [3/3 액션아이템] 실행 시작 ==="
    retry 3 60 "$CLAUDE_BIN" -p "$PROMPT2" --allowedTools "Read Write Edit Glob Grep Bash(curl:*) mcp__claude_ai_Google_Calendar__create_event mcp__claude_ai_Google_Calendar__update_event mcp__claude_ai_Google_Calendar__list_events mcp__claude_ai_Google_Calendar__list_calendars" 2>&1
    echo "=== $(date '+%Y-%m-%d %H:%M:%S') [3/3 액션아이템] 실행 종료 ==="
    echo
  } >> "$LOG_FILE"

  slack_auth_cleanup   # trap 으로도 걸려 있으나, 여기서 즉시 지워 노출 시간을 줄인다
else
  echo "=== $(date '+%Y-%m-%d %H:%M:%S') [3/3 액션아이템] STAGE2_ENABLED=false, 건너뜀 ===" >> "$LOG_FILE"
fi
