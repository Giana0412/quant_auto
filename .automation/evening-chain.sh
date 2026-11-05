#!/bin/bash
# (원래 저녁 체인이었으나 매매대회 아침 브리핑 용도로 스케줄을 옮겼다 —
# 이름은 남아 있지만 실제로는 "아침 체인"이다.) 뉴스레터 → 시장 → 결론 → 점검을
# **순서대로 하나씩** 돌린다. launchd 가 매일 06:00 KST 에 이것 하나만 부른다
# (com.giana.evening-chain.plist) — 그날 그물이 안 걸리면 07:30 에 백업으로 한 번 더.
# 한국장 개장(09:00) 전에 텔레그램 그룹에 브리핑이 도착하게 하려는 시간이다.
#
# ── 왜 하나로 합쳤나 ──────────────────────────────────────────────────────
# 예전에는 잡 4개를 15분 간격(20:00·20:15·20:30·20:45)으로 따로 걸었다.
# 그 전제는 "각 단계가 15분 안에 끝난다"였는데, **노트북이 자고 있으면 무너진다.**
#
# 2026-08-19 실제로 벌어진 일:
#   21:47:16  뉴스레터 시작 (20:00 잡이 1시간 47분 늦게 깨어남)
#   22:03:38  시장봇 + 건강검진이 **동시에** 시작 (뉴스레터가 아직 도는 중)
#   22:03:40  건강검진: 뉴스 0 / 시장 0 / 결론 0 → 🔴 알림 발송
#   22:03:46  분석봇 시작 → 재료가 아직 없어서 "종합할 자료 없음" 하고 끝
#   22:03:57  뉴스레터 종료 → 그제서야 다이제스트 시작
#   08:17:52  다이제스트 종료 (다음날 아침)
# 결과: 그룹에 결론이 한 통도 안 갔고, 개인방엔 오탐 경보가 갔다.
#
# macOS launchd 는 `StartCalendarInterval` 잡이 잠든 사이 지나가면 **깨어날 때 한꺼번에**
# 실행한다. 잡이 여러 개면 전부 같은 순간에 뜨고 순서가 사라진다.
# 그래서 잡을 **하나로 줄이고 순서를 스크립트가 책임진다.** 밀려도 순서는 지켜진다.
#
# ── 설계 ────────────────────────────────────────────────────────────────
# - 앞 단계가 끝나야 다음이 시작한다 (재료가 준비된 뒤에 소비한다)
# - 한 단계가 실패해도 나머지는 계속한다. 마지막 건강검진이 무엇이 빠졌는지 알린다
# - 락으로 중복 실행을 막는다 (깨어날 때 두 번 뜨는 경우 대비)

set -uo pipefail   # -e 는 쓰지 않는다 — 한 단계가 실패해도 체인은 계속 가야 한다

# ── 노트북이 자면 체인이 죽는다 ────────────────────────────────────────────
# 2026-10-23 실제로 벌어진 일:
#   06:13  시작
#   07:51  archive-newsletters ✅ (1시간 38분 — 평소 1분 20초)
#   12:29  market-snapshot 🔴 600초 초과로 중단 (4시간 38분 경과)
#   12:30  daily-conclusion — 재료가 없어 22초 만에 빈손 종료
# 로그에 원인이 그대로 찍혀 있었다:
#   "API Error: Your computer went to sleep mid-response."
# 그날 그룹에 간 건 이벤트 알림뿐이고 **브리핑은 통째로 날아갔다.**
#
# 🔴 2026-10-25 정정. 여기 오래 적혀 있던 "timeout 의 상한은 벽시계 기준이라
# 자는 동안에도 시간이 흐른다" 는 **틀렸다.** macOS 절전 중에는 timeout 의
# 타이머가 **멈춘다.** 그날 실측:
#   06:26:40 → 07:43:25  market-snapshot 77분 걸렸는데 상한은 600초, rc=0
# 깨어난 순간 초과로 죽는 게 아니라 **아예 안 죽는다.** 즉 단계 상한은
# 절전에 대해 아무 보호도 못 한다. 보호는 두 가지로만 가능하다 —
#   ① 안 자게 한다 (전원을 꽂는다. 아래 caffeinate 로는 반쪽만 된다)
#   ② 자버렸다는 걸 **사후에 알아챈다** (단계마다 소요초를 직접 재서 기록 — §단계)
#
# caffeinate 로 자신을 다시 띄운다. -i 는 유휴 절전을 막는다.
# 🔴 -s 는 **전원이 연결된 동안에만** 시스템 절전을 막는다. 배터리로 돌면
# 무력하고, 뚜껑을 닫은 클램셸 절전은 -i 로도 못 막는다. 2026-10-25 에
# 배터리 15% + 뚜껑 닫힘으로 체인이 4시간 52분을 기어갔다 — 15분마다 2~45초씩
# DarkWake 하는 동안에만 전진했다. 10/24 에 10분 만에 끝난 건 caffeinate 가
# 고쳐서가 아니라 그때 전원이 꽂혀 있었기 때문이다.
# 그래서 코드가 할 수 있는 건 "안 꽂혔으면 알리는 것"까지다 (§전원 확인).
# CHAIN_CAFFEINATED 로 재귀를 끊는다. 🔴 락을 잡기 **전에** 해야 한다 —
# 락을 잡고 exec 하면 trap 이 날아가 락이 영영 안 풀린다.
if [ -z "${CHAIN_CAFFEINATED:-}" ] && command -v caffeinate >/dev/null 2>&1; then
  export CHAIN_CAFFEINATED=1
  exec caffeinate -i -s "/Users/gyuhyeongkim/orca/projects/quant_auto/.automation/evening-chain.sh" "$@"
