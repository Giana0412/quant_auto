#!/usr/bin/env python3
"""팀 결정·미해결 질문 장부. append-only JSONL.

── 왜 필요한가 ───────────────────────────────────────────────────────────
2026-10-24 에 찾아보니 팀이 내린 결정이 **레포 어디에도 없었다.** 9/11 "바이오텍
제외", 9/30 섹터 목표, 킬 기준, Q-1~Q-5 미해결 질문이 전부 .docx 와 카톡·대화에만
있었다. 그래서 10/17 에 "바이오 도박성으로 돌리자"는 제안이 9/11 결정을 뒤집는
것이라는 걸 **사람의 기억으로만** 짚을 수 있었다. 대화 맥락이 날아가면 못 짚는다.

결정은 코드가 아니라 **데이터**다. 그래서 book-log·regime-log·watchlist 와 같은
자리에 같은 방식(append-only JSONL)으로 쌓는다. 고친 기록도 지우지 않고 덮어쓴다 —
`supersedes` 로 이어 붙여 **왜 바뀌었는지가 남게** 한다.

── 쓰는 법 ───────────────────────────────────────────────────────────────
  decision_log.py                      # 미해결 질문 + 살아있는 결정
  decision_log.py --brief              # 텔레그램용 한두 줄 (건강검진이 부른다)
  decision_log.py --all                # 닫힌 것까지 전부
  decision_log.py add --kind question --title "..." [--owner 이정민] [--due 2026-10-28]
  decision_log.py close Q-2 --answer "11/13 확정 (주최측 메일)"
  decision_log.py supersede D-003 --title "..." --detail "..."

🔴 이 스크립트는 **무슨 일이 있어도 0 으로 끝난다.** 건강검진의 한 단계로 불리는데
여기서 죽으면 건강검진이 같이 죽는다 — 이 레포가 두 번 겪은 실패 방식이다.
"""
import argparse
import json
import sys
from datetime import date
from pathlib import Path

ROOT = Path("/Users/gyuhyeongkim/orca/projects/quant_auto")
DATA = ROOT / "personal/10-market/_decisions/decisions.jsonl"

OPEN = {"open", "active"}


def read():
    if not DATA.exists():
        return []
    out = []
    for line in DATA.read_text().splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            out.append(json.loads(line))
        except Exception:
            continue          # 한 줄 깨져도 나머지는 읽는다
    return out


def append(rec):
    DATA.parent.mkdir(parents=True, exist_ok=True)
    with DATA.open("a") as f:
        f.write(json.dumps(rec, ensure_ascii=False) + "\n")


def next_id(rows, kind):
    pre = "Q" if kind == "question" else "D"
    ns = [int(r["id"].split("-")[1]) for r in rows
          if r.get("id", "").startswith(pre + "-") and r["id"].split("-")[1].isdigit()]
    return f"{pre}-{max(ns, default=0) + 1:03d}"


def latest(rows):
    """supersede 체인을 따라가 **살아있는 판**만 남긴다."""
    dead = {r["supersedes"] for r in rows if r.get("supersedes")}
    return [r for r in rows if r["id"] not in dead]


def overdue(r, today):
    d = r.get("due")
    if not d or r.get("status") not in OPEN:
        return 0
    try:
        return (today - date.fromisoformat(d)).days
    except Exception:
        return 0


def cmd_show(a):
    rows = read()
    if not rows:
        print("장부가 비어 있다 — `decision_log.py add` 로 쌓는다")
        return 0
    live = rows if a.all else latest(rows)
    today = date.today()
    qs = [r for r in live if r.get("kind") == "question"
          and (a.all or r.get("status") in OPEN)]
    ds = [r for r in live if r.get("kind") == "decision"
          and (a.all or r.get("status") in OPEN)]

    if qs:
        print(f"── 미해결 질문 {len(qs)}건 ──")
        for r in sorted(qs, key=lambda x: (-overdue(x, today), x["id"])):
            od = overdue(r, today)
            mark = f"  🔴 기한 {od}일 지남" if od > 0 else (
                f"  (기한 {r['due']})" if r.get("due") else "")
            own = r.get("owner") or "담당 미정"
            print(f"  {r['id']}  {r['title']}")
            print(f"        {own}{mark}")
            if r.get("status") == "answered":
                print(f"        ✅ {r.get('answer', '')}")
    if ds:
        print(f"\n── 살아있는 결정 {len(ds)}건 ──")
        for r in sorted(ds, key=lambda x: x.get("date", "")):
            sup = "  ← 이전 판을 대체" if r.get("supersedes") else ""
            print(f"  {r['id']}  [{r.get('date','?')}] {r['title']}{sup}")
            if r.get("detail"):
                print(f"        {r['detail']}")
    return 0


