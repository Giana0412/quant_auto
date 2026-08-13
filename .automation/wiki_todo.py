#!/usr/bin/env python3
"""회의 결정사항의 액션 아이템을 담당자별로 모아 vault/index/할일.md 를 만든다.

260811 싱크에서 이준범이 목요일까지의 목표로 꼽은 것 중 하나:

    주간에 우리가 미팅을 하면은 무슨 일을 할지가 결론이 나잖아요. 대부분의
    "내가 뭘 해야겠다"는 것도 미팅으로서 많이 정립이 되고, **그게 이제 본인의
    데일리에 반영되는 어떤 스킬** — 얘네들은 기본이고 (1:05:28)

즉 **회의 결론이 각자의 할 일로 이어지는 경로**다. 지금까지는 결정사항 문서를
사람이 직접 열어봐야 자기 몫을 알 수 있었다.

정본은 회의 결정사항 문서이고 이 파일은 그것을 담당자별로 다시 자른 목차다.
그래서 매번 통째로 덮어쓴다 — 여기서 항목을 지워도 다음 실행에 되살아난다.
(할 일을 지우려면 결정사항 문서를 고치거나, 완료로 표시해야 한다)

기한·상태는 .automation/action-items.json 에서 가져온다 — STAGE2 가 Slack 으로
기한을 물어 채우는 파일이다.
"""

import json
import os
import re
from collections import defaultdict
from datetime import date, datetime

VAULT_DIR = os.environ.get(
    "VAULT_DIR", "/Users/gyuhyeongkim/orca/projects/obsidian_test"
)
DECISIONS = os.path.join(VAULT_DIR, "vault/wiki/05-meetings/결정사항")
STATE = os.path.join(VAULT_DIR, ".automation/action-items.json")
OUT = os.path.join(VAULT_DIR, "vault/index/할일.md")

# 결정사항 문서에 실제로 쓰이는 두 형식을 모두 받는다:
#   **김규형**              / **김규형 — 이번 주 (7/29~7/31)**   → 블록 헤더
#   - [김규형] 항목          / - [미정] 항목                      → 인라인 표기
OWNER_BLOCK = re.compile(r"^\*\*(.+?)\*\*\s*$")
OWNER_INLINE = re.compile(r"^[-*]\s*\[([^\]]+)\]\s*(.+)$")
ITEM = re.compile(r"^[-*]\s+(.+)$")
ACTION_H = re.compile(r"^##+\s*.*(액션|할 일|Action)", re.I)
ANY_H = re.compile(r"^##+\s")
NAME = re.compile(r"^(\d{6})-(.+)-결정사항$")


def clean_owner(s):
    """'김규형 — 이번 주 (7/29~7/31)' → '김규형'"""
    s = re.split(r"[—\-–(]", s, maxsplit=1)[0]
    return re.sub(r"\*\*|`", "", s).strip() or "미정"


def load_status():
    """action-items.json 의 상태를 task 텍스트 앞부분으로 찾을 수 있게 만든다."""
    if not os.path.exists(STATE):
        return {}
    try:
        items = json.load(open(STATE, encoding="utf-8"))
    except Exception:
        return {}
    out = {}
    for it in items:
        key = re.sub(r"\s+", "", (it.get("task") or ""))[:24]
        if key:
            out[key] = it
    return out


def parse(path):
    """한 결정사항 문서에서 (담당자, 항목) 목록을 뽑는다."""
    lines = open(path, encoding="utf-8").read().split("\n")
    out, owner, inside = [], None, False

    for line in lines:
        if ACTION_H.match(line):
            inside, owner = True, None
            continue
        if inside and ANY_H.match(line):      # 다음 절이 시작되면 끝
            break
        if not inside:
            continue

        m = OWNER_BLOCK.match(line.strip())
        if m:
            owner = clean_owner(m.group(1))
            continue

        m = OWNER_INLINE.match(line.strip())
        if m:
            out.append((clean_owner(m.group(1)), m.group(2).strip()))
            continue

        # 들여쓴 줄은 윗 항목의 부연이므로 별도 할 일로 세지 않는다
        if line.startswith(("  ", "\t")):
            continue

        m = ITEM.match(line.strip())
        if m and m.group(1).strip():
            out.append((owner or "미정", m.group(1).strip()))

    return out


def main():
    status = load_status()
    by_owner = defaultdict(list)

    for fn in sorted(os.listdir(DECISIONS), reverse=True):
        if not fn.endswith(".md"):
            continue
        m = NAME.match(fn[:-3])
        if not m:
            continue
        yymmdd, topic = m.groups()
        try:
            d = datetime.strptime(yymmdd, "%y%m%d").strftime("%Y-%m-%d")
        except ValueError:
            d = yymmdd
        for owner, task in parse(os.path.join(DECISIONS, fn)):
            st = status.get(re.sub(r"\s+", "", task)[:24])
            by_owner[owner].append({
                "date": d, "topic": topic, "doc": fn[:-3], "task": task,
                "due": (st or {}).get("due_date"),
                "state": (st or {}).get("status"),
            })

    today = date.today().isoformat()
    L = [
        "---", "created: 2026-08-13", f"updated: {today}",
        "purpose: 회의 결정사항의 액션 아이템을 담당자별로 모은 목차 — 자동 생성",
        "---", "",
        "# 할 일 (담당자별)", "",
        "> `.automation/wiki_todo.py` 가 자동 생성한다. **손으로 고치지 말 것** — 다음 실행에서 덮어써진다.",
        "> **정본은 회의 결정사항 문서다.** 여기서 항목을 지워도 되살아난다 —",
        "> 없애려면 결정사항 문서를 고쳐야 한다.", "",
    ]

    total = sum(len(v) for v in by_owner.values())
    L.append(f"회의 결정사항에서 뽑은 **{total}건** / 담당자 **{len(by_owner)}명**. 최근 회의 순.\n")

    # 사람 먼저, '미정'은 맨 뒤
    for owner in sorted(by_owner, key=lambda o: (o == "미정", o)):
        items = by_owner[owner]
        L.append(f"## {owner} ({len(items)}건)\n")
        for it in items:
            bits = [f"- {it['task']}"]
            meta = [f"{it['date']} {it['topic']}"]
            if it["due"]:
                meta.append(f"기한 {it['due']}")
            if it["state"]:
                meta.append({"awaiting_due_date": "기한 미정",
                             "scheduled": "캘린더 등록됨",
                             "reminded": "알림 발송됨"}.get(it["state"], it["state"]))
            bits.append(f"  ↳ {' · '.join(meta)} — [[{it['doc']}]]")
            L += bits
        L.append("")

    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with open(OUT, "w", encoding="utf-8") as f:
        f.write("\n".join(L).rstrip("\n") + "\n")
    print(f"  생성: vault/index/할일.md — {total}건 / {len(by_owner)}명")


if __name__ == "__main__":
    main()
