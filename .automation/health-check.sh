#!/bin/bash
# 자동화 건강검진. launchd가 매일 20:45 KST에 호출한다 (com.giana.health-check.plist)
# — 뉴스레터(20:00)·시장봇(20:15)·분석봇(20:30) 이 전부 끝난 뒤다.
#
# ── 왜 만들었나 ────────────────────────────────────────────────────────────
# 같은 사고가 두 번 났다.
#   ① 슬랙 수집이 6일간 죽어 있었다 (셸 따옴표 하나 → exit 127)
#   ② 뉴스레터가 11일간 0건이었다 (.gmail.env 없음, 8/07~8/18)
# 둘 다 로그에는 매일 🔴로 찍혔는데 아무도 안 봤고, launchd는 종료코드 0으로
# "성공"이라 보고했다. 조사한 stigmergy 운영 런북에도 같은 함정이 적혀 있다 —
# "건너뛴 잡은 초록색으로 보인다. 그래서 별도 장부로 확인해야 한다."
#
# ── 설계 ──────────────────────────────────────────────────────────────────
# 1. **로그가 아니라 산출물을 본다.** 로그의 "실행 시작"은 성공을 뜻하지 않는다.
#    파일이 실제로 생겼는지를 본다.
# 2. **매일 보낸다(하트비트).** 문제 있을 때만 보내면 이 스크립트가 죽었을 때
#    조용해지는데, 그게 정확히 지금까지의 실패 방식이다. 매일 한 줄이 오면
#    **안 오는 것 자체가 신호**가 된다.
# 3. **며칠째인지 센다.** "오늘 0건"보다 "6일째 0건"이 훨씬 크게 들린다.
#
# grep 이 0건일 때 1을 반환해 set -e 로 죽는 것이 ①의 원인이었으므로,
# 이 파일의 모든 grep/count 는 `|| true` 로 감쌌다.

set -euo pipefail

VAULT_DIR="/Users/gyuhyeongkim/orca/projects/obsidian_test"
LOG_DIR="$VAULT_DIR/.automation/logs"
LOG_FILE="$LOG_DIR/$(date +%Y%m%d).log"

mkdir -p "$LOG_DIR"
cd "$VAULT_DIR"

source "$VAULT_DIR/.automation/lib/net.sh"
if ! wait_for_network >> "$LOG_FILE" 2>&1; then
  echo "=== $(date '+%Y-%m-%d %H:%M:%S') [건강검진] 네트워크 없음 — 건너뜀 ===" >> "$LOG_FILE"
  exit 0
fi

# 인자로 YYMMDD 를 주면 그날을 점검한다 (테스트·소급 확인용). 없으면 오늘.
# --dry-run 을 같이 주면 텔레그램을 보내지 않고 메시지만 출력한다.
DRY=0
TARGET=""
for a in "$@"; do
  case "$a" in
    --dry-run) DRY=1 ;;
    [0-9][0-9][0-9][0-9][0-9][0-9]) TARGET="$a" ;;
  esac
done

# 체인이 자정을 넘겨도 단계들이 같은 날짜를 쓰도록 CHAIN_DATE 를 우선한다
TODAY="${TARGET:-${CHAIN_DATE:-$(TZ=Asia/Seoul date +%y%m%d)}}"
MD=$(TZ=Asia/Seoul date -j -f %y%m%d "$TODAY" +%-m/%-d 2>/dev/null || echo "$TODAY")

# 점검 대상일의 로그 (인자로 과거 날짜를 주면 그날 로그를 본다)
LOG_FILE="$LOG_DIR/20${TODAY}.log"

# 해당 날짜의 뉴스레터 개수. **`ls` 를 `|| true` 로 감싸는 게 핵심** —
# 매치가 없으면 ls 가 1을 반환하고, pipefail 때문에 파이프라인 전체가 실패해
# set -e 가 스크립트를 죽인다. 이게 슬랙 수집을 6일간 죽였던 것과 같은 함정이라
# 여기서 두 번째로 밟았다. 매치 없음은 정상 상태이지 에러가 아니다.
count_news() {
  { ls personal/09-newsletters/{newneek,uppity,bloomberg}/"$1"-* 2>/dev/null || true; } \
    | grep -c . || true
}

# 대상일부터 거슬러 올라가며 발행물이 있는 첫 날을 찾는다 → "며칠째 0건"을 센다.
# "오늘 0건"보다 "11일째 0건"이 훨씬 크게 들리기 때문에 이 숫자가 핵심이다.
news_streak() {
  local i d cnt
  for i in $(seq 0 30); do
    d=$(TZ=Asia/Seoul date -j -v-"${i}"d -f %y%m%d "$TODAY" +%y%m%d 2>/dev/null) || break
    cnt=$(count_news "$d")
    if [ "${cnt:-0}" -gt 0 ]; then echo "$i|$d"; return; fi
  done
  echo "31+|-"
}

