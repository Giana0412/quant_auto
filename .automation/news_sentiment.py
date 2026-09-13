#!/usr/bin/env python3
"""뉴스 센티멘트 ↔ 가격 반응 매칭. 1차 미팅(260911) 김규형 액션 아이템.

── 왜 이 설계인가 ────────────────────────────────────────────────────────
회의에서 "뉴스 센티멘트와 변동성을 매칭하는 기능"을 맡았다. 만들려면 세 가지가
필요한데, 각각을 이렇게 풀었다.

1) **뉴스 소스 — 뉴스레터가 아니라 yfinance 티커별 뉴스를 쓴다.**
   기존 파이프라인의 뉴스 경로(newsletter_fetch.py → 뉴닉·어피티·블룸버그)는
   **한국어 일반 소비자용**이라 미국 중소형 서플라이어 커버리지가 사실상 0 이다.
   그리고 더 큰 문제는 **조인 키가 없다**는 것이었다 — 뉴스 본문과 [스크리닝]
   종목을 잇는 건 지금까지 daily-conclusion.sh 의 LLM 이 문맥으로 하는 일이었고
   숫자로 매칭되는 구조가 아니었다. yfinance 의 Ticker.news 는 애초에 **티커에
   붙어서** 오므로 그 문제가 통째로 사라진다(별도 개체명 인식이 필요 없다).

2) **점수 — 외부 라이브러리 없이 금융 전용 렉시콘으로 센다.**
   VADER 같은 범용 감성분석기는 금융 헤드라인에서 자주 틀린다: beat·miss·cut·
   short·outperform 은 일상 영어와 금융에서 뜻이 다르다("beats estimates"는
   강한 호재인데 범용 사전은 beat 를 폭력으로 읽는다). 그리고 이 저장소는
   운영 venv 가 이미 취약해서(curl_cffi 조차 없다) 의존성을 늘리고 싶지 않다.
   LLM 을 부르지 않는 이유는 파이프라인의 기존 방침과 같다 — 기계적으로 셀 수
   있는 일에 에이전트를 끼우지 않는다(§newsletter_fetch.py docstring). 덕분에
   결정적이고, 오프라인이고, 헤드라인 수백 개를 세도 비용이 0 이다.

3) **"변동성과 매칭" 이 뭔지 — 뉴스와 가격이 어긋난 종목을 찾는 것이다.**
   센티멘트만 내면 "좋은 뉴스가 있다"까지밖에 말 못 한다. 매매에 쓰려면
   **그 뉴스가 이미 가격에 반영됐는지**를 알아야 한다. 그래서 센티멘트 점수와
   최근 5거래일 벤치 대비 초과수익을 나란히 놓고 어긋난 쪽을 표시한다:
     · 뉴스 좋은데 아직 안 올랐다  → 🟢 미반영 (진입 후보)
     · 뉴스 좋고 이미 올랐다      → ⚪ 반영됨 (쫓아 사는 것)
     · 뉴스 나쁜데 안 빠졌다      → 🔴 미반영 위험 (보유 중이면 점검)
     · 뉴스 나쁘고 이미 빠졌다    → ⚪ 반영됨
   여기에 변동성(21일 고저폭)을 같이 낸다 — 뉴스가 강한데 변동성이 낮은 종목은
   "아직 안 움직인" 것이고, 그게 회의에서 정한 "한 달 안에 움직일 종목" 찾기와
   직접 이어진다.

🔴 **한계 — 이건 신호 보조지 매매 근거가 아니다.**
헤드라인 한 줄에서 센 점수라 맥락(이미 알려진 뉴스인지, 루머인지)을 모른다.
표본도 티커당 10건 남짓이고, 뉴스가 없는 종목은 점수가 없는 게 아니라 **모르는
것**이다(0 과 구분해서 표시한다).

실측 오탐률(2026-09-13, 20종목 첫 실행): NOISE 필터를 넣기 전 판정 13건 중
4건이 오탐이었다. 필터 후 남은 오탐 유형은 **제목에 티커가 나오지만 본문
주인공은 다른 회사**인 경우다 — 예: TJX 가 "Macy's Sinks 5% Despite Raised
Full-Year Outlook, Kohl's and TJX Barely Budge" 로 +1.00 을 받았는데 정작
TJX 는 "barely budge" 다. is_relevant() 가 티커 등장만 보기 때문이고, 제목
안에서 티커의 **위치·역할**까지 보려면 파싱이 훨씬 무거워진다. 그래서 지금은
근거 헤드라인을 항상 같이 출력한다 — **사람이 한 줄 읽고 기각할 수 있게** 하는
게 이 단계에서 가장 싼 방어다. 필터를 조일수록 '모름' 이 늘어나는 맞교환이
있고(4→10종목), 틀린 확신보다 모름이 낫다고 보고 조이는 쪽을 택했다.

실행:
  .automation/.venv/bin/python .automation/news_sentiment.py            # 스크리닝 상위 자동
  .automation/.venv/bin/python .automation/news_sentiment.py SWKS QRVO  # 종목 지정
"""
import re
import sys
import warnings
from datetime import datetime, timedelta, timezone

