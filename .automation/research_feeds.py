#!/usr/bin/env python3
"""기관 리서치 리포트 추적 — 자동으로 되는 건 긁고, 안 되는 건 링크만 보낸다.

── 왜 이렇게 나뉘었나 ────────────────────────────────────────────────────
2026-09-20 에 발행처 7곳(BlackRock·Morgan Stanley·Goldman Sachs·JPM·
Standard Chartered·Franklin Templeton·Deloitte)을 하나씩 실제로 찔러 본 결과,
**자동 수집이 되는 곳은 BlackRock 하나뿐**이었다.

  · **BlackRock** — 랜딩 페이지 정적 HTML 에 최신호 PDF 링크가 그대로 있고,
    robots.txt 가 /us/individual/literature/ 를 막지 않는다. 실측으로
    HTTP 200 · 222KB 다운로드까지 확인했다. → **크롤링한다.**

  · **JPM · Franklin · Morgan Stanley · Deloitte** — 금지된 건 아닌데 페이지가
    SPA 라 정적 HTML 에 PDF 링크가 **0건**이다. 뽑으려면 헤드리스 브라우저가
    필요한데, 주 1회 PDF 하나 받자고 Playwright 를 체인에 넣는 건 배보다 배꼽이다
    (설치 용량·깨지기 쉬움·지금도 체인이 106초다). → **링크만 보낸다.**
    · 여담: Morgan Stanley 는 robots.txt 에 ClaudeBot·anthropic-ai 를 **명시적으로
      허용**해 두었다. 크롤링을 환영하는데 정작 페이지가 JS 라 정적으로는 안 잡힌다.

  · **Standard Chartered** — robots.txt 가 /_documents/ 를 막는다. PDF 가 거기 있다.
    → **링크만 보낸다.**

  · 🔴 **Goldman Sachs** — robots.txt 가 `*` 에게는 열어 두면서 **GPTBot·
    ChatGPT-User 에게만 /what-we-do/research/ 와 /insights/top-of-mind/ 를 막았다.**
    "사람은 되고 AI 크롤러는 안 된다"를 명시적으로 표현한 것이다. 우리 봇이
    기술적으로 GPTBot 이 아니더라도 의도를 알면서 우회할 이유가 없다.
    → **절대 긁지 않는다. 링크만 보낸다.**

링크만 보내는 쪽은 **매일 보내면 소음**이라 요일을 지정해 주 1회만 낸다
(대부분 목·금에 발행된다). 사람이 클릭해서 받는 건 robots.txt 와 무관하다.

사용:
  .automation/.venv/bin/python .automation/research_feeds.py          # 평소(새 것만)
  .automation/.venv/bin/python .automation/research_feeds.py --links  # 수동 목록 강제 출력
  .automation/.venv/bin/python .automation/research_feeds.py --all    # 캐시 보기
"""
import json
import re
import sys
import urllib.request
from datetime import date, datetime
from pathlib import Path

SEEN = Path("personal/10-market/_reports/research-seen.jsonl")

UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/140.0 Safari/537.36 "
      "(LC-Ghosts-research-bot; weekly; respects robots.txt)")
TIMEOUT = 25

# ── 자동 수집 ────────────────────────────────────────────────────────────
# 랜딩 페이지에서 PDF 링크를 정규식으로 뽑는다. 페이지 구조가 바뀌면 조용히
# 0건이 되므로, 0건일 때 그 사실을 출력한다(실패를 성공처럼 보이게 두지 않는다).
CRAWLABLE = [
    dict(
        key="blackrock-weekly",
        name="BlackRock Weekly Commentary",
        landing="https://www.blackrock.com/us/individual/insights/"
                "blackrock-investment-institute/weekly-commentary",
        pattern=r'href="([^"]*weekly-investment-commentary[^"]*\.pdf)"',
        base="https://www.blackrock.com",
    ),
]

# ── 링크만 (자동 수집 불가·부적절) ───────────────────────────────────────
MANUAL = [
    ("JPM Weekly Market Recap", "매주",
     "https://am.jpmorgan.com/us/en/asset-management/adv/insights/"
     "market-insights/market-updates/weekly-market-recap/", "SPA 라 정적 추출 불가"),
    ("Goldman Sachs Insights", "수시",
     "https://www.goldmansachs.com/insights",
     "🔴 robots.txt 가 AI 크롤러에게 리서치를 막음 — 사람이 직접"),
    ("Morgan Stanley Ideas", "수시",
     "https://www.morganstanley.com/ideas", "SPA (단 robots 는 ClaudeBot 허용)"),
    ("Standard Chartered Insights", "매주",
     "https://www.sc.com/en/wealth-insights/", "robots.txt 가 /_documents/ 금지"),
    ("Franklin Templeton Insights", "수시·분기",
     "https://www.franklintempleton.com/investor/insights", "SPA 라 정적 추출 불가"),
    ("Deloitte Insights", "수시",
     "https://www.deloitte.com/us/en/insights.html", "SPA 라 정적 추출 불가"),
    ("LSEG Lipper Alpha", "매주 목",
     "https://lipperalpha.refinitiv.com/",
     "→ lseg_reports.py 가 이미 자동 추적 중"),
]
# 링크 목록을 낼 요일 (0=월 … 4=금). 대부분 목·금 발행이라 금요일에 한 번.
MANUAL_WEEKDAY = 4