fi

VAULT_DIR="${VAULT_DIR:-$HOME/orca/projects/quant_auto}"
LOG_DIR="$VAULT_DIR/.automation/logs"
LOG_FILE="$LOG_DIR/$(date +%Y%m%d).log"
LOCK="$LOG_DIR/.evening-chain.lock"

mkdir -p "$LOG_DIR"
cd "$VAULT_DIR"

# timeout 은 macOS 기본 명령이 아니다 (homebrew coreutils). 없으면 단계 상한이
# 통째로 사라지므로 조용히 넘어가지 않고 여기서 멈춘다 — 상한 없는 실행이
# 정확히 이번 사고의 원인이었다.
if ! command -v timeout >/dev/null 2>&1; then
  echo "=== $(date '+%Y-%m-%d %H:%M:%S') [저녁체인] 🔴 timeout 명령 없음 — 중단 (brew install coreutils) ===" >> "$LOG_FILE"
  exit 1
fi

# 오늘 하루만 건너뛰기. 손으로 이미 돌렸을 때 저녁에 또 나가는 걸 막는 용도다.
#   touch .automation/logs/.skip-$(TZ=Asia/Seoul date +%y%m%d)
# 표시 파일에 날짜가 박혀 있어 **다음 날 자동으로 무효**가 된다 — 끄고 켜는 걸
# 잊어버려서 며칠씩 안 도는 사고를 막기 위해서다.
SKIP_FILE="$LOG_DIR/.skip-$(TZ=Asia/Seoul date +%y%m%d)"
if [ -f "$SKIP_FILE" ]; then
  echo "=== $(date '+%Y-%m-%d %H:%M:%S') [저녁체인] 오늘은 건너뜀 ($(basename "$SKIP_FILE")) ===" >> "$LOG_FILE"
  exit 0
fi

# 중복 실행 방지. mkdir 은 원자적이라 락으로 쓸 수 있다.
# **락 안에 PID 를 적어두고 회수할 때 그 프로세스가 살아있는지 확인한다.**
# 예전엔 "6시간 지났으면 회수"였는데, 그러면 앞 실행이 아직 매달려 있는데도
# 새 체인을 띄워 둘이 동시에 돈다. 시간이 아니라 생사로 판단해야 한다.
if ! mkdir "$LOCK" 2>/dev/null; then
  holder=$(cat "$LOCK/pid" 2>/dev/null || echo "")
  if [ -n "$holder" ] && kill -0 "$holder" 2>/dev/null; then
    echo "=== $(date '+%Y-%m-%d %H:%M:%S') [저녁체인] 이미 실행 중 (PID $holder) — 건너뜀 ===" >> "$LOG_FILE"
    exit 0
  fi
  echo "=== $(date '+%Y-%m-%d %H:%M:%S') [저녁체인] 죽은 락 회수 (PID ${holder:-불명}) ===" >> "$LOG_FILE"
  rm -rf "$LOCK"
  mkdir "$LOCK" 2>/dev/null || { echo "락 생성 실패" >> "$LOG_FILE"; exit 1; }
fi
echo $$ > "$LOCK/pid"
trap 'rm -rf "$LOCK" 2>/dev/null || true' EXIT INT TERM

# 체인이 자정을 넘겨도 모든 단계가 **같은 날짜**를 쓰게 고정한다.
# 8/21 실행이 다음날 10:19 에 끝났는데, 1단계는 260821 뉴스레터를 저장하고
# 3단계는 260822 파일을 찾다가 "종합할 자료 없음"으로 끝냈다. 그래서 발송이 0이었다.
export CHAIN_DATE="${CHAIN_DATE:-$(TZ=Asia/Seoul date +%y%m%d)}"
CHAIN_LOG="$LOG_DIR/20${CHAIN_DATE}.log"

