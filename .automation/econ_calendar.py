#!/usr/bin/env python3
"""경제지표 일정 수집 — 관제 사이트에서 직접 긁는다.

── 왜 직접 긁나 ──────────────────────────────────────────────────────────
지표 날짜를 손으로 적으면 반드시 틀린다. 실제로 1차 회의록의 "9월 16일 금리 관련
발표"가 무엇인지 몰라 2주간 ⚠️미확인으로 떠 있었고, Fed 캘린더를 직접 파싱하고서야
9/15–16 FOMC 였음이 확인됐다. **지어낸 날짜는 그대로 매매 판단에 들어간다.**

── 소스별 실측 (2026-09-22 직접 확인) ───────────────────────────────────
| 기관 | 상태 | 비고 |
|---|---|---|
| **Fed** (FOMC) | ✅ 파싱됨 | robots 제약 없음. 2026년 8회 회의 전부 |
| **BEA** (GDP·PCE·무역) | ✅ 파싱됨 | 표 구조가 깔끔. 10/29 GDP 확인 |
| **Census** (소매·내구재·주택) | ❌ **JS 렌더링** | calendar.html 에 표가 0개. 실측 확인 |
| **BLS** (고용·CPI·PPI) | ❌ **403** | 크롤러를 막는다. 수동 입력 fallback |

BLS 가 막혀 있는 게 뼈아프다 — 고용·CPI 가 시장을 가장 크게 흔드는데 자동화가 안 된다.
그 둘은 `macro-calendar.json` 에 손으로 넣고 `source` 에 그렇게 적어 두었다.

수집 결과는 **덮어쓰지 않고 병합**한다. 손으로 넣은 이벤트(대회 일정·9/23 행사 등)와
수집분이 섞여 있어서, 수집분만 `auto_source` 로 표시해 구분한다.

실행:
  .automation/.venv/bin/python .automation/econ_calendar.py            # 미리보기
  .automation/.venv/bin/python .automation/econ_calendar.py --merge    # 캘린더에 병합
"""
import json
import re
import sys
import urllib.request
from datetime import date, datetime
from pathlib import Path

CAL = Path(".automation/macro-calendar.json")
UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/140.0 Safari/537.36 "
      "(LC-Ghosts-research-bot; respects robots.txt)")
TIMEOUT = 25
YEAR = 2026
MONTHS = ("January February March April May June July August September "
          "October November December").split()
MON_RE = "|".join(MONTHS)

# 관심 지표만 남긴다 — BEA·Census 는 지역별 통계까지 다 내보내서 그대로 넣으면 소음이다.
KEEP = re.compile(
    r"GDP|Personal Income|Trade in Goods|Retail|Durable|Housing Start|"
    r"New Residential|Construction|Business Inventor|Wholesale|Advance Economic",
    re.I)
# 감시 리드타임 — 이벤트 성격별. §macro-calendar.json _주석
LEAD = [
    (re.compile(r"GDP", re.I), 5),
    (re.compile(r"Personal Income|PCE", re.I), 5),
    (re.compile(r"Retail", re.I), 4),
    (re.compile(r"Trade in Goods", re.I), 3),
    (re.compile(r"Durable|Housing|Construction", re.I), 3),
]
DEFAULT_LEAD = 3


def fetch(url):
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
        return r.read().decode("utf-8", errors="replace")


def strip_tags(s):
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", s)).strip()


def table_rows(html):
    for r in re.findall(r"<tr[^>]*>(.*?)</tr>", html, re.S):
        cells = [strip_tags(c) for c in re.findall(r"<t[dh][^>]*>(.*?)</t[dh]>", r, re.S)]
        cells = [c for c in cells if c]
        if cells:
            yield cells