def fetch(url):
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
        return r.read().decode("utf-8", errors="replace")


def load_seen():
    if not SEEN.exists():
        return {}
    out = {}
    for line in SEEN.read_text().splitlines():
        try:
            r = json.loads(line)
        except Exception:
            continue
        if isinstance(r, dict) and "url" in r:
            out[r["url"]] = r
    return out


def save_seen(recs):
    SEEN.parent.mkdir(parents=True, exist_ok=True)
    tmp = SEEN.with_suffix(SEEN.suffix + ".tmp")
    with tmp.open("w") as f:
        for r in sorted(recs.values(), key=lambda r: (r.get("pub_date", ""), r["url"])):
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    tmp.replace(SEEN)


def pdf_date(url):
    """파일명에 박힌 발행일(YYYYMMDD)을 뽑는다. 없으면 None."""
    m = re.search(r"(20\d{6})", url)
    if not m:
        return None
    try:
        return datetime.strptime(m.group(1), "%Y%m%d").date().isoformat()
    except Exception:
        return None


def pdf_title(url):
    """파일명 뒤쪽 슬러그를 읽을 만한 제목으로. 날짜·언어코드·확장자를 걷어낸다."""
    slug = url.rsplit("/", 1)[-1].replace(".pdf", "")
    slug = re.sub(r"^.*?-20\d{6}-", "", slug)
    slug = re.sub(r"-(en|us|en-us)-", "-", slug)
    return slug.replace("-", " ").strip().capitalize() or "(제목 없음)"


def crawl_one(src, seen):
    """한 발행처의 최신호를 확인. (레코드 or None, 상태문자열)"""
    try:
        html = fetch(src["landing"])
    except Exception as e:
        return None, f"조회 실패: {str(e)[:50]}"
    links = re.findall(src["pattern"], html, re.I)
    if not links:
        # 🔴 페이지 구조가 바뀌면 여기로 온다. 조용히 넘어가면 "새 게 없음"과
        # 구분이 안 돼서 몇 주째 놓치고도 모른다.
        return None, "PDF 링크를 못 찾음 — 페이지 구조가 바뀌었을 수 있다"
    url = links[0]
    if url.startswith("/"):
        url = src["base"] + url
    if url in seen:
        return None, "새 것 없음"
    rec = dict(url=url, source=src["name"], key=src["key"],
               pub_date=pdf_date(url) or "", title=pdf_title(url),
               first_seen=date.today().isoformat())
    return rec, "새 발행물"


def main():
    force_links = "--links" in sys.argv
    show_all = "--all" in sys.argv
    seen = load_seen()

    if show_all:
        rows = sorted(seen.values(), key=lambda r: r.get("pub_date", ""), reverse=True)
        print(f"[기관 리서치] 캐시 {len(rows)}건")
        for r in rows[:30]:
            print(f"  {r.get('pub_date','')[:10]}  {r.get('source','')}")
            print(f"     {r.get('title','')}")
            print(f"     {r['url']}")
        return 0

    print("[기관 리서치]")
    added, notes = [], []
    for src in CRAWLABLE:
        rec, status = crawl_one(src, seen)
        if rec:
            seen[rec["url"]] = rec
            added.append(rec)
        elif status != "새 것 없음":
            notes.append(f"{src['name']}: {status}")
    save_seen(seen)

    if added:
        for r in added:
            print(f"  🆕 {r['source']}  ({r.get('pub_date') or '날짜 미상'})")
            print(f"     {r['title']}")
            print(f"     {r['url']}")
    else:
        print("  자동 수집분: 새 것 없음")
    for n in notes:
        print(f"  ⚠️ {n}")

    # 링크 목록은 주 1회만 — 매일 내면 소음이고, 매일 내면 아무도 안 읽는다
    if force_links or date.today().weekday() == MANUAL_WEEKDAY:
        print("\n  ── 손으로 받는 곳 (자동 수집 불가) ──")
        for name, freq, url, why in MANUAL:
            print(f"  · {name} ({freq})")
            print(f"    {url}")
            print(f"    — {why}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
