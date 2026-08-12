#!/bin/bash
# vault schema 규칙 검사 — 주 1회 실행. 보고만 하고 고치지 않는다.
#
# 결과를 vault/log/lint-report.md 에 남긴다. 로그 파일이 아니라 vault 안에
# 두는 이유: 로그는 아무도 안 본다. 2026-08-06~12 사이 STAGE2 가 6일간 죽어 있었는데
# 아무도 몰랐던 것이 stderr 로그만 쌓였기 때문이다. Obsidian 에서 바로 보이게 둔다.

set -euo pipefail

VAULT_DIR="/Users/gyuhyeongkim/orca/projects/obsidian_test"
export VAULT_DIR
REPORT="$VAULT_DIR/vault/log/lint-report.md"
TODAY=$(TZ=Asia/Seoul date +%Y-%m-%d)

cd "$VAULT_DIR"

OUT=$(python3 "$VAULT_DIR/.automation/wiki_lint.py" 2>&1) || true
COUNT=$(printf '%s' "$OUT" | sed -n 's/^합계 \([0-9]*\)건.*/\1/p')

{
  echo "---"
  echo "created: 2026-08-12"
  echo "updated: $TODAY"
  echo "purpose: vault schema 규칙 위반 자동 점검 결과 (주 1회 갱신)"
  echo "---"
  echo
  echo "# Lint 리포트"
  echo
  echo "- 마지막 검사: **$TODAY**"
  echo "- 위반: **${COUNT:-?}건**"
  echo
  echo "> 이 파일은 \`.automation/wiki-lint.sh\` 가 자동으로 덮어쓴다. 손으로 고치지 말 것."
  echo "> 규칙 정의는 \`.automation/wiki_lint.py\`, 배경은 [[전체-구조도|전체 구조도]] §4~§6."
  echo
  echo '```'
  printf '%s\n' "$OUT"
  echo '```'
  echo
  echo "## 규칙"
  echo
  echo "| | 규칙 | 왜 |"
  echo "|---|---|---|"
  echo "| L1 | 깨진 위키링크가 없을 것 | 링크가 끊기면 맥락 추적이 끊긴다 |"
  echo "| L2 | 번호 표기(\`#9는\`)가 태그로 오인식되지 않을 것 | 태그 창이 쓰레기 태그로 찬다 |"
  echo "| L3 | 모든 문서에 \`created\` 가 있을 것 | 언제 것인지 모르면 최신 여부를 못 판단한다 |"
  echo "| L4 | 아무도 링크하지 않는 문서가 없을 것 | 검색으로만 닿는 문서는 사실상 묻힌다 |"
  echo "| L5 | 고쳐진 문서에는 \`updated\` 가 있을 것 | git 이력과 대조해 판정한다 |"
  echo "| L7 | \`review_by\` 가 지난 문서 보고 | 오래된 문서 정리 장치 |"
} > "$REPORT"

printf '%s\n' "$OUT"
echo "→ 리포트: vault/log/lint-report.md"
