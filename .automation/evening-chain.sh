#!/bin/bash
# 저녁 체인 — 뉴스레터 → 시장 → 결론 → 점검을 **순서대로 하나씩** 돌린다.
# launchd 가 매일 20:00 KST 에 이것 하나만 부른다 (com.giana.evening-chain.plist).
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

VAULT_DIR="/Users/gyuhyeongkim/orca/projects/obsidian_test"
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

{
  echo "=== $(date '+%Y-%m-%d %H:%M:%S') [저녁체인] 시작 ==="
} >> "$LOG_FILE"

# 단계마다 상한 시간을 둔다. **무엇도 영원히 매달려선 안 된다.**
# newsletter_fetch 가 IMAP 에서 23시간 멈춰 락을 붙잡은 사고가 이 규칙이 없어서
# 났다. 상한을 넘기면 죽이고 다음 단계로 간다 — 멈추는 것보다 실패가 낫다.
# (timeout 124 = 시간 초과. 체인 전체 상한은 이 합인 30분.)
declare -a STEPS=(
  "archive-newsletters:900"   # 메일 수집 + 다이제스트 — 제일 오래 걸린다
  "market-snapshot:420"
  "daily-conclusion:420"
  "health-check:120"
)

for entry in "${STEPS[@]}"; do
  step="${entry%%:*}"; limit="${entry##*:}"
  start=$(date '+%H:%M:%S')
  # 🔴 -k 가 반드시 있어야 한다. timeout 은 상한에서 TERM 을 보낸 뒤 **자식이
  # 실제로 죽을 때까지 기다린다.** claude 가 TERM 에 안 죽는 바람에 420초 상한이
  # 86분이 된 적이 있다 (2026-08-23 daily-conclusion: 19:24:36→20:51:14).
  # -k 60 이면 TERM 후 60초 안에 안 죽을 때 KILL 로 확실히 끊는다.
  timeout -k 60 "$limit" bash "$VAULT_DIR/.automation/${step}.sh" >/dev/null 2>&1
  rc=$?
  case $rc in
    0)   msg="✅" ;;
    124) msg="🔴 ${limit}초 초과로 중단" ;;
    *)   msg="🔴 종료코드 $rc" ;;
  esac
  echo "=== $(date '+%Y-%m-%d %H:%M:%S') [저녁체인] ${step} ${msg} (${start} 시작) ===" >> "$LOG_FILE"
done

echo "=== $(date '+%Y-%m-%d %H:%M:%S') [저녁체인] 종료 ===" >> "$LOG_FILE"
echo >> "$LOG_FILE"