warnings.filterwarnings("ignore")

import pandas as pd
import yfinance as yf
from gs_quant.timeseries import returns

from market_metrics import (
    BENCH, LOOKBACKS, MIN_SPAN21, excess, fetch, rel_vol, screen, screen_universe, span21,
)

# ── 금융 전용 센티멘트 렉시콘 ────────────────────────────────────────────
# 가중치는 -3~+3. 여러 단어로 된 표현을 먼저 본다 — "price target cut" 을
# 그냥 두면 cut(-2) 하나로만 세지만 실제로는 더 강한 신호이고, 반대로
# "cuts costs" 는 호재인데 cut 로 잡히면 부호가 뒤집힌다.
PHRASES = {
    # 실적·가이던스 (가장 강한 신호)
    r"beats?\s+(analyst\s+)?(estimates?|expectations?|forecasts?)": 3,
    r"tops?\s+(analyst\s+)?(estimates?|expectations?|forecasts?)": 3,
    r"miss(es|ed)?\s+(analyst\s+)?(estimates?|expectations?|forecasts?)": -3,
    r"rais(es|ed)\s+(full[- ]year\s+)?(guidance|outlook|forecast)": 3,
    r"(cuts?|lowers?|slash(es|ed)?)\s+(full[- ]year\s+)?(guidance|outlook|forecast)": -3,
    r"withdraws?\s+guidance": -3,
    r"profit\s+warning": -3,
    # 애널리스트 액션
    r"price\s+target\s+(raised|hiked|increased|up)": 2,
    r"(raises?|hikes?|lifts?)\s+price\s+target": 2,
    r"price\s+target\s+(cut|lowered|reduced|slashed|down)": -2,
    r"(cuts?|lowers?)\s+price\s+target": -2,
    r"upgrade[ds]?\s+to": 3, r"downgrade[ds]?\s+to": -3,
    # 비용절감은 호재 — cut 단독 규칙에 먹히지 않도록 먼저 잡는다
    r"(cuts?|cutting)\s+(costs?|expenses?|debt)": 2,
    # 자본정책
    r"(share\s+)?(buyback|repurchase)": 2,
    r"(rais(es|ed)|hikes?|boosts?)\s+dividend": 2,
    r"(cuts?|suspends?)\s+dividend": -3,
    r"(stock|share)\s+offering": -2,          # 희석
    # 사건
    r"short\s+seller": -3, r"class\s+action": -2,
    r"(sec|doj|ftc)\s+(probe|investigation|inquiry)": -3,
    r"steps?\s+down|resign(s|ed)?": -2,
    r"(wins?|awarded|secures?)\s+(contract|deal|order|approval)": 2,
    r"fda\s+approv(al|es|ed)": 3, r"fda\s+reject": -3,
}
WORDS = {
    # 긍정
    "surge": 2, "surges": 2, "soar": 2, "soars": 2, "jumps": 2, "jumped": 2,
    "rally": 2, "rallies": 2, "rebound": 1, "climbs": 1, "gains": 1, "rises": 1,
    "upgrade": 3, "upgraded": 3, "outperform": 2, "overweight": 2,
    "beats": 2, "beat": 2, "tops": 2, "exceeds": 2, "record": 2, "strong": 1,
    "growth": 1, "expands": 1, "wins": 2, "breakthrough": 2, "bullish": 2,
    "profitable": 1, "turnaround": 1, "upside": 1, "optimistic": 1, "boost": 1,
    "partnership": 1, "acquires": 1, "milestone": 1, "accelerating": 1,
    # 부정
    "plunge": -2, "plunges": -2, "tumbles": -2, "sinks": -2, "slumps": -2,
    "crashes": -3, "falls": -1, "drops": -1, "slides": -1, "declines": -1,
    "downgrade": -3, "downgraded": -3, "underperform": -2, "underweight": -2,
    "miss": -2, "misses": -2, "missed": -2, "weak": -1, "weakness": -1,
    "warns": -2, "warning": -2, "lawsuit": -2, "probe": -2, "investigation": -2,
    "recall": -2, "delay": -1, "delayed": -1, "halted": -2, "bankruptcy": -3,
    "layoffs": -1, "fraud": -3, "downside": -1, "bearish": -2, "disappointing": -2,
    "concerns": -1, "headwinds": -1, "slowdown": -1, "loss": -1, "losses": -1,
    "struggles": -1, "plummet": -3, "plummets": -3,
}
# 부정어가 앞 3단어 안에 있으면 부호를 뒤집는다 ("fails to beat" 같은 것)
NEGATORS = re.compile(r"\b(not|no|never|fails?\s+to|failed\s+to|without|unlikely)\b")

