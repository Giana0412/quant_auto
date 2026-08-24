#!/bin/bash
# 분석봇: 오늘의 뉴스 다이제스트 + 시장 스냅샷을 종합해 "오늘의 결론"을 만들고
# 텔레그램으로 발송한다. launchd가 매일 20:30 KST에 호출한다
# (com.giana.daily-conclusion.plist) — 뉴스레터(20:00)·시장봇(20:15) 이후.

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


# 체인이 자정을 넘겨도 단계들이 같은 날짜를 쓰도록 CHAIN_DATE 를 우선한다
TODAY_KST="${CHAIN_DATE:-$(TZ=Asia/Seoul date +%y%m%d)}"
TODAY_ISO_KST=$(TZ=Asia/Seoul date -j -f %y%m%d "$TODAY_KST" +%Y-%m-%d)
CONCLUSION_PATH="personal/10-market/_conclusions/${TODAY_KST}-오늘의결론.md"
EASY_PATH="personal/10-market/_conclusions/${TODAY_KST}-오늘의결론-쉬운설명.md"

PROMPT="오늘 날짜(KST): ${TODAY_ISO_KST} (YYMMDD: ${TODAY_KST})

용도: **블룸버그 터미널 매매대회 전략 세팅용 아침 브리핑.** 한국장 개장(09:00) 전에
읽고 그날 포지션을 잡는 데 쓴다. 대회는 전 세계 주식을 사고 평가는 벤치마크 대비
상대수익률이므로, **벤치마크를 이기는 쪽이 어디인가**만 중요하다.

입력:
- personal/10-market/data/${TODAY_KST}-시장데이터.md (지표, 있을 수도 없을 수도)
- personal/09-newsletters/_digests/${TODAY_KST}-일일요약.md (뉴스, 있을 수도 없을 수도)

작업:
1. 둘 다 없으면 '오늘 종합할 자료 없음 — 결론 생략'만 출력하고 끝낸다.
2. 있는 것만 읽어 종합한다. **없는 숫자를 지어내지 않는다.**
3. ${CONCLUSION_PATH} 를 작성한다. **오늘 날짜로 이미 있어도 Edit 이 아니라 Write 로
   전체를 새로 써서 덮어쓴다** (allowedTools 에 Edit 이 없어 부분 수정은 헤드리스에서
   승인 없이 그대로 멈춘다 — market-snapshot.sh 와 같은 이유). 텔레그램 Markdown 만 쓴다 (*bold*, \`code\`).
   **중요**: _italic_ 문법은 쓰지 않는다 — 파일 경로의 언더스코어와 겹치면 짝이 안 맞아
   메시지 전체 발송이 실패한다. 강조는 *bold* 만, 경로는 \`백틱\` 으로 감싼다.
   형식 (없는 절은 통째로 생략, 전체 22줄 이내):

📈 *마켓 ${TODAY_ISO_KST}*

*레짐*
(벤치마크 50MA 위/아래 · VIX · 브레드스 %와 장의 성격. 한 줄로)

*이기는 쪽* (벤치 대비 1개월)
(초과수익 플러스 상위 3개까지. **RS 지속일을 같이 적는다** — 승10일과 승1일은 다르다)

*지는 쪽*
(마이너스 하위 2~3개. **베타가 큰데 마이너스면 위험만 지는 조합**이라 베타를 같이 적는다.
 3개월은 플러스인데 RS 가 패로 돌아선 것이 있으면 그게 제일 중요하니 먼저 적는다)

*종목 후보*
(스크리닝 상위 2~3개를 티커·초과수익·베타로. 그 다음 줄에 피할 것 —
 하위 중 베타 큰 것들을 묶어서. 같은 섹터인데 상위·하위가 갈리면 그 사실을 적는다)

*주의*
(상관 0.8 이상 쌍이 있으면: 둘 다 사면 분산이 아니라 같은 베팅.
 스트레치(|z|>=1.5) 있으면 평균회귀 후보로 적는다. 둘 다 없으면 이 절 생략)

*종목*
(뉴스 연계 종목이 있으면 벤치 대비 1개월 초과수익과 함께. 없으면 생략)

*이벤트*
(실적발표 14일 내 목록이 있으면 D-N 으로. 없으면 이 절 생략)

*모델 북* (20%씩 5종목)
([포지션 사이징] 절 그대로: 티커 나열 + 북 베타 + 추적오차. 제외된 종목이 있으면
 왜(상관) 빠졌는지 한 줄. 추적오차가 크면 '변동성 큰 상대수익'이라고 짚는다)

*뉴스*
- (매매 판단에 영향 있는 것만 1줄씩, 최대 3개)

원문: \`personal/10-market/data/...\`

4. 파일을 쓴 뒤 텔레그램 **팀 그룹**에 발송한다:
   .automation/send_telegram.sh ${CONCLUSION_PATH} --to group
   (--to group 을 빼먹으면 팀이 아니라 개인방으로 간다. 스크립트가 미설정이면 조용히
    건너뛰므로 실패로 취급하지 않는다. 출력을 그대로 보고한다.)

5. ${EASY_PATH} 를 작성한다 — 같은 내용을 **왜 그런지까지 풀어쓴** 버전.
   숫자만 나열하지 말고 '이게 무슨 뜻이냐'를 설명한다. 예를 들어 베타가 4인 자산은
   벤치마크가 1% 움직일 때 4% 움직인다는 뜻이고, 상관이 0.95면 두 개를 나눠 사도
   한 곳에 몰아넣은 것과 같다는 식으로. 20줄 정도까지.
   여기서도 _italic_ 은 쓰지 않는다. **원본에 없는 숫자·사건을 만들지 않는다.**
6. ${EASY_PATH} 도 같은 그룹에 발송한다:
   .automation/send_telegram.sh ${EASY_PATH} --to group

personal/10-market/_conclusions/ 외의 다른 파일은 건드리지 않는다. git commit/push는 하지 않는다."

{
  echo "=== $(date '+%Y-%m-%d %H:%M:%S') [분석봇] 실행 시작 ==="
  retry 3 60 "$CLAUDE_BIN" -p "$PROMPT" --allowedTools "Read Write Glob Grep Bash(.automation/send_telegram.sh:*)" 2>&1
  echo "=== $(date '+%Y-%m-%d %H:%M:%S') [분석봇] 실행 종료 ==="
  echo
} >> "$LOG_FILE"