def cmd_brief(a):
    """텔레그램 한두 줄. **짧아야 한다** — 결론 파일이 4000바이트 제한에 걸린다."""
    rows = latest(read())
    today = date.today()
    qs = [r for r in rows if r.get("kind") == "question" and r.get("status") in OPEN]
    od = [r for r in qs if overdue(r, today) > 0]
    if not qs:
        return 0
    line = f"미해결 질문 {len(qs)}건"
    if od:
        worst = max(od, key=lambda r: overdue(r, today))
        line += f" · 🔴 {worst['id']} 기한 {overdue(worst, today)}일 지남"
    noowner = [r for r in qs if not r.get("owner")]
    if noowner:
        line += f" · 담당 미정 {len(noowner)}건"
    print(line)
    return 0


def cmd_add(a):
    rows = read()
    rec = dict(id=a.id or next_id(rows, a.kind),
               date=a.date or date.today().isoformat(),
               kind=a.kind, status="open" if a.kind == "question" else "active",
               title=a.title, detail=a.detail or "", owner=a.owner or "",
               source=a.source or "", due=a.due or "", supersedes=a.supersedes or "")
    append(rec)
    print(f"추가: {rec['id']}  {rec['title']}")
    return 0


def cmd_close(a):
    rows = read()
    cur = [r for r in rows if r.get("id") == a.id]
    if not cur:
        print(f"{a.id} 를 못 찾았다", file=sys.stderr)
        return 0
    r = dict(cur[-1])
    r.update(status="answered" if r.get("kind") == "question" else "closed",
             answer=a.answer or "", closed_date=date.today().isoformat(),
             supersedes=a.id)
    append(r)
    print(f"닫음: {a.id}  {r['title']}\n  → {a.answer}")
    return 0


def cmd_supersede(a):
    rows = read()
    cur = [r for r in rows if r.get("id") == a.id]
    if not cur:
        print(f"{a.id} 를 못 찾았다", file=sys.stderr)
        return 0
    old = cur[-1]
    rec = dict(id=next_id(rows, old.get("kind", "decision")),
               date=date.today().isoformat(), kind=old.get("kind", "decision"),
               status="active", title=a.title or old["title"],
               detail=a.detail or "", owner=a.owner or old.get("owner", ""),
               source=a.source or "", due="", supersedes=a.id)
    append(rec)
    print(f"대체: {a.id} → {rec['id']}  {rec['title']}")
    return 0


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--brief", action="store_true")
    p.add_argument("--all", action="store_true")
    sub = p.add_subparsers(dest="cmd")

    q = sub.add_parser("add")
    q.add_argument("--kind", default="question", choices=["question", "decision"])
    q.add_argument("--title", required=True)
    q.add_argument("--detail"); q.add_argument("--owner"); q.add_argument("--due")
    q.add_argument("--date"); q.add_argument("--source"); q.add_argument("--id")
    q.add_argument("--supersedes")

    c = sub.add_parser("close")
    c.add_argument("id"); c.add_argument("--answer")

    s = sub.add_parser("supersede")
    s.add_argument("id"); s.add_argument("--title"); s.add_argument("--detail")
    s.add_argument("--owner"); s.add_argument("--source")

    a = p.parse_args()
    try:
        if a.cmd == "add":
            return cmd_add(a)
        if a.cmd == "close":
            return cmd_close(a)
        if a.cmd == "supersede":
            return cmd_supersede(a)
        return cmd_brief(a) if a.brief else cmd_show(a)
    except Exception as e:
        print(f"# 장부 처리 실패: {e}", file=sys.stderr)
        return 0        # 🔴 부르는 쪽(건강검진)을 죽이지 않는다


if __name__ == "__main__":
    sys.exit(main())
