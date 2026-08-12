#!/bin/bash
# Slack 자격증명 공용 처리 — process-slack-docs.sh, slack-collect.sh 가 함께 쓴다.
#
# 토큰을 headless 에이전트의 도구 호출(curl 명령 인자)에 절대 노출시키지 않기 위해
# curl 설정 파일에 Authorization 헤더를 미리 박아두고, 에이전트는 파일 경로만 참조한다.
# (Bash(curl:*) 허용 패턴에서는 $VAR 같은 셸 변수 확장이 정적분석 불가로 차단되므로
#  환경변수 전달 방식은 쓸 수 없다 — curl -K 설정파일이 유일한 우회로다.)
#
# 사용법:
#   source "$VAULT_DIR/.automation/lib/slack-auth.sh"
#   slack_auth_begin || exit 1
#   ... curl -K "$SLACK_AUTH_RC" ...
#   (스크립트가 어떻게 끝나든 trap 이 자격증명 파일을 지운다)

SLACK_ENV_FILE="${SLACK_ENV_FILE:-$VAULT_DIR/.automation/.slack.env}"
SLACK_AUTH_RC="${SLACK_AUTH_RC:-$VAULT_DIR/.automation/.slack-auth.curlrc}"

# 실패·중단·정상종료 어느 경우에도 자격증명 파일을 남기지 않는다.
# (2026-08-06~08-12 사이, 스크립트가 중간에 죽으면서 이 파일이 디스크에 계속 남아 있었다)
slack_auth_cleanup() {
  if [ -f "$SLACK_AUTH_RC" ]; then
    shred -u "$SLACK_AUTH_RC" 2>/dev/null || rm -f "$SLACK_AUTH_RC"
  fi
  return 0
}

slack_auth_begin() {
  if [ ! -f "$SLACK_ENV_FILE" ]; then
    echo "🔴 Slack 토큰 파일이 없다: $SLACK_ENV_FILE" >&2
    echo "   SLACK_BOT_TOKEN=xoxb-... 형식으로 만들고 chmod 600 할 것" >&2
    return 1
  fi

  local tok
  tok=$(grep -E '^SLACK_BOT_TOKEN=' "$SLACK_ENV_FILE" | head -1 | cut -d= -f2-)
  if [ -z "$tok" ]; then
    echo "🔴 $SLACK_ENV_FILE 에 SLACK_BOT_TOKEN 항목이 없다" >&2
    return 1
  fi

  trap slack_auth_cleanup EXIT INT TERM
  printf 'header = "Authorization: Bearer %s"\n' "$tok" > "$SLACK_AUTH_RC"
  chmod 600 "$SLACK_AUTH_RC"
  unset tok
}