def parse_md(text):
    """'October 29' / 'Oct 29' → date. 연도는 YEAR 고정(캘린더가 당해만 싣는다)."""
    m = re.search(rf"\b({MON_RE}|{'|'.join(x[:3] for x in MONTHS)})\w*\s+(\d{{1,2}})\b", text)
    if not m:
        return None
    mon = next((i + 1 for i, x in enumerate(MONTHS)
                if x.lower().startswith(m.group(1)[:3].lower())), None)
    if not mon:
        return None
    try:
        return date(YEAR, mon, int(m.group(2)))
    except ValueError:
        return None


def lead_for(name):
    for pat, d in LEAD:
        if pat.search(name):
            return d
    return DEFAULT_LEAD


def collect_bea():
    out = []
    try:
        html = fetch("https://www.bea.gov/news/schedule")
    except Exception as e:
        return out, f"BEA 실패: {str(e)[:50]}"
    for cells in table_rows(html):
        joined = " | ".join(cells)
        d = parse_md(joined)
        if not d:
            continue
        name = next((c for c in cells[::-1] if len(c) > 10 and parse_md(c) != d), cells[-1])
        if not KEEP.search(name):
            continue
        out.append(dict(date=d.isoformat(), name=f"[BEA] {name[:60]}", kind="지표",
                        confirmed=True, watch_days=lead_for(name),
                        auto_source="bea.gov/news/schedule", watch=name[:110]))
    return out, None


def collect_census():
    out = []
    try:
        html = fetch("https://www.census.gov/economic-indicators/calendar.html")
    except Exception as e:
        return out, f"Census 실패: {str(e)[:50]}"
    for cells in table_rows(html):
        joined = " | ".join(cells)
        d = parse_md(joined)
        if not d:
            continue
        name = next((c for c in cells if KEEP.search(c)), None)
        if not name:
            continue
        out.append(dict(date=d.isoformat(), name=f"[Census] {name[:60]}", kind="지표",
                        confirmed=True, watch_days=lead_for(name),
                        auto_source="census.gov/economic-indicators/calendar.html",
                        watch=name[:110]))
    return out, None


def main():
    merge = "--merge" in sys.argv
    got, notes = [], []
    for fn in (collect_bea, collect_census):
        rows, err = fn()
        got += rows
        if err:
            notes.append(err)
        elif not rows:
            # 🔴 0건을 조용히 넘기지 않는다 — "새 게 없음"과 "파서가 깨짐"은 다르다.
            # Census 는 실제로 JS 렌더링이라 상시 0건이다(2026-09-22 확인).
            notes.append(f"{fn.__name__} 0건 — 페이지 구조를 확인할 것")

    # 같은 날 같은 이름은 한 번만
    uniq = {}
    for e in got:
        uniq[(e["date"], e["name"])] = e
    got = sorted(uniq.values(), key=lambda e: e["date"])

    today = date.today()
    future = [e for e in got if date.fromisoformat(e["date"]) >= today]

    print(f"[경제지표 수집] {len(got)}건 · 오늘 이후 {len(future)}건")
    for n in notes:
        print(f"  ⚠️ {n}")
    print(f"  ⚠️ BLS(고용·CPI·PPI)는 403 으로 막혀 자동 수집 불가 — 수동 입력분 유지\n")
    for e in future[:25]:
        d = (date.fromisoformat(e["date"]) - today).days
        print(f"  D-{d:<3} {e['date']}  {e['name'][:62]}  (리드 {e['watch_days']}일)")

    if not merge:
        print("\n  (--merge 를 주면 macro-calendar.json 에 병합한다)")
        return 0

    data = json.loads(CAL.read_text())
    # 🔴 수동 입력분을 지우지 않는다. 이전 자동 수집분만 갈아끼운다.
    manual = [e for e in data["events"] if not e.get("auto_source")]
    data["events"] = manual + future
    data["events"].sort(key=lambda e: (e.get("date") or "9999", e["name"]))
    CAL.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n")
    print(f"\n  병합 완료 — 수동 {len(manual)}건 + 자동 {len(future)}건 = {len(data['events'])}건")
    return 0


if __name__ == "__main__":
    sys.exit(main())