# 🔴 기사가 아닌 것 — 세면 점수가 오염된다. 첫 실행(2026-09-13)에서 실제로 나온 오탐:
#   "Can Strong End-Market Demand Boost Carpenter Technology's Growth?"
#     → strong·growth·boost 로 +1.00 만점. 그냥 질문형 클릭베이트다.
#   "Axon beats Palantir by 36 Roundtable 100 spots"
#     → beats 가 실적이 아니라 랭킹 순위다.
#   "3 Under-the-Radar Defense Stocks With Record Backlogs" → record 로 가점.
#   "Should Value Investors Buy Marathon Petroleum (MPC) Stock?" → strong·growth.
# 공통점은 **새 사실을 전달하지 않는다**는 것이다. 물음표로 끝나는 제목,
# 숫자로 시작하는 리스티클, 정기 코너(Zacks Bull/Bear), 실적 콜 전문(transcript)을
# 뺀다. 헤드라인 렉시콘의 최대 약점이 이 부류라 소스 단계에서 거르는 게 낫다.
NOISE = [
    r"\?\s*$",                                   # 질문형 — 사실이 아니라 추측이다
    r"^\d+\s",                                   # "3 Under-the-Radar ..." 리스티클
    r"\b(best|top)\b.{0,30}\b(stocks?|picks?)\b.{0,20}\b(to buy|for)\b",
    r"earnings call transcript",
    r"zacks\s+(bull|bear)|zacks\.com|featured highlights",
    r"what you need to know",
    r"\bbeats?\s+\w+\s+by\s+\d+",                # "beats Palantir by 36 spots" — 실적이 아니라 랭킹
    r"\b(should|is|are|can|will|does|do)\b.{0,40}\b(buy|worth|good)\b",
    r"here('| i)s why",                          # "Stock Trades Up, Here Is Why"
    r"\bmotley fool\b|\bstocks? to watch\b",
]
NOISE_RE = re.compile("|".join(NOISE), re.I)

MAX_AGE_DAYS = 7      # 이보다 오래된 기사는 "지금 상태"를 말해주지 않는다
MIN_ARTICLES = 2      # 1건짜리 점수는 표본이 아니라 우연이다 — 표시는 하되 약하다고 표기
MOVE_DAYS = 5         # 가격이 뉴스를 얼마나 따라왔는지 재는 창


def score_text(text):
    """헤드라인 한 줄의 센티멘트. 반환 (원점수, 매칭수, 매칭어)."""
    t = " " + text.lower() + " "
    total, hits, matched = 0, 0, []
    for pat, w in PHRASES.items():
        for m in re.finditer(pat, t):
            head = t[max(0, m.start() - 40):m.start()]
            sign = -1 if NEGATORS.search(head) else 1
            total += w * sign
            hits += 1
            matched.append(m.group(0).strip())
    # 이미 구(句)로 잡힌 구간은 단어 규칙에서 제외한다 — "price target cut" 을
    # -2 로 세고 cut 을 또 -2 로 세면 같은 사건을 두 번 세는 것이다.
    for phrase in matched:
        t = t.replace(phrase.lower(), " ")
    for w_, val in WORDS.items():
        for m in re.finditer(rf"\b{re.escape(w_)}\b", t):
            head = t[max(0, m.start() - 30):m.start()]
            sign = -1 if NEGATORS.search(head) else 1
            total += val * sign
            hits += 1
            matched.append(w_)
    return total, hits, matched


