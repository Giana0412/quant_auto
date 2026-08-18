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

# 네트워크 대기·재시도 — 깨어난 직후 Wi-Fi 가 안 올라온 상태에서 죽는 것을 막는다.
# 대기 기록도 일별 로그에 남긴다 (건너뛴 이유가 어딘가엔 있어야 한다).
source "$VAULT_DIR/.automation/lib/net.sh"
if ! wait_for_network >> "$LOG_FILE" 2>&1; then
  echo "=== $(date '+%Y-%m-%d %H:%M:%S') 네트워크 없음 — 이번 실행 건너뜀 ===" >> "$LOG_FILE"
  exit 0
fi


TODAY_KST=$(TZ=Asia/Seoul date +%y%m%d)
TODAY_ISO_KST=$(TZ=Asia/Seoul date +%Y-%m-%d)
CONCLUSION_PATH="personal/10-market/_conclusions/${TODAY_KST}-오늘의결론.md"
EASY_PATH="personal/10-market/_conclusions/${TODAY_KST}-오늘의결론-쉬운설명.md"

PROMPT="오늘 날짜(KST): ${TODAY_ISO_KST} (YYMMDD: ${TODAY_KST})

입력:
- personal/09-newsletters/_digests/${TODAY_KST}-일일요약.md (뉴스, 있을 수도 없을 수도 있음)
- personal/10-market/data/${TODAY_KST}-시장데이터.md (시장, 있을 수도 없을 수도 있음)

작업:
1. 둘 다 없으면 '오늘 종합할 자료 없음 — 결론 생략'만 출력하고 끝낸다.
2. 있는 것만 읽어서 종합한다 (하나만 있어도 그것 기준으로 작성, 없는 쪽은 언급하지 않는다).
3. ${CONCLUSION_PATH} 를 작성한다. **깔끔한 불렛포인트 위주, 설명 문장은 최소화한다** (전체 15줄 이내, 폰 알림으로 훑어보기 좋게 — 문장으로 풀어쓰지 말고 사실만 짧게 나열). 텔레그램 Markdown 문법만 쓴다 (*bold*, \`code\` — #, ## 같은 헤더 문법은 지원 안 되니 쓰지 않는다).
   **중요**: _italic_ 문법(밑줄 두 개로 감싸기)은 쓰지 않는다 — 파일 경로에 흔한 언더스코어(예: _digests, _conclusions)와 겹치면 텔레그램이 짝이 안 맞는 것으로 보고 메시지 전체 발송이 실패한다. 강조는 *bold*만 쓴다. 파일 경로를 넣을 땐 \`백틱\`으로 감싼다(코드 서식 안에서는 언더스코어가 안전하다).
   형식 (시장을 한국/미국/그외로 나눠서 불렛으로 — 없는 항목은 그 줄만 생략):

📊 *오늘의 결론 (${TODAY_ISO_KST})*

*시장*
🇰🇷 한국: 코스피 X,XXX (±X.X%), 코스닥 XXX (±X.X%)
🇺🇸 미국: S&P 500 (±X.X%), 나스닥 (±X.X%)
🌍 그외: 원/달러 X,XXX원, 금 (±X.X%)

   **묵은 숫자는 반드시 표시한다.** 시장데이터 파일의 표에 \`⏸ N일 전\` 이 붙은 줄이 있으면,
   그 줄의 텔레그램 항목 뒤에도 \`(N일 전)\` 을 붙인다. 예: \`🇺🇸 미국: S&P 500 -0.2% (4일 전)\`.
   휴장·데이터 지연으로 갱신이 안 된 것을 **오늘 움직인 것처럼 쓰지 않는다.**
   기준일이 오늘이 아닌 항목만 표시하면 되고, 오늘 것은 아무 표시도 하지 않는다.

*뉴스*
- (핵심 뉴스 1줄씩, 최대 3개)
- ...

*주목* (ALERT 있을 때만 이 섹션 포함)
- 티커/이름 (±X.X%) — 이유 한 줄

원문: \`personal/10-market/data/...\`, \`personal/09-newsletters/_digests/...\`

4. 파일을 다 쓴 뒤, 다음 명령으로 텔레그램에 발송한다:
   .automation/send_telegram.sh ${CONCLUSION_PATH}
   (이 스크립트는 텔레그램이 아직 설정 안 됐으면 조용히 건너뛴다 — 실패로 취급하지 않는다. 출력 결과를 그대로 보고해라.)

5. 이어서 ${EASY_PATH} 를 작성한다 — **같은 사실을 훨씬 쉽고 재밌게 풀어쓴 두 번째 버전**. 3번 버전이 팩트를 압축한 브리핑이라면, 이건 친한 친구가 오늘 있었던 일을 옆에서 조곤조곤 재밌게 설명해주는 버전이다.
   - 숫자·전문용어를 몰라도 이해되게 풀어쓴다 (예: '코스피 -4.58%' → '한국 주식시장 전체가 오늘 꽤 크게 빠졌어요'). 비유·일상적인 표현을 적극 쓴다.
   - 딱딱한 표/구조 대신 이야기하듯 자연스럽게 흐르게 쓴다. '오늘 제일 재밌었던 건', '한 줄로 말하면' 같은 후킹 문장으로 시작해도 좋다.
   - **사실을 과장하거나 지어내지 않는다** — 원본(뉴스 다이제스트/시장데이터)에 없는 숫자·사건을 만들지 않는다. 쉽게 풀어쓰는 것과 없는 걸 지어내는 건 다르다.
   - 이모지는 자유롭게 써도 되지만 과하지 않게. 분량은 3번 버전보다 길어도 된다(20줄 정도까지 — 텔레그램에서 편하게 읽히는 선).
   - 마찬가지로 _italic_ 문법은 쓰지 않는다(*bold*, \`code\`만). 파일 경로는 이 버전엔 안 넣어도 된다(원문은 3번 버전에 이미 있음).
6. ${EASY_PATH} 도 텔레그램에 발송한다:
   .automation/send_telegram.sh ${EASY_PATH}

personal/10-market/_conclusions/ 외의 다른 파일은 건드리지 않는다. git commit/push는 하지 않는다."

{
  echo "=== $(date '+%Y-%m-%d %H:%M:%S') [분석봇] 실행 시작 ==="
  retry 3 60 "$CLAUDE_BIN" -p "$PROMPT" --allowedTools "Read Write Glob Grep Bash(.automation/send_telegram.sh:*)" 2>&1
  echo "=== $(date '+%Y-%m-%d %H:%M:%S') [분석봇] 실행 종료 ==="
  echo
} >> "$LOG_FILE"
