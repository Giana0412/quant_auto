#!/usr/bin/env python3
"""LSEG Lipper Alpha Insight 정기 리포트 추적기.

── 왜 ────────────────────────────────────────────────────────────────────
LSEG(구 Refinitiv)가 lipperalpha.refinitiv.com 에 **무료로** 매주 올리는
애널리스트 리포트들이다(Tajinder Dhillon, CFA). 대회 기간이 26Q3 실적 시즌과
겹치는데, 이 리포트가 **섹터별 컨센서스 성장률·추정치 리비전·서프라이즈율·
실적 캘린더**를 매주 갱신해 준다.

실제로 26Q3 컨센서스를 보면 에너지 +109.6% · 반도체 +131.2% 인데 금융은 +5.4%
(11개 섹터 중 하위권)라, 팀 전략의 금융주 비중을 다시 볼 근거가 된다.
블룸버그 터미널이 학교에 2대뿐이라 접근이 제한적인 것과 달리 이건 아무 때나 볼 수 있다.

── 🔴 robots.txt 를 지킨다 — PDF 는 자동으로 받지 않는다 ─────────────────
이 사이트의 robots.txt 는 이렇게 돼 있다:

    User-agent: *
    Disallow: /feed/
    Disallow: /wp-content/      ← PDF 가 여기 있다
    ...
    User-agent: Twitterbot
    Allow: /wp-content/uploads/

즉 **PDF 경로(/wp-content/uploads/)와 RSS(/feed/)는 일반 봇에게 금지**다.
그래서 이 스크립트는:
  · 디스커버리를 **sitemap** 으로 한다 (금지 목록에 없고, 애초에 크롤러에게
    알려주려고 존재하는 경로다). RSS 는 금지라 안 쓴다.
  · 글 본문 페이지(/2026/09/...)만 읽어 **제목·날짜·PDF 링크**를 뽑는다.
  · **PDF 자체는 내려받지 않는다.** 링크만 브리핑에 띄우고 사람이 클릭한다.

리포트는 공개·무료이고 사이트의 Disallow 목록은 워드프레스 기본값 그대로라
(wp-admin·wp-includes·xmlrpc 등) PDF 를 겨냥한 조항으로 보이지는 않는다.
그래도 기계가 읽으라고 써 둔 표시는 지키는 게 맞다 — 사람이 브라우저로 받는 건
robots.txt 와 무관하므로 실질적으로 잃는 건 클릭 한 번뿐이다.

캐시를 둬서 **이미 본 글은 다시 요청하지 않는다.** 주 1회 실행 기준으로 새 글
2~3건만 페이지를 읽으므로 서버 부담이 거의 없다.

사용:
  .automation/.venv/bin/python .automation/lseg_reports.py             # 최근 21일 중 새 것
  .automation/.venv/bin/python .automation/lseg_reports.py --days 60   # 창을 넓혀서
  .automation/.venv/bin/python .automation/lseg_reports.py --all       # 캐시 전체 보기
  .automation/.venv/bin/python .automation/lseg_reports.py --backfill  # 과거 전부 수집
"""
import json
import re
import sys
import time
import urllib.request
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

BASE = "https://lipperalpha.refinitiv.com"
SITEMAP_INDEX = f"{BASE}/sitemap_index.xml"
SEEN = Path("personal/10-market/_reports/lseg-seen.jsonl")

# 추적할 정기 발행물. slug 접두사 → 표시 이름.
# 새 계열을 넣고 싶으면 sitemap 에서 slug 를 보고 여기 추가하면 된다.
FAMILIES = {
    "this-week-in-earnings": "This Week in Earnings",
    "weekly-aggregates-report": "Weekly Aggregates",
    "sp-500-earnings-dashboard": "S&P 500 Earnings Dashboard",
    "earnings-scorecard": "Earnings Scorecard",
    "sp-500-earnings-today": "S&P 500 Earnings Today",
    "lipper-u-s-fund-flows": "Lipper US Fund Flows",
    "stockreports-": "StockReports+",
}

# 사람이 브라우저로 볼 때와 같은 UA 를 쓰되 정체를 밝힌다. 연락처 없이 봇 이름만
# 다는 건 오히려 불친절해서, 평범한 UA 뒤에 목적을 덧붙였다.
UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/140.0 Safari/537.36 "
      "(LC-Ghosts-research-bot; weekly; respects robots.txt)")
TIMEOUT = 25
POLITE_DELAY = 1.5      # 연속 요청 사이 간격(초)

# 🔴 평소 실행은 **최근 것만** 본다. 이게 없으면 sitemap 에 있는 과거 발행물
# 344건을 MAX_FETCH 씩 거슬러 올라가며 29번을 돌아야 한다 — 매주 한 번 쓰는
# 도구에서 아무도 안 읽을 2011년 글을 계속 긁는 셈이다.
# 과거를 훑고 싶으면 --backfill 로 명시한다.
DEFAULT_WINDOW_DAYS = 21


def fetch(url):
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
        return r.read().decode("utf-8", errors="replace")


def latest_post_sitemap():
    """post-sitemap 청크 중 가장 번호가 큰 것. 워드프레스(Yoast)는 오래된 글부터
    청크를 채우므로 **최신 글은 마지막 청크**에 있다 — post-sitemap.xml 을 그냥
    읽으면 2011년 글이 나온다(실제로 한 번 헛짚었다)."""
    xml = fetch(SITEMAP_INDEX)
    names = set(re.findall(r"post-sitemap(\d*)\.xml", xml))
    if not names:
        return None
    nums = sorted((int(n) if n else 1) for n in names)
    n = nums[-1]
    return f"{BASE}/post-sitemap{'' if n == 1 else n}.xml"


