#!/bin/bash
# 체인이 **오늘 돌았는지**를 체인 밖에서 확인한다. 독립 launchd 잡이다
# (com.giana.chain-watchdog.plist, 매일 14:00 KST).
#
# ── 왜 건강검진으로는 안 되는가 ────────────────────────────────────────────
# health-check.sh 는 evening-chain.sh 의 한 단계다. 그래서 **체인이 통째로 안 돌면
# 건강검진도 같이 침묵한다.** 설계 주석에 적힌 "매일 보내니까 안 오는 것 자체가
# 신호"는 사람이 매일 알림을 세고 있을 때만 성립한다. 2026-10-23 에 체인이
# 6시간 38분 걸려 브리핑이 통째로 날아갔을 때, 알아챈 건 그날 저녁 김규형이
# 직접 물어봤기 때문이었다.
#
# 이 스크립트는 그 **침묵을 양성 신호로 바꾼다.** 체인이 안 돌았으면 체인과
# 무관한 잡이 따로 깨어나서 알린다.
#
# ── 왜 헤드라인을 따로 보는가 ──────────────────────────────────────────────
# 시장데이터·결론은 하루 빠져도 다음 날 다시 만들면 된다. 헤드라인은 아니다 —
# yfinance 가 티커당 최근 ~20건만 줘서 하루 거르면 그날 기사가 영영 사라진다.
# 2026-11-14 학습 마감까지 날짜를 하루도 못 버린다 (§headline_status.py).
#
# ── 🔴 깨어날 때의 경쟁 조건 ───────────────────────────────────────────────
# 노트북이 꺼져 있다 20:00 에 깨면 launchd 가 밀린 잡을 **한꺼번에** 띄운다 —
# 체인(06:00·07:30)과 이 감시(14:00)가 같은 순간에 뜬다. 그대로 검사하면
# 체인이 아직 시작도 안 했는데 "안 돌았다"고 오보를 낸다.
# 그래서 ① 락이 살아 있으면 물러나고 ② 아니면 10분 간격으로 3번까지 다시 본다.
# 오탐 한 번이면 사람이 다음부터 알림을 안 본다 — 그게 제일 비싼 고장이다.
#
# 알림은 **문제가 있을 때만** 보낸다. 정상일 때의 하트비트는 건강검진이 이미
# 매일 보내고 있어서, 둘 다 보내면 하루 두 통이 되고 사람이 둘 다 안 보게 된다.
# 대신 자기가 살아 있다는 표시를 파일로 남기고(.watchdog-last), 건강검진이
# 그 파일이 오래됐는지 본다 — **서로 감시한다.**
#
# 사용법:
#   chain-watchdog.sh                # 평소 (launchd)
#   chain-watchdog.sh --dry-run      # 발송 없이 메시지만
#   chain-watchdog.sh --now          # 재시도 없이 즉시 1회 (수동 확인용)
#   chain-watchdog.sh 261023         # 특정 날짜를 소급 점검

set -uo pipefail   # -e 는 쓰지 않는다 — 검사 하나가 실패해도 나머지는 봐야 한다

VAULT_DIR="${VAULT_DIR:-$HOME/orca/projects/quant_auto}"
LOG_DIR="$VAULT_DIR/.automation/logs"
LOCK="$LOG_DIR/.evening-chain.lock"
BEAT="$LOG_DIR/.watchdog-last"
WLOG="$LOG_DIR/watchdog.log"

mkdir -p "$LOG_DIR"
cd "$VAULT_DIR" || exit 0

DRY=0; NOW=0; TARGET=""
for a in "$@"; do
  case "$a" in
    --dry-run) DRY=1 ;;
    --now)     NOW=1 ;;
    [0-9][0-9][0-9][0-9][0-9][0-9]) TARGET="$a"; NOW=1 ;;
  esac
done

TODAY="${TARGET:-$(TZ=Asia/Seoul date +%y%m%d)}"
MD=$(TZ=Asia/Seoul date -j -f %y%m%d "$TODAY" +%-m/%-d 2>/dev/null || echo "$TODAY")

# 그날 체인이 끝까지 갔는지. **로그가 아니라 완주 표시를 본다** — "시작"은
# 성공을 뜻하지 않는다(건강검진 설계 1번 규칙).
chain_done() {
  grep -q '\[저녁체인\] 종료' "$LOG_DIR/20${1}.log" 2>/dev/null
}
# 손으로 건너뛴 날은 고장이 아니다.
chain_skipped() {
  [ -f "$LOG_DIR/.skip-${1}" ]
}
# 락을 살아있는 프로세스가 쥐고 있으면 지금 도는 중이다.
chain_running() {
  local pid
  pid=$(cat "$LOCK/pid" 2>/dev/null || echo "")
  [ -n "$pid" ] && kill -0 "$pid" 2>/dev/null
}

# ── 재시도 ────────────────────────────────────────────────────────────────
# 깨어날 때 체인과 같이 떴을 수 있으니 바로 단정하지 않는다.
TRIES=3; [ "$NOW" -eq 1 ] && TRIES=1
for ((i = 1; i <= TRIES; i++)); do
  if chain_done "$TODAY" || chain_skipped "$TODAY"; then break; fi
  if [ "$i" -lt "$TRIES" ]; then
    chain_running && [ "$DRY" -eq 0 ] \
      && echo "$(date '+%F %T') 체인 실행 중 — ${i}/${TRIES} 대기" >> "$WLOG"
    sleep 600
  fi
done

# 🔴 살아있다는 표시. 건강검진이 이걸 본다.
# dry-run 은 쓰지 않는다 — 사람이 손으로 테스트한 게 "감시견이 돌았다"로
# 둔갑하면, 정작 잡이 죽었을 때 건강검진이 그걸 못 잡는다.
[ "$DRY" -eq 1 ] || date '+%F %T' > "$BEAT"

