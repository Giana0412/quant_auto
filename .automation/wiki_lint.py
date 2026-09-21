#!/usr/bin/env python3
"""위키 건강검진 — 지식베이스가 조용히 썩는 걸 막는다.

Karpathy 의 LLM Wiki 패턴에서 ingest/query 와 나란히 놓인 세 번째 작업이다.
위키는 방치하면 **틀린 채로 자신 있게 남아** 원본보다 위험해진다. 린트가 잡는 것:

  1. **출처 없는 수치** — 숫자를 주장하면서 [출처] 나 날짜가 없는 줄
  2. **묵은 미확인** — ⚠️미확인 이 오래 방치되면 그 자체가 리스크다
  3. **끊긴 내부 링크** — 페이지를 옮기고 링크를 안 고친 것
  4. **고아 페이지** — index 에서 도달 못 하는 페이지
  5. **지난 날짜** — 이미 지난 일정이 ⚠️미확인 으로 남아 있는 것

린트는 **막지 않고 알린다.** 위키는 사람이 판단할 재료지 통과해야 할 관문이 아니다.

실행:
  python3 .automation/wiki_lint.py
  python3 .automation/wiki_lint.py --stale-days 5
"""
import re
import sys
from datetime import date, datetime
from pathlib import Path

WIKI = Path("wiki")
INDEX = WIKI / "index.md"
STALE_DAYS = 10          # ⚠️미확인 이 이보다 오래되면 경고

# 숫자 주장인데 출처가 없으면 잡는다. 표 구분선·링크·코드는 제외한다.
NUM = re.compile(r"[-+]?\d[\d,]*\.?\d*\s*(%|%p|bp|원|달러|배|건|종목|회)")
HAS_SRC = re.compile(r"\[[^\]]*\d{4}-\d{2}-\d{2}[^\]]*\]|\[[^\]]+\]\([^)]+\)|출처|§|→")
DATE = re.compile(r"(20\d{2}-\d{2}-\d{2})")


def pages():
    return sorted(p for p in WIKI.rglob("*.md"))


def rel(p):
    return str(p.relative_to(WIKI))


def check_sources(p, lines, out):
    """숫자를 주장하면서 출처·날짜·참조가 하나도 없는 줄.

    🔴 **출처는 절 단위로 상속된다.** 처음엔 줄 단위로만 봤더니 `## F-1 … [2026-09-21]`
    처럼 제목에 날짜를 달아 둔 절의 본문이 전부 걸려 24건이 쏟아졌다. 양치기 소년이
    되면 아무도 린트를 안 본다 — 가장 가까운 상위 제목에 출처가 있으면 그 절 전체가
    출처를 가진 것으로 본다."""
    in_code = False
    sec_has_src = False
    for i, ln in enumerate(lines, 1):
        st = ln.strip()
        if st.startswith("```"):
            in_code = not in_code
            continue
        if in_code:
            continue
        if st.startswith("#"):
            # 새 절 시작 — 제목 자체에 출처·날짜가 있으면 이 절은 통과
            sec_has_src = bool(HAS_SRC.search(ln) or DATE.search(ln))
            continue
        if sec_has_src or st.startswith(("|", "|---", ">")):
            continue
        if not NUM.search(ln) or HAS_SRC.search(ln) or DATE.search(ln):
            continue
        out.append((p, i, "출처없는 수치", st[:70]))


def check_stale(p, lines, out, stale_days):
    """⚠️미확인 이 오래 묵었나. 같은 줄이나 근처 줄의 날짜를 본다."""
    today = date.today()
    for i, ln in enumerate(lines, 1):
        if "⚠️미확인" not in ln and "미확인" not in ln:
            continue
        ctx = " ".join(lines[max(0, i - 4):i + 2])
        ds = DATE.findall(ctx)
        if not ds:
            continue
        newest = max(datetime.strptime(d, "%Y-%m-%d").date() for d in ds)
        age = (today - newest).days
        if age > stale_days:
            out.append((p, i, f"묵은 미확인 {age}일", ln.strip()[:70]))


def check_past_due(p, lines, out):
    """이미 지난 날짜가 아직 미확인/예정으로 남아 있나."""
    today = date.today()
    for i, ln in enumerate(lines, 1):
        if not re.search(r"미확인|추정|예정|확인할", ln):
            continue
        for d in DATE.findall(ln):
            when = datetime.strptime(d, "%Y-%m-%d").date()
            if when < today:
                out.append((p, i, f"지난 날짜({d})가 아직 미확정", ln.strip()[:60]))
                break


def check_links(p, lines, out, known):
    for i, ln in enumerate(lines, 1):
        for m in re.finditer(r"\]\(([^)#]+\.md)(#[^)]*)?\)", ln):
            target = (p.parent / m.group(1)).resolve()
            if target not in known:
                out.append((p, i, "끊긴 링크", m.group(1)))


def main():
    stale_days = STALE_DAYS
    if "--stale-days" in sys.argv:
        try:
            stale_days = int(sys.argv[sys.argv.index("--stale-days") + 1])
        except Exception:
            pass
    if not WIKI.exists():
        print(f"🔴 {WIKI}/ 가 없다", file=sys.stderr)
        return 1

    ps = pages()
    known = {p.resolve() for p in ps}
    out = []
    linked = set()

    for p in ps:
        lines = p.read_text().splitlines()
        check_sources(p, lines, out)
        check_stale(p, lines, out, stale_days)
        check_past_due(p, lines, out)
        check_links(p, lines, out, known)

    # 고아 페이지 — index 에서 한 다리 건너 도달 가능한지만 본다(깊은 그래프는 과함)
    for p in ps:
        for m in re.finditer(r"\]\(([^)#]+\.md)", p.read_text()):
            linked.add((p.parent / m.group(1)).resolve())
    orphans = [p for p in ps
               if p.resolve() not in linked and p.resolve() != INDEX.resolve()]

    print(f"[위키 린트] 페이지 {len(ps)}개 · 기준 미확인 {stale_days}일\n")
    if orphans:
        print("── 고아 페이지 (어디서도 링크되지 않음) ──")
        for p in orphans:
            print(f"  · {rel(p)}")
        print()

    if out:
        by = {}
        for p, i, kind, txt in out:
            by.setdefault(kind.split()[0], []).append((p, i, kind, txt))
        for kind in sorted(by):
            items = by[kind]
            print(f"── {kind} ({len(items)}건) ──")
            for p, i, k, txt in items[:8]:
                print(f"  {rel(p)}:{i}  {k}")
                print(f"     {txt}")
            if len(items) > 8:
                print(f"  … 외 {len(items) - 8}건")
            print()

    total = len(out) + len(orphans)
    if total == 0:
        print("✅ 문제 없음")
    else:
        print(f"총 {total}건. **막지 않고 알리기만 한다** — 판단은 사람이 한다.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
