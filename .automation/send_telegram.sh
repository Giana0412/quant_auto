#!/bin/bash
# 텔레그램으로 메시지 발송. .automation/.telegram.env(gitignored)에 토큰/chat_id가
# 있어야 실제로 보낸다 — 없으면 조용히 건너뛴다 (에러 아님, 아직 설정 전이라는 뜻).
#
# 사용법: send_telegram.sh <메시지파일경로>
# 헤드리스 에이전트가 호출할 때 토큰 값 자체를 절대 보거나 다루지 않도록,
# 토큰은 이 스크립트 내부(source)에서만 쓰이고 에이전트에게는 노출되지 않는다.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ENV_FILE="$SCRIPT_DIR/.telegram.env"

if [ ! -f "$ENV_FILE" ]; then
  echo "텔레그램 미설정 — .telegram.env 없음. 발송 건너뜀." >&2
  exit 0
fi

MSG_FILE="${1:?사용법: send_telegram.sh <메시지파일경로>}"
if [ ! -f "$MSG_FILE" ]; then
  echo "메시지 파일 없음: $MSG_FILE" >&2
  exit 1
fi

# shellcheck disable=SC1090
source "$ENV_FILE"

if [ -z "${TELEGRAM_BOT_TOKEN:-}" ] || [ -z "${TELEGRAM_CHAT_ID:-}" ]; then
  echo "TELEGRAM_BOT_TOKEN 또는 TELEGRAM_CHAT_ID 미설정. 발송 건너뜀." >&2
  exit 0
fi

TEXT=$(cat "$MSG_FILE")
TEXT="${TEXT:0:4000}"  # 텔레그램 메시지 4096자 제한

send_message() {
  local parse_mode_arg=("$@")
  curl -s -w "\n%{http_code}" \
    "https://api.telegram.org/bot${TELEGRAM_BOT_TOKEN}/sendMessage" \
    --data-urlencode "chat_id=${TELEGRAM_CHAT_ID}" \
    --data-urlencode "text=${TEXT}" \
    "${parse_mode_arg[@]}"
}

RESPONSE=$(send_message --data-urlencode "parse_mode=Markdown")
HTTP_CODE=$(echo "$RESPONSE" | tail -1)
BODY=$(echo "$RESPONSE" | head -1)

if [ "$HTTP_CODE" = "200" ]; then
  echo "텔레그램 발송 성공"
  exit 0
fi

# Markdown 파싱 실패(예: 짝 안 맞는 _..._, *...*)는 흔한 실수라
# 서식 없이 평문으로 한 번 더 시도한다 — 메시지 자체를 못 보내는 것보다 낫다.
echo "Markdown 발송 실패 (HTTP $HTTP_CODE): $BODY — 평문으로 재시도" >&2
RESPONSE=$(send_message)
HTTP_CODE=$(echo "$RESPONSE" | tail -1)
BODY=$(echo "$RESPONSE" | head -1)

if [ "$HTTP_CODE" = "200" ]; then
  echo "텔레그램 발송 성공 (평문 폴백)"
else
  echo "텔레그램 발송 실패 (HTTP $HTTP_CODE): $BODY" >&2
  exit 1
fi
