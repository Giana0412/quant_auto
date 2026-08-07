#!/bin/bash
# 분석봇: 오늘의 뉴스 다이제스트 + 시장 스냅샷을 종합해 "오늘의 결론"을 만들고
# 텔레그램으로 발송한다. launchd가 매일 20:30 KST에 호출한다
# (com.giana.daily-conclusion.plist) — 뉴스레터(20:00)·시장봇(20:15) 이후.

set -euo pipefail

VAULT_DIR="/Users/gyuhyeongkim/orca/projects/obsidian_test"
CLAUDE_BIN="/Users/gyuhyeongkim/.local/bin/claude"
LOG_DIR="$VAULT_DIR/.automation/logs"
LOG_FILE="$LOG_DIR/$(date +%Y%m%d).log"

mkdir -p "$LOG_DIR"
cd "$VAULT_DIR"

TODAY_KST=$(TZ=Asia/Seoul date +%y%m%d)
TODAY_ISO_KST=$(TZ=Asia/Seoul date +%Y-%m-%d)
CONCLUSION_PATH="personal/10-market/_conclusions/${TODAY_KST}-오늘의결론.md"

PROMPT="오늘 날짜(KST): ${TODAY_ISO_KST} (YYMMDD: ${TODAY_KST})

입력:
- personal/09-newsletters/_digests/${TODAY_KST}-일일요약.md (뉴스, 있을 수도 없을 수도 있음)
- personal/10-market/data/${TODAY_KST}-시장데이터.md (시장, 있을 수도 없을 수도 있음)

작업:
1. 둘 다 없으면 '오늘 종합할 자료 없음 — 결론 생략'만 출력하고 끝낸다.
2. 있는 것만 읽어서 종합한다 (하나만 있어도 그것 기준으로 작성, 없는 쪽은 언급하지 않는다).
3. ${CONCLUSION_PATH} 를 작성한다. **텔레그램 메시지로 그대로 보낼 것이므로 길게 쓰지 않는다** (전체 15줄 이내, 문어체 vault 문서가 아니라 폰 알림으로 읽기 좋은 간결한 톤). 텔레그램 Markdown 문법만 쓴다 (*bold*, _italic_, \`code\` — #, ## 같은 헤더 문법은 지원 안 되니 쓰지 않는다). 형식 예시:

📊 *오늘의 결론 (${TODAY_ISO_KST})*

*시장*: (1-2줄, 급등락 있으면 강조)
*뉴스*: (1-2줄, 오늘 가장 중요한 것)
*연결고리*: (시장과 뉴스가 이어지는 지점이 있으면 1줄, 없으면 이 줄 생략)
*주목*: (ALERT 난 지수/종목이 있으면 나열, 없으면 이 줄 생략)

_원문: vault/06-docs 등 필요시 경로만 짧게_

4. 파일을 다 쓴 뒤, 다음 명령으로 텔레그램에 발송한다:
   .automation/send_telegram.sh ${CONCLUSION_PATH}
   (이 스크립트는 텔레그램이 아직 설정 안 됐으면 조용히 건너뛴다 — 실패로 취급하지 않는다. 출력 결과를 그대로 보고해라.)

personal/10-market/_conclusions/ 외의 다른 파일은 건드리지 않는다. git commit/push는 하지 않는다."

{
  echo "=== $(date '+%Y-%m-%d %H:%M:%S') [분석봇] 실행 시작 ==="
  "$CLAUDE_BIN" -p "$PROMPT" --allowedTools "Read Write Glob Grep Bash(.automation/send_telegram.sh:*)" 2>&1
  echo "=== $(date '+%Y-%m-%d %H:%M:%S') [분석봇] 실행 종료 ==="
  echo
} >> "$LOG_FILE"