# 오늘 이미 그룹으로 나갔으면 다시 안 보낸다.
# 이 레포의 자동화는 **하루 한 번 시도가 전부**여서, 그날 네트워크가 한 번 흔들리면
# 그대로 끝났다. 실제 실패 원인은 날마다 달랐다 —
#   08-18 세션 한도 / 08-22 IMAP 무한 대기 / 08-23 DNS 실패(ENOTFOUND)
# 공통점은 "재시도가 없었다"는 것이라, 저녁에 한 번 더 도는 백업 실행을 붙였다.
# 이 검사가 그 두 번째 실행이 중복 발송하지 않게 막아준다.
if grep -q '발송 성공 → 그룹' "$CHAIN_LOG" 2>/dev/null; then
  echo "=== $(date '+%Y-%m-%d %H:%M:%S') [저녁체인] 오늘 이미 그룹 발송 완료 — 건너뜀 ===" >> "$LOG_FILE"
  exit 0
fi

CHAIN_T0=$(date +%s)
{
  echo "=== $(date '+%Y-%m-%d %H:%M:%S') [저녁체인] 시작 ==="
} >> "$LOG_FILE"

# ── 전원 확인 ─────────────────────────────────────────────────────────────
# 🔴 배터리로 돌면 체인이 기어간다(위 caffeinate 주석). 막을 방법이 없으니 **알린다.**
# 체인을 멈추지는 않는다 — 느리게라도 헤드라인은 주워야 한다. 날짜는 소급이
# 안 되므로 하루 거르면 그날 기사는 영영 못 줍는다 (§headline_status.py).
# 이 줄을 감시견이 읽는다 (§chain-watchdog.sh) — 그래서 문구를 바꾸면 거기도 봐야 한다.
if ! pmset -g batt 2>/dev/null | grep -q 'AC Power'; then
  BATT=$(pmset -g batt 2>/dev/null | sed -n 's/.*[^0-9]\([0-9]\{1,3\}\)%.*/\1/p' | head -1)
  echo "=== $(date '+%Y-%m-%d %H:%M:%S') [저녁체인] ⚠️ 배터리 구동 (${BATT:-?}%) — 절전으로 느려질 수 있다 ===" >> "$LOG_FILE"
fi

# 단계마다 상한 시간을 둔다. **무엇도 영원히 매달려선 안 된다.**
# newsletter_fetch 가 IMAP 에서 23시간 멈춰 락을 붙잡은 사고가 이 규칙이 없어서
# 났다. 상한을 넘기면 죽이고 다음 단계로 간다 — 멈추는 것보다 실패가 낫다.
# (timeout 124 = 시간 초과. 체인 전체 상한은 이 합인 35분.)
#
# 🔴 2026-09-13 market-snapshot 을 420 → 600 으로 올렸다. 스크립트가 느려진 게
# 아니라 **LLM 작성 단계가 길어졌다** — 실측으로 market_metrics 71초 +
# news_sentiment 31초 = 102초뿐이고 나머지가 전부 claude -p 다. 그날 하루에만
# 프롬프트에 절이 셋 늘어(워치리스트·매크로일정·뉴스대조) 마크다운 작성량이
# 늘었고, 같은 날 13:52 런은 278초에 끝났는데 14:22 런은 420초를 넘겼다.
# daily-conclusion 도 같은 이유로 420 → 480. 절을 더 붙일 때마다 여기를 같이 봐야 한다.
declare -a STEPS=(
  "archive-newsletters:900"   # 메일 수집 + 다이제스트 — 제일 오래 걸린다
  "market-snapshot:600"       # 스크립트 102초 + LLM. 절이 늘면 LLM 쪽이 늘어난다
  # TradingAgents 세컨드 오피니언(§agent_review.py) — 구독(claude -p)으로 돈다.
  # 실측 2026-11-06: GILD 1종목 293초(애널리스트 3 + 토론 + 매니저, 호출당 ~5초).
  # 6종목 ÷ 동시 2 = 3물결 × ~300초 ≈ 15분. 상한은 2배 남짓으로 잡는다.
  # 결론보다 앞이어야 결론이 읽는다 — 그만큼 브리핑이 15분 늦어진다.
  "agent-review:2000"
  "daily-conclusion:480"
  "dashboard-push:60"        # 결론을 팀 대시보드(Streamlit) 브리핑 탭으로 — 구글 시트 경유(§push_briefing.py)
  "event-alerts:90"        # 감시 창에 새로 들어온 이벤트만 팀 그룹에 알린다(조용한 날은 조용)
  "health-check:120"
  # 🔴 아래는 **브리핑 본체가 아니다.** 개인 연구용 데이터 수집이라 맨 뒤에 둔다 —
  # 앞에 끼우면 그만큼 브리핑이 한국장 개장(09:00) 쪽으로 밀린다. 여기 있으면
  # 느려져도 자기만 늦고, 실패해도 브리핑은 이미 나간 뒤다.
  # 209종목 × 뉴스 + 189종목 가격이라 실측 3~4분. 상한은 넉넉히 600.
  "headline-collect:600"
)

