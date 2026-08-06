#!/bin/bash
# Slack Sync가 vault/05-slack에 모아둔 원본을 읽어서
# vault/06-docs/{01-전사본,02-정리본,03-결정사항}에 3종 문서로 정리하는 headless Claude 실행 스크립트.
# launchd가 1시간마다 호출한다 (com.giana.obsidian-slack-docs-sync.plist).

set -euo pipefail

VAULT_DIR="/Users/gyuhyeongkim/orca/projects/obsidian_test"
CLAUDE_BIN="/Users/gyuhyeongkim/.local/bin/claude"
LOG_DIR="$VAULT_DIR/.automation/logs"
LOG_FILE="$LOG_DIR/$(date +%Y%m%d).log"

mkdir -p "$LOG_DIR"
cd "$VAULT_DIR"

PROMPT='vault/06-docs/_템플릿-가이드.md 파일을 먼저 읽고 그 형식을 그대로 따른다.

작업:
1. vault/05-slack/*.md 를 전부 확인한다.
2. 각 파일에 실질적인 내용(파일 첨부 📎 코드블록, 또는 의미 있는 회의/문서 텍스트)이 있는지 확인한다. "채널에 참여함" 같은 시스템 메시지나 멘션만 있는 빈 메시지는 건너뛴다.
3. 내용이 있는 파일에 대해, 그 안의 실제 날짜(문서/회의 내용에서 추론, 없으면 slack_url이나 created 필드 사용)와 주제로 파일명을 만들어서 vault/06-docs/01-전사본/, 02-정리본/, 03-결정사항/ 에 이미 같은 이름(YYMMDD-주제-*.md)의 결과물이 있는지 Glob으로 확인한다.
4. 이미 3종 다 있으면 건너뛴다 (중복 생성 금지). 하나라도 없으면 템플릿 가이드 형식대로 전사본/정리본/결정사항 3종을 새로 작성한다.
   - 전사본: 원문 보존, 요약 금지, 오탈자 교정 최소화
   - 정리본: 한줄요약/핵심논의(소주제별)/맥락배경/미결정사항/액션아이템(표) 구조
   - 결정사항: 결정사항/미결정보류/액션아이템 구조 (짧고 명확하게, 공식 결정이 없으면 "없음"으로 명시)
5. 처리한 원본과 새로 만든 문서 목록을 마지막에 요약해서 출력한다. 처리할 새 원본이 없으면 "처리할 새 원본 없음"이라고만 출력하고 끝낸다.

git commit/push는 하지 않는다 (obsidian-git이 별도로 자동 커밋한다). vault/05-slack, vault/06-docs 외의 파일은 건드리지 않는다.'

{
  echo "=== $(date '+%Y-%m-%d %H:%M:%S') 실행 시작 ==="
  "$CLAUDE_BIN" -p "$PROMPT" --allowedTools "Read Write Edit Glob Grep" 2>&1
  echo "=== $(date '+%Y-%m-%d %H:%M:%S') 실행 종료 ==="
  echo
} >> "$LOG_FILE"