def sitemap_entries(url):
    """(글 URL, lastmod) 목록."""
    xml = fetch(url)
    out = []
    for m in re.finditer(r"<url>(.*?)</url>", xml, re.S):
        blk = m.group(1)
        loc = re.search(r"<loc>([^<]+)</loc>", blk)
        mod = re.search(r"<lastmod>([^<]+)</lastmod>", blk)
        if loc:
            out.append((loc.group(1).strip(), (mod.group(1).strip() if mod else "")))
    return out


def classify(url):
    """글 URL 이 추적 대상 계열인지. 맞으면 (계열키, 표시이름)."""
    slug = url.rstrip("/").rsplit("/", 1)[-1]
    for key, name in FAMILIES.items():
        if slug.startswith(key):
            return key, name
    return None, None


def parse_post(url):
    """글 페이지에서 제목과 PDF 링크를 뽑는다. **PDF 는 받지 않는다**(§docstring)."""
    html = fetch(url)
    t = re.search(r"<title>(.*?)</title>", html, re.S | re.I)
    title = re.sub(r"\s+", " ", t.group(1)).strip() if t else ""
    title = re.sub(r"\s*\|\s*Lipper Alpha Insight.*$", "", title)
    title = (title.replace("&#124;", "|").replace("&amp;", "&")
                  .replace("&#8217;", "’").replace("&nbsp;", " ").strip())
    pdfs = re.findall(r'href="([^"]+\.pdf)"', html)
    return title, (pdfs[0] if pdfs else None)


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
        for r in sorted(recs.values(), key=lambda r: (r.get("lastmod", ""), r["url"])):
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    tmp.replace(SEEN)


def main():
    backfill = "--backfill" in sys.argv
    days = None if backfill else DEFAULT_WINDOW_DAYS
    if "--days" in sys.argv:
        try:
            days = int(sys.argv[sys.argv.index("--days") + 1])
        except Exception:
            pass
    show_all = "--all" in sys.argv

    seen = load_seen()

    # --all 은 네트워크를 안 타고 캐시만 보여준다. days 기본값(21)이 생기면서
    # `not days` 조건이 항상 거짓이 돼 크롤링 경로로 새는 버그가 있었다.
    if show_all:
        rows = sorted(seen.values(), key=lambda r: r.get("lastmod", ""), reverse=True)
        print(f"[LSEG 리포트] 캐시 {len(rows)}건")
        for r in rows[:40]:
            print(f"  {r.get('lastmod','')[:10]}  {r.get('family',''):<28} {r.get('title','')[:60]}")
            if r.get("pdf"):
                print(f"              {r['pdf']}")
        return 0

    try:
        sm = latest_post_sitemap()
        if not sm:
            print("[LSEG 리포트] sitemap 을 못 찾았다", file=sys.stderr)
            return 1
        entries = sitemap_entries(sm)
    except Exception as e:
        # 🔴 외부 사이트가 죽어도 브리핑 전체를 죽이지 않는다
        print(f"[LSEG 리포트] 조회 실패: {str(e)[:70]}", file=sys.stderr)
        return 0

    cutoff = None
    if days:
        cutoff = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()

    fresh = []
    for url, mod in entries:
        key, name = classify(url)
        if not key:
            continue
        if cutoff and mod and mod < cutoff:
            continue
        if url in seen:
            continue
        fresh.append((url, mod, key, name))

    # 오래된 것부터 처리하되, 한 번에 너무 많이 긁지 않는다
    fresh.sort(key=lambda x: x[1])
    MAX_FETCH = 12
    dropped = max(0, len(fresh) - MAX_FETCH)
    fresh = fresh[-MAX_FETCH:]

    added = []
    for i, (url, mod, key, name) in enumerate(fresh):
        if url in seen and seen[url].get("title"):
            rec = seen[url]
        else:
            if i:
                time.sleep(POLITE_DELAY)
            try:
                title, pdf = parse_post(url)
            except Exception as e:
                print(f"  ⚠️ {url} 읽기 실패: {str(e)[:40]}", file=sys.stderr)
                continue
            rec = dict(url=url, lastmod=mod, family=name, family_key=key,
                       title=title, pdf=pdf,
                       first_seen=date.today().isoformat())
            seen[url] = rec
        added.append(rec)

    save_seen(seen)

    print(f"[LSEG 리포트] 새 발행물 {len(added)}건"
          + (f" (최근 {days}일)" if days else " (전체 소급)")
          + (f" · 한 번에 {MAX_FETCH}건까지만 봐서 {dropped}건 남겨둠 — 다시 실행하면 이어서 본다"
             if dropped else ""))
    if not added:
        print("  없음 — 마지막 확인 이후 새로 올라온 게 없다"
              + (f" (최근 {days}일 기준)" if days else ""))
        return 0

    for r in sorted(added, key=lambda r: r.get("lastmod", ""), reverse=True):
        when = (r.get("lastmod") or "")[:10]
        print(f"  {when}  [{r['family']}]")
        print(f"     {r.get('title','')}")
        if r.get("pdf"):
            print(f"     PDF: {r['pdf']}")
        else:
            print(f"     {r['url']}")
    print("\n  ※ PDF 는 자동으로 받지 않는다 — 이 사이트 robots.txt 가 /wp-content/ 를")
    print("     일반 봇에게 막아 두었다. 링크를 눌러 직접 받으면 된다(사람은 무관).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