# ── 단계가 끝났는지 **무엇으로 판정하는가** ───────────────────────────────
# 종료코드만 보면 안 된다. 2026-10-25 에 market-snapshot 이 이렇게 끝났다:
#   claude 가 느려진 백그라운드 작업을 10분 만에 죽이고 **0 으로 종료**
#   → 261025-시장데이터.md 가 안 생겼는데 로그에는 `✅` 만 남았다
# 로그에 ✅ 가 찍히면 사람은 거기서 읽기를 멈춘다. **거짓 ✅ 가 침묵보다 나쁘다.**
# 그래서 단계마다 그 단계가 만들어야 하는 파일을 같이 확인한다.
step_artifact() {
  case "$1" in
    market-snapshot)  echo "$VAULT_DIR/personal/10-market/data/${CHAIN_DATE}-시장데이터.md" ;;
    daily-conclusion) echo "$VAULT_DIR/personal/10-market/_conclusions/${CHAIN_DATE}-오늘의결론.md" ;;
    agent-review)     echo "$VAULT_DIR/personal/10-market/data/${CHAIN_DATE}-에이전트의견.md" ;;
    # 나머지는 산출물이 "조용한 게 정상"이다 — 이벤트알림은 새 이벤트가 없으면
    # 아무것도 안 보내고, 헤드라인은 자기 JSONL 에 append 만 한다(건수는 감시견이 본다).
    *) echo "" ;;
  esac
}

for entry in "${STEPS[@]}"; do
  step="${entry%%:*}"; limit="${entry##*:}"
  start=$(date '+%H:%M:%S'); t0=$(date +%s)
  # 🔴 -k 가 반드시 있어야 한다. timeout 은 상한에서 TERM 을 보낸 뒤 **자식이
  # 실제로 죽을 때까지 기다린다.** claude 가 TERM 에 안 죽는 바람에 420초 상한이
  # 86분이 된 적이 있다 (2026-08-23 daily-conclusion: 19:24:36→20:51:14).
  # -k 60 이면 TERM 후 60초 안에 안 죽을 때 KILL 로 확실히 끊는다.
  timeout -k 60 "$limit" bash "$VAULT_DIR/.automation/${step}.sh" >/dev/null 2>&1
  rc=$?
  # 🔴 소요시간은 **직접 잰다.** timeout 에 맡길 수 없다 — 절전 중에 그 타이머가
  # 멈추기 때문에 상한이 아무 일도 하지 않는다 (맨 위 정정 주석).
  took=$(( $(date +%s) - t0 ))
  case $rc in
    0)   msg="✅" ;;
    124) msg="🔴 ${limit}초 초과로 중단" ;;
    *)   msg="🔴 종료코드 $rc" ;;
  esac
  if [ "$rc" -eq 0 ]; then
    # ⓐ 만들어야 할 파일이 없으면 성공이 아니다.
    art=$(step_artifact "$step")
    if [ -n "$art" ] && [ ! -s "$art" ]; then
      if [ "$step" = "daily-conclusion" ] \
         && [ ! -s "$VAULT_DIR/personal/10-market/data/${CHAIN_DATE}-시장데이터.md" ]; then
        # 결론은 시장데이터를 재료로 쓴다. 재료가 없어서 못 만든 건 이 단계의
        # 잘못이 아니다 — 앞 단계가 이미 🔴 로 찍혀 있다. 여기서 또 🔴 를 올리면
        # 고장 하나가 알림 두 줄이 되고, 사람이 원인을 뒤 단계로 착각한다.
        msg="⚪ 재료 없음 (시장데이터가 없다)"
      else
        msg="🔴 산출물 없음 ($(basename "$art"))"
      fi
    fi
    # ⓑ 상한의 2배를 넘기고도 살아 있었다 = timeout 이 멈춰 있었다 = 절전이다.
    #    ⓐ **뒤에** 붙인다. 산출물이 없는 건 증상이고 절전은 원인이라, 둘 다
    #    해당하면 원인이 줄 끝에 남아야 사람이 "왜" 를 먼저 집는다.
    if [ "$took" -gt $((limit * 2)) ]; then
      msg="${msg%✅} 🔴 절전 의심 (상한 ${limit}초의 2배 초과, 종료코드는 0)"
      msg="${msg# }"
    fi
  fi
  echo "=== $(date '+%Y-%m-%d %H:%M:%S') [저녁체인] ${step} ${msg} (${took}초, ${start} 시작) ===" >> "$LOG_FILE"
done

echo "=== $(date '+%Y-%m-%d %H:%M:%S') [저녁체인] 종료 ($(( ($(date +%s) - CHAIN_T0) / 60 ))분) ===" >> "$LOG_FILE"
echo >> "$LOG_FILE"
