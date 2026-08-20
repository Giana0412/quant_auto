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
if ! mkdir "$LOCK" 2>/dev/null; then
  # 6시간 넘게 남아 있으면 죽은 락으로 보고 회수한다 (한 번 끼면 영영 못 도는 것 방지)
  if [ -n "$(find "$LOCK" -maxdepth 0 -mmin +360 2>/dev/null)" ]; then
    rmdir "$LOCK" 2>/dev/null && mkdir "$LOCK" 2>/dev/null || true
  else
    echo "=== $(date '+%Y-%m-%d %H:%M:%S') [저녁체인] 이미 실행 중 — 건너뜀 ===" >> "$LOG_FILE"
    exit 0
  fi
fi
trap 'rmdir "$LOCK" 2>/dev/null || true' EXIT INT TERM

{
  echo "=== $(date '+%Y-%m-%d %H:%M:%S') [저녁체인] 시작 ==="
} >> "$LOG_FILE"

for step in archive-newsletters market-snapshot daily-conclusion health-check; do
  start=$(date '+%H:%M:%S')
  if bash "$VAULT_DIR/.automation/${step}.sh" >/dev/null 2>&1; then
    echo "=== $(date '+%Y-%m-%d %H:%M:%S') [저녁체인] ${step} ✅ (${start} 시작) ===" >> "$LOG_FILE"
  else
    echo "=== $(date '+%Y-%m-%d %H:%M:%S') [저녁체인] ${step} 🔴 종료코드 $? (${start} 시작) ===" >> "$LOG_FILE"
  fi
done

echo "=== $(date '+%Y-%m-%d %H:%M:%S') [저녁체인] 종료 ===" >> "$LOG_FILE"
echo >> "$LOG_FILE"