NEWS_TODAY=$(count_news "$TODAY")
STREAK_RAW=$(news_streak)
STREAK_DAYS="${STREAK_RAW%%|*}"
STREAK_LAST="${STREAK_RAW##*|}"

MARKET_FILE="personal/10-market/data/${TODAY}-시장데이터.md"
CONCL_FILE="personal/10-market/_conclusions/${TODAY}-오늘의결론.md"
[ -f "$MARKET_FILE" ] && MARKET_OK=1 || MARKET_OK=0
[ -f "$CONCL_FILE" ]  && CONCL_OK=1  || CONCL_OK=0

# 슬랙 수집 파이프라인은 2026-08-19 회사용 자동화를 걷어내면서 제거했다.
# 없어진 잡을 계속 찾으면 매일 오탐이 나므로 점검 항목에서도 뺐다.

# 로그의 오류 표시.
# **자기가 쓴 줄은 빼야 한다.** 이 스크립트도 문제를 발견하면 로그에 남기는데,
# 그 표시를 다음 실행이 "오류"로 다시 세면 한 번 문제가 난 뒤로는 영원히 🔴 이 되고
# 숫자가 실행할 때마다 늘어난다 (실제로 2→4건으로 불어났다). 슬랙 수집기가 자기 봇
# 메시지를 다시 수집하던 것과 같은 되먹임이라, 자기 출력은 다른 표시(`문제:`)를 쓴다.
ERRORS=$(grep -c '🔴' "$LOG_FILE" 2>/dev/null || true)
ERRORS=${ERRORS:-0}

# 프롬프트 문자열이 끊기는 버그 정적 검사.
# 건강검진은 원래 증상만 본다("시장데이터 파일 없음"). 이걸 같이 돌리면 **원인**까지
# 알려줄 수 있다 — 실제로 그 사고의 원인이 market-snapshot.sh 43행의 큰따옴표였다.
PROMPT_BAD=$(python3 "$VAULT_DIR/.automation/check_prompts.py" 2>/dev/null | grep '^🔴' | head -3 || true)

PROBLEMS=()
if [ -n "$PROMPT_BAD" ]; then
  while IFS= read -r line; do
    [ -n "$line" ] && PROBLEMS+=("${line#🔴 }")
  done <<< "$PROMPT_BAD"
fi
# 뉴스레터는 주말·공휴일에 원래 안 온다. 하루 0건으로 매주 알림이 오면 사람이
# 알림을 무시하게 되고, 그러면 진짜 고장도 같이 묻힌다. **연속 3일 이상**일 때만
# 문제로 본다 — 11일 장애는 잡고 주말은 안 잡는 선.
[ "${STREAK_DAYS%%+*}" -ge 3 ] 2>/dev/null \
  && PROBLEMS+=("뉴스레터 ${STREAK_DAYS}일째 0건 (마지막 ${STREAK_LAST})") || true
[ "$MARKET_OK" -eq 0 ] && PROBLEMS+=("시장데이터 파일 없음")
[ "$CONCL_OK" -eq 0 ]  && PROBLEMS+=("오늘의결론 파일 없음")
[ "$ERRORS" -gt 0 ] && PROBLEMS+=("로그에 오류 표시 ${ERRORS}건")

MSG_FILE=$(mktemp -t healthcheck)
trap 'rm -f "$MSG_FILE"' EXIT INT TERM

if [ ${#PROBLEMS[@]} -eq 0 ]; then
  printf '✅ *%s 자동화 정상*\n뉴스 %s · 시장 ✓ · 결론 ✓\n' \
    "$MD" "$NEWS_TODAY" > "$MSG_FILE"
else
  {
    printf '🔴 *%s 자동화 점검*\n' "$MD"
    for p in "${PROBLEMS[@]}"; do printf -- '- %s\n' "$p"; done
    printf '\n로그: `.automation/logs/20%s.log`\n' "$TODAY"
  } > "$MSG_FILE"
fi

if [ "$DRY" -eq 1 ]; then
  echo "── dry-run (${TODAY}) — 발송하지 않음 ──"
  cat "$MSG_FILE"
  exit 0
fi

{
  echo "=== $(date '+%Y-%m-%d %H:%M:%S') [건강검진] 실행 시작 ==="
  echo "뉴스 ${NEWS_TODAY}건 / 시장 ${MARKET_OK} / 결론 ${CONCL_OK} / 오류 ${ERRORS}건"
  # 자기 발견은 🔴 이 아니라 '문제:' 로 쓴다 — 위 ERRORS 계산이 이 줄을 다시 세면
  # 되먹임이 생긴다 (2→4건으로 불어났던 실제 버그).
  if [ ${#PROBLEMS[@]} -gt 0 ]; then printf '  문제: %s\n' "${PROBLEMS[@]}"; fi
  "$VAULT_DIR/.automation/send_telegram.sh" "$MSG_FILE" 2>&1 || echo "발송 실패"
  echo "=== $(date '+%Y-%m-%d %H:%M:%S') [건강검진] 실행 종료 ==="
  echo
} >> "$LOG_FILE"