PROBLEMS=()

# ① 체인 완주 여부 + 며칠째인지.
#    "오늘 안 돌았다"보다 "3일째 안 돌았다"가 훨씬 크게 들린다(건강검진 설계 3번).
if chain_skipped "$TODAY"; then
  :
elif chain_done "$TODAY"; then
  :
elif chain_running; then
  START=$(grep -m1 '\[저녁체인\] 시작' "$LOG_DIR/20${TODAY}.log" 2>/dev/null \
          | sed -n 's/^=== \([0-9-]* [0-9:]*\) .*/\1/p')
  if [ -n "$START" ]; then
    MINS=$(( ( $(date +%s) - $(date -j -f '%Y-%m-%d %H:%M:%S' "$START" +%s 2>/dev/null || date +%s) ) / 60 ))
    # 평소 10분이다. 3시간을 넘겼으면 자다 깨다 하는 중이라 사실상 실패다
    # (10/23 에 6시간 38분이 걸렸고 브리핑은 못 나갔다).
    [ "$MINS" -gt 180 ] && PROBLEMS+=("체인이 ${MINS}분째 안 끝남 (${START} 시작) — 절전 의심")
  fi
else
  STREAK=0
  for i in $(seq 0 13); do
    d=$(TZ=Asia/Seoul date -j -v-"${i}"d -f %y%m%d "$TODAY" +%y%m%d 2>/dev/null) || break
    chain_skipped "$d" && continue
    chain_done "$d" && break
    STREAK=$((STREAK + 1))
  done
  PROBLEMS+=("체인 ${STREAK}일째 완주 못 함 — 브리핑이 안 나갔다")
fi

# ② 헤드라인 수집. 하루 거르면 복구가 안 되므로 따로 본다.
eval "$(python3 "$VAULT_DIR/.automation/headline_status.py" 2>/dev/null \
        | grep -E '^[A-Z_]+=' || true)"
LAST_DATE="${LAST_DATE:--}"; DAYS_STALE="${DAYS_STALE:-999}"
ROWS_LAST="${ROWS_LAST:-0}"; DATES_LABELED="${DATES_LABELED:-0}"
NEED="${NEED:-20}"; READY="${READY:-0}"
STATUS="${STATUS:-missing}"   # STATUS 줄이 없으면 스크립트 자체가 안 돈 것

# 체인은 06:00 KST(=전날 17:00 ET)에 도니 **1일 뒤처진 게 정상**이다.
# 🔴 조회 실패를 정체로 보고하면 오보가 된다 — 둘은 다른 고장이다.
if [ "$STATUS" = "missing" ]; then
  PROBLEMS+=("헤드라인 상태 조회 실패 — .automation/headline_status.py 확인")
elif [ "$DAYS_STALE" -gt 2 ] 2>/dev/null; then
  PROBLEMS+=("헤드라인 ${DAYS_STALE}일째 안 늘어남 (마지막 ${LAST_DATE}) — 날짜는 소급 복구 불가")
elif [ "$ROWS_LAST" -lt 50 ] 2>/dev/null && [ "$DAYS_STALE" -le 2 ] 2>/dev/null; then
  # 평일은 400~900건, 주말은 10~30건이다. 50건 미만이 평일이면 반쪽 수집이다.
  DOW=$(TZ=Asia/Seoul date -j -f %Y-%m-%d "$LAST_DATE" +%u 2>/dev/null || echo 6)
  [ "$DOW" -le 5 ] 2>/dev/null \
    && PROBLEMS+=("헤드라인 ${LAST_DATE} 가 ${ROWS_LAST}건뿐 — 반쪽 수집 의심") || true
fi

# ── 발송 ──────────────────────────────────────────────────────────────────
if [ ${#PROBLEMS[@]} -eq 0 ]; then
  LINE="정상 · 헤드라인 ${LAST_DATE} ${ROWS_LAST}건 · 라벨날짜 ${DATES_LABELED}일"
  [ "$READY" -eq 1 ] && LINE="$LINE · 🎓 학습 가능" || LINE="$LINE (학습까지 D-${NEED})"
  if [ "$DRY" -eq 1 ]; then
    echo "── dry-run (${TODAY}) — 문제 없음, 발송 안 함 ──"; echo "$LINE"
  else
    echo "$(date '+%F %T') $LINE" >> "$WLOG"
  fi
  exit 0
fi

MSG_FILE=$(mktemp -t chainwatchdog)
trap 'rm -f "$MSG_FILE"' EXIT INT TERM
{
  printf '🚨 *%s 체인 감시*\n' "$MD"
  for p in "${PROBLEMS[@]}"; do printf -- '- %s\n' "$p"; done
  printf '\n헤드라인 마지막 %s (%s건) · 라벨날짜 %s일' "$LAST_DATE" "$ROWS_LAST" "$DATES_LABELED"
  [ "$READY" -eq 1 ] && printf ' · 학습 가능\n' || printf ' · 학습까지 D-%s\n' "$NEED"
  printf '\n손으로 돌리기: `bash .automation/evening-chain.sh`\n'
} > "$MSG_FILE"

if [ "$DRY" -eq 1 ]; then
  echo "── dry-run (${TODAY}) — 발송하지 않음 ──"
  cat "$MSG_FILE"
  exit 0
fi

{
  echo "$(date '+%F %T') 🚨 ${PROBLEMS[*]}"
  "$VAULT_DIR/.automation/send_telegram.sh" "$MSG_FILE" 2>&1 || echo "발송 실패"
} >> "$WLOG"
