#!/bin/bash
# Slack 원본 수집 — slack-sync 옵시디언 플러그인의 대체품.
#
# 플러그인은 Obsidian 앱이 켜져 있어야만 동작해서, 앱을 닫은 2026-08-06 이후
# 수집이 조용히 멈췄다(로그에는 "처리할 새 원본 없음"만 찍혀 정상처럼 보였다).
# 이 스크립트는 launchd가 직접 돌리므로 앱과 무관하다.
#
# process-slack-docs.sh 가 문서화 전에 먼저 호출한다. 단독 실행도 가능하다:
#   bash .automation/slack-collect.sh --dry-run

set -euo pipefail

VAULT_DIR="/Users/gyuhyeongkim/orca/projects/obsidian_test"
export VAULT_DIR

cd "$VAULT_DIR"
exec python3 "$VAULT_DIR/.automation/slack_collect.py" "$@"