def fetch_news(ticker, max_age_days=MAX_AGE_DAYS):
    """티커에 붙은 최근 뉴스. yfinance 스키마가 판올림되며 바뀌어서
    (예전엔 평평한 dict, 지금은 {'id', 'content'}) 양쪽을 다 받는다."""
    try:
        raw = yf.Ticker(ticker).news or []
    except Exception:
        return []
    cutoff = datetime.now(timezone.utc) - timedelta(days=max_age_days)
    out = []
    for item in raw:
        c = item.get("content", item) if isinstance(item, dict) else {}
        title = (c.get("title") or "").strip()
        if not title:
            continue
        pub = c.get("pubDate") or c.get("providerPublishTime")
        try:
            when = (datetime.fromisoformat(pub.replace("Z", "+00:00"))
                    if isinstance(pub, str)
                    else datetime.fromtimestamp(pub, tz=timezone.utc))
        except Exception:
            continue
        if when < cutoff:
            continue
        prov = c.get("provider")
        out.append(dict(
            title=title, summary=(c.get("summary") or "")[:400], when=when,
            provider=(prov.get("displayName") if isinstance(prov, dict) else prov) or "?",
        ))
    return out


def is_relevant(article, ticker, name):
    """그 종목 얘기가 맞는지. yfinance 는 티커에 붙여 주기는 하는데 느슨하다 —
    실측(2026-09-13)에서 MTCH 의 최상위 기사가 Reddit(RDDT) 얘기였다.
    티커나 회사명이 제목·요약에 실제로 나오는 것만 센다."""
    hay = (article["title"] + " " + article["summary"]).lower()
    if re.search(rf"\b{re.escape(ticker.lower())}\b", hay):
        return True
    if name:
        # "Skyworks Solutions, Inc." → 첫 두 단어까지만 보고 접미사는 버린다
        core = re.sub(r"\b(inc|corp|corporation|co|ltd|plc|group|holdings?|the)\b\.?", "",
                      name.lower()).strip()
        first = " ".join(core.split()[:2])
        if len(first) >= 4 and first in hay:
            return True
    return False


def ticker_sentiment(ticker, name=None):
    """티커 하나의 센티멘트 집계. 뉴스가 없으면 None 을 돌려준다 —
    **점수 0 과 '모른다'는 다른 상태다.** 0 으로 뭉개면 뉴스가 없는 종목이
    '중립 뉴스가 있는 종목'처럼 보여서 매칭 표에서 같은 취급을 받는다."""
    arts = [a for a in fetch_news(ticker)
            if is_relevant(a, ticker, name) and not NOISE_RE.search(a["title"])]
    if not arts:
        return None
    scored = []
    for a in arts:
        s, hits, matched = score_text(a["title"] + ". " + a["summary"])
        if hits:
            scored.append((s, a, matched))
    if not scored:
        return None
    raw = [s for s, _, _ in scored]
    # 기사당 점수를 [-1, 1] 로 눌러 한 기사가 표를 지배하지 않게 한다
    norm = [max(-1.0, min(1.0, s / 3.0)) for s in raw]
    best = max(scored, key=lambda x: abs(x[0]))
    return dict(
        n=len(scored), score=sum(norm) / len(norm),
        pos=sum(1 for s in raw if s > 0), neg=sum(1 for s in raw if s < 0),
        top_title=best[1]["title"][:88], top_score=best[0],
        top_terms=", ".join(dict.fromkeys(best[2]))[:60],
        newest=max(a["when"] for _, a, _ in scored),
    )


