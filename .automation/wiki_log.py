#!/usr/bin/env python3
"""vault/log/log.md 에 작업 기록을 한 줄 덧붙인다. 절대 지우거나 고치지 않는다.

카파시 LLM Wiki 원문 (vault/raw/references/karpathy-llm-wiki.md):

    log.md is chronological. It's an **append-only** record of what happened and
    when — ingests, queries, lint passes. A useful tip: if each entry starts with
    a consistent prefix (e.g. `## [2026-04-02] ingest | Article Title`), the log
    becomes parseable with simple unix tools —
    `grep "^## \\[" log.md | tail -5` gives you the last 5 entries.

이 형식을 그대로 따른다. 그래서 아래가 동작한다:

    grep '^## \\[' vault/log/log.md | tail -5          # 최근 5건
    grep '^## \\[.*| query' vault/log/log.md | wc -l   # 조회 횟수 (= 조회율 지표)

**조회율은 지금까지 측정 수단이 없던 핵심 지표다**(설계문서 §10). query 를
여기 남기기 시작하면 그때부터 잰다. 그리고 답을 못 찾은 질문은 그 자체로
"다음에 채울 곳" 목록이 된다.

사용법:
  python3 .automation/wiki_log.py ingest "260810-주간회의" --detail "3종 생성"
  python3 .automation/wiki_log.py lint   --detail "위반 0건"
  python3 .automation/wiki_log.py query  "왜 노션 안 쓰기로 했나" --detail "출처 3건" --found
  python3 .automation/wiki_log.py query  "채널A 계약 조건" --no-found
"""

import argparse
import os
import re
from datetime import date

VAULT_DIR = os.environ.get(
    "VAULT_DIR", "/Users/gyuhyeongkim/orca/projects/obsidian_test"
)
LOG = os.path.join(VAULT_DIR, "vault/log/log.md")

HEADER = """---
created: 2026-08-12
updated: {today}
purpose: vault 작업 기록 — ingest·query·lint 를 시간순으로 덧붙인다 (append-only)
---

# 작업 로그

> **덧붙이기만 한다.** 지난 항목을 고치거나 지우지 않는다.
> `.automation/wiki_log.py` 가 기록하며, 형식은 카파시 LLM Wiki 원문을 따른다.
>
> ```bash
> grep '^## \\[' vault/log/log.md | tail -5           # 최근 5건
> grep -c '^## \\[.*\\] query ' vault/log/log.md      # 조회 횟수
> ```

"""


def ensure_file():
    if os.path.exists(LOG):
        return
    os.makedirs(os.path.dirname(LOG), exist_ok=True)
    with open(LOG, "w", encoding="utf-8") as f:
        f.write(HEADER.format(today=date.today().isoformat()))


def touch_updated(text):
    """frontmatter 의 updated 만 오늘로. 본문은 건드리지 않는다."""
    return re.sub(r"^updated:.*$", f"updated: {date.today().isoformat()}",
                  text, count=1, flags=re.M)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("op", choices=["ingest", "query", "lint", "promote", "handoff"])
    ap.add_argument("subject", nargs="?", default="", help="대상 문서명 또는 질문")
    ap.add_argument("--detail", default="", help="한 줄 부연")
    ap.add_argument("--found", dest="found", action="store_true",
                    help="query 전용 — vault 에서 답을 찾았음")
    ap.add_argument("--no-found", dest="found", action="store_false",
                    help="query 전용 — 답이 vault 에 없었음")
    ap.set_defaults(found=None)
    a = ap.parse_args()

    ensure_file()
    text = open(LOG, encoding="utf-8").read()

    subject = " ".join(a.subject.split())[:100] or "-"
    line = f"## [{date.today().isoformat()}] {a.op} | {subject}"

    body = []
    if a.op == "query" and a.found is not None:
        # 못 찾은 질문이 곧 다음에 채울 곳이다 — 눈에 띄게 남긴다
        body.append("- 결과: " + ("답변함" if a.found else "**vault 에 없음 — 채워야 할 곳**"))
    if a.detail:
        body.append(f"- {a.detail}")

    entry = line + "\n" + ("\n".join(body) + "\n" if body else "")
    with open(LOG, "w", encoding="utf-8") as f:
        f.write(touch_updated(text).rstrip("\n") + "\n\n" + entry)

    print(f"  기록: {line}")


if __name__ == "__main__":
    main()
