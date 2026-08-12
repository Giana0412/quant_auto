#!/bin/bash
# 네트워크 대기 · 재시도 공용 헬퍼.
#
# 왜 필요한가 — 2026-08-08 ~ 08-11 나흘 동안 개인 자동화 3종이 전부 죽었는데,
# 로그에 남은 것은 이 한 줄뿐이었다:
#     API Error: Unable to connect to API (ENOTFOUND)
#
# 노트북이 20:00 예정 시각에 자고 있다가 늦게 깨면(실측: 20:00 예정 → 20:14/20:31 실행)
# launchd 는 바로 잡을 띄우는데 그 시점엔 Wi-Fi 가 아직 안 올라와 있다.
# 스크립트는 set -euo pipefail 이라 첫 실패에서 그대로 죽고, 재시도도 알림도 없었다.
#
# 맥미니로 옮기면 근본 원인(잠자기)은 사라지지만 그건 한참 뒤 일이고,
# 그때도 네트워크가 순간 끊기는 일은 있다. 그래서 이 계층은 계속 필요하다.
#
# 사용법:
#   source "$VAULT_DIR/.automation/lib/net.sh"
#   wait_for_network || exit 1
#   retry 3 60 "$CLAUDE_BIN" -p "$PROMPT" --allowedTools "..."

NET_PROBE_URL="${NET_PROBE_URL:-https://api.anthropic.com/v1/messages}"

# wait_for_network [최대대기초] [확인간격초]
#   API 에 닿을 때까지 기다린다. 닿으면 0, 시간 초과면 1.
#   HTTP 상태코드는 보지 않는다 — 405 여도 "연결은 됐다"는 뜻이므로 충분하다.
wait_for_network() {
    local max="${1:-600}" gap="${2:-15}" waited=0

    if curl -s --max-time 5 -o /dev/null "$NET_PROBE_URL" 2>/dev/null; then
        return 0
    fi

    echo "⏳ 네트워크 대기 중 (최대 ${max}초)"
    while [ "$waited" -lt "$max" ]; do
        sleep "$gap"
        waited=$((waited + gap))
        if curl -s --max-time 5 -o /dev/null "$NET_PROBE_URL" 2>/dev/null; then
            echo "✅ 네트워크 연결됨 (${waited}초 대기)"
            return 0
        fi
    done

    echo "🔴 네트워크가 ${max}초 동안 올라오지 않았다 — 이번 실행을 건너뛴다"
    return 1
}

# retry <시도횟수> <첫대기초> <명령...>
#   실패하면 대기 시간을 두 배로 늘려가며 다시 시도한다.
#   깨어난 직후의 일시적 실패를 흡수하는 것이 목적이라, 몇 번 만에 됐는지 로그에 남긴다.
retry() {
    local tries="$1" delay="$2"; shift 2
    local n=1

    while true; do
        if "$@"; then
            [ "$n" -gt 1 ] && echo "✅ ${n}회차에 성공"
            return 0
        fi
        if [ "$n" -ge "$tries" ]; then
            echo "🔴 ${tries}회 모두 실패: $1"
            return 1
        fi
        echo "⚠️ 실패 (${n}/${tries}) — ${delay}초 뒤 재시도"
        sleep "$delay"
        n=$((n + 1))
        delay=$((delay * 2))
    done
}