def classify(sent, move):
    """센티멘트와 가격 반응이 어긋난 쪽을 찾는다 (§docstring 3번).
    임계값은 '확정된 최적값'이 아니라 출발점이다 — 센티 |0.15| 는 기사
    두어 건이 같은 방향을 가리키는 정도, 이동 |2%p| 는 5거래일 초과수익으로
    의미 있는 반응이라고 볼 만한 하한이다."""
    S, MV = 0.15, 2.0
    if sent >= S and move < MV:
        return "🟢 미반영", "호재인데 아직 안 올랐다 — 진입 후보"
    if sent >= S and move >= MV:
        return "⚪ 반영됨", "호재가 이미 가격에 있다 — 쫓아 사는 것"
    if sent <= -S and move > -MV:
        return "🔴 미반영", "악재인데 안 빠졌다 — 보유 중이면 점검"
    if sent <= -S and move <= -MV:
        return "⚪ 반영됨", "악재가 이미 반영됐다"
    return "· 중립", ""


def main():
    extras = [a.upper() for a in sys.argv[1:] if not a.startswith("-")]
    df, _ = fetch()
    if BENCH not in df.columns:
        print("벤치마크(ACWI) 를 못 받았다 — 상대값 계산 불가", file=sys.stderr)
        return 1
    b = df[BENCH].dropna()

    if extras:
        syms, tags = extras, {t: "" for t in extras}
        px = yf.download(syms, period="6mo", interval="1d",
                         progress=False, auto_adjust=True)["Close"]
        if isinstance(px, pd.Series):
            px = px.to_frame(syms[0])
        px = px.reindex(b.index).ffill().dropna(axis=1, how="all")
    else:
        # 스크리닝 상위·하위를 본다 — 하위도 봐야 "악재인데 안 빠진" 쪽이 잡힌다.
        # 206종목 전부에 뉴스를 받으면 호출이 200번이라 상위/하위만 본다.
        src = screen_universe()
        up, down, _, px, _ = screen(b, src, top=10)
        rows = up + down
        syms = [r[3] for r in rows]
        tags = {r[3]: r[4] for r in rows}

    print(f"[뉴스 센티멘트 ↔ 가격 반응]  최근 {MAX_AGE_DAYS}일 기사 · "
          f"가격 반응은 {MOVE_DAYS}거래일 벤치 대비 초과수익")
    print(f"  {'티커':<7}{'센티':>7}{'기사':>5}{'5일':>8}{'21일폭':>8}  {'판정':<9} 근거")

    results, unknown = [], []
    for s in syms:
        name = None
        try:
            name = (yf.Ticker(s).info or {}).get("shortName")
        except Exception:
            pass
        sent = ticker_sentiment(s, name)
        if sent is None:
            unknown.append(s)
            continue
        ser = px[s].dropna() if s in px.columns else None
        if ser is None or len(ser) < MOVE_DAYS + 2:
            unknown.append(s)
            continue
        move = excess(ser, b, MOVE_DAYS)
        if move is None:
            unknown.append(s)
            continue
        sp = span21(ser)
        mark, why = classify(sent["score"], move)
        results.append(dict(sym=s, sent=sent, move=move, span=sp, mark=mark, why=why,
                            tag=tags.get(s, "")))

    # 어긋난 것(🟢/🔴)을 위로 — 매일 훑을 때 가장 볼 값이 있는 줄이다
    results.sort(key=lambda r: (r["mark"].startswith("·"), r["mark"].startswith("⚪"),
                                -abs(r["sent"]["score"])))
    for r in results:
        weak = "*" if r["sent"]["n"] < MIN_ARTICLES else " "
        print(f"  {r['sym']:<7}{r['sent']['score']:>+7.2f}{r['sent']['n']:>4}{weak}"
              f"{r['move']:>+7.1f}%{r['span']:>7.1f}%  {r['mark']:<9} {r['why']}")
        if not r["mark"].startswith("·"):
            print(f"           └ \"{r['sent']['top_title']}\" ({r['sent']['top_terms']})")

    if unknown:
        # 🔴 뉴스 없음을 '중립'으로 뭉개지 않는다 — 모르는 것과 중립은 다르다
        print(f"\n  판정 불가 {len(unknown)}종목 (최근 {MAX_AGE_DAYS}일 관련 기사 없음 "
              f"— 중립이 아니라 '모름'이다): {' · '.join(unknown)}")
    print(f"\n  * 표시는 기사 {MIN_ARTICLES}건 미만이라 점수가 약하다는 뜻이다.")
    print("  ※ 헤드라인 렉시콘 점수라 맥락(이미 알려진 뉴스인지·루머인지)을 모른다 —"
          " 신호 보조지 매매 근거가 아니다.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
