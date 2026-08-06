#!/bin/bash
# Slack Sync가 vault/05-slack에 모아둔 원본을 읽어서
# vault/06-docs/{01-전사본,02-정리본,03-결정사항}에 3종 문서로 정리하는 headless Claude 실행 스크립트.
# launchd가 1시간마다 호출한다 (com.giana.obsidian-slack-docs-sync.plist).

set -euo pipefail

VAULT_DIR="/Users/gyuhyeongkim/orca/projects/obsidian_test"
CLAUDE_BIN="/Users/gyuhyeongkim/.local/bin/claude"
LOG_DIR="$VAULT_DIR/.automation/logs"
LOG_FILE="$LOG_DIR/$(date +%Y%m%d).log"

mkdir -p "$LOG_DIR"
cd "$VAULT_DIR"

PROMPT='vault/06-docs/_템플릿-가이드.md 파일을 먼저 읽고 그 형식을 그대로 따른다.

작업:
1. vault/05-slack/*.md 를 전부 확인한다.
2. 각 파일에 실질적인 내용(파일 첨부 📎 코드블록, 또는 의미 있는 회의/문서 텍스트)이 있는지 확인한다. "채널에 참여함" 같은 시스템 메시지나 멘션만 있는 빈 메시지는 건너뛴다.
3. 내용이 있는 파일에 대해, 그 안의 실제 날짜(문서/회의 내용에서 추론, 없으면 slack_url이나 created 필드 사용)와 주제로 파일명을 만들어서 vault/06-docs/01-전사본/, 02-정리본/, 03-결정사항/ 에 이미 같은 이름(YYMMDD-주제-*.md)의 결과물이 있는지 Glob으로 확인한다.
4. 이미 3종 다 있으면 건너뛴다 (중복 생성 금지). 하나라도 없으면 템플릿 가이드 형식대로 전사본/정리본/결정사항 3종을 새로 작성한다.
   - 전사본: 원문 보존, 요약 금지, 오탈자 교정 최소화
   - 정리본: 한줄요약/핵심논의(소주제별)/맥락배경/미결정사항/액션아이템(표) 구조
   - 결정사항: 결정사항/미결정보류/액션아이템 구조 (짧고 명확하게, 공식 결정이 없으면 "없음"으로 명시)
5. 처리한 원본과 새로 만든 문서 목록을 마지막에 요약해서 출력한다. 처리할 새 원본이 없으면 "처리할 새 원본 없음"이라고만 출력하고 끝낸다.

git commit/push는 하지 않는다 (obsidian-git이 별도로 자동 커밋한다). vault/05-slack, vault/06-docs 외의 파일은 건드리지 않는다.'

{
  echo "=== $(date '+%Y-%m-%d %H:%M:%S') [1/2 문서화] 실행 시작 ==="
  "$CLAUDE_BIN" -p "$PROMPT" --allowedTools "Read Write Edit Glob Grep" 2>&1
  echo "=== $(date '+%Y-%m-%d %H:%M:%S') [1/2 문서화] 실행 종료 ==="
  echo
} >> "$LOG_FILE"

# --- 2단계: 액션 아이템 → Slack 기한 문의 / 답장 파싱 / 캘린더 등록 / 당일 알림 ---
# 준비 상태(TODO)가 남아있으면 조용히 건너뛴다:
#   - Slack Bot Token에 chat:write, im:write 스코프가 추가돼야 함
#   - Google Calendar MCP 연결(claude.ai/customize/connectors)이 돼 있어야 함
#   둘 다 준비되면 이 스크립트의 STAGE2_ENABLED를 true로 바꾸고,
#   --allowedTools 에 정확한 캘린더 MCP 도구 이름을 추가해야 한다 (연결 후 `claude mcp list`로 확인).
STAGE2_ENABLED=false

if [ "$STAGE2_ENABLED" = "true" ]; then
  SLACK_TOKEN=$(python3 -c "import json;print(json.load(open('$VAULT_DIR/.obsidian/plugins/slack-sync/data.json'))['slackToken'])")
  SLACK_CHANNEL="test_ob"
  TODAY_KST=$(TZ=Asia/Seoul date +%Y-%m-%d)

  PROMPT2="오늘 날짜(KST): ${TODAY_KST}. Slack 채널: #${SLACK_CHANNEL}. Slack Bot Token은 환경변수 SLACK_TOKEN에 있다 (절대 출력/로그에 그대로 남기지 말고 curl 헤더에만 사용).

.automation/action-items.json 을 상태 저장소로 쓴다. 스키마: [{id, source_doc, owner, task, status(awaiting_due_date|scheduled|reminded), due_date(YYYY-MM-DD|null), slack_prompt_ts(string|null), calendar_event_id(string|null)}]

3단계로 처리한다:

[A] 신규 액션 아이템 발견
- vault/06-docs/03-결정사항/*.md 를 훑어서, action-items.json에 아직 없는(source_doc 기준) 문서의 '## 액션 아이템'을 파싱해 새 항목들을 status=awaiting_due_date로 추가한다.
- 새로 추가된 항목이 있는 문서마다, curl로 https://slack.com/api/chat.postMessage 를 호출해 #${SLACK_CHANNEL}에 아래 형식으로 게시하고, 응답의 message ts를 그 문서의 모든 신규 항목의 slack_prompt_ts에 저장한다:
  '📋 <문서명> 액션 아이템 기한을 정해주세요:\n1) [담당자] 항목\n2) ...\n\n각 번호에 날짜로 답장해주세요 (예: 1) 8/10  2) 8/8)'

[B] 답장 확인
- status=awaiting_due_date 이고 slack_prompt_ts가 있는 항목들에 대해, curl로 https://slack.com/api/conversations.replies?channel=<채널ID>&ts=<slack_prompt_ts> 를 호출해 사람이 남긴 답장(봇 메시지 제외)이 있는지 확인한다 (채널ID는 https://slack.com/api/conversations.list?types=public_channel,private_channel 로 이름→ID 변환).
- 답장 텍스트에서 번호별 날짜를 파싱한다 (자연어 날짜 허용, 연도 없으면 올해로 간주, KST 기준).
- 매칭된 항목은 status=scheduled, due_date를 채우고, curl로 https://slack.com/api/users.list 에서 owner 이름과 매칭되는 사용자를 찾아 Slack user id를 얻은 뒤, 사용 가능한 Google Calendar MCP 도구로 해당 날짜에 종일 일정을 만든다 (제목: '[담당자] task 내용', 설명에 source_doc 경로 포함). 생성된 이벤트 id를 calendar_event_id에 저장한다.

[C] 당일 알림
- status=scheduled 이고 due_date == ${TODAY_KST} 인 항목에 대해, curl로 chat.postMessage 를 호출해 #${SLACK_CHANNEL}에 '<@SLACK_USER_ID>님, 오늘 이거 해야 함: <task>' 를 게시하고 status=reminded로 바꾼다. owner의 Slack user id를 못 찾으면 이름을 그대로 쓴다.

마지막에 A/B/C 각각 몇 건 처리했는지 한 줄로 요약 출력. 할 일이 전혀 없으면 '처리할 액션 아이템 없음'만 출력.

action-items.json 과 Slack API 호출 외의 다른 파일/서비스는 건드리지 않는다."

  {
    echo "=== $(date '+%Y-%m-%d %H:%M:%S') [2/2 액션아이템] 실행 시작 ==="
    SLACK_TOKEN="$SLACK_TOKEN" "$CLAUDE_BIN" -p "$PROMPT2" --allowedTools "Read Write Edit Glob Grep Bash(curl:*)" 2>&1
    echo "=== $(date '+%Y-%m-%d %H:%M:%S') [2/2 액션아이템] 실행 종료 ==="
    echo
  } >> "$LOG_FILE"
else
  echo "=== $(date '+%Y-%m-%d %H:%M:%S') [2/2 액션아이템] STAGE2_ENABLED=false, 건너뜀 ===" >> "$LOG_FILE"
fi
