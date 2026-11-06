#!/usr/bin/env python3
"""헤드라인을 모으고 **시장이 직접 라벨을 달게** 한다.

── 왜 이렇게 하나 ────────────────────────────────────────────────────────
사람이 "이 뉴스는 호재/악재" 라고 라벨링하면 두 가지가 망가진다.
  1. 사람의 사전지식이 샌다 — 결과를 알고 나서 라벨을 달게 된다
  2. 비싸다. 수천 건을 일관되게 달 수가 없다

대신 **헤드라인 발행 후 N거래일 벤치 대비 초과수익**을 정답으로 쓴다.
이러면 라벨이 공짜이고, "사람이 호재라고 생각하는 것"이 아니라
**"실제로 주가를 움직인 것"**을 배우게 된다. 둘은 같지 않다.

── 🔴 생존편향이 여기엔 없다 ─────────────────────────────────────────────
개별종목 스크리닝 백테스트는 생존편향 때문에 불가능하다(§market_metrics).
오늘의 ETF 구성종목으로 과거를 돌리면 망한 종목이 이미 빠져 있어서다.

그런데 이 작업은 다르다. 헤드라인은 **그 시점에 실재했고**, 라벨은 **그 이후**
가격이다. 앞을 내다본 정보가 입력에 섞이지 않는다. 다만 수집 대상 유니버스가
오늘 기준이라 **"오늘 살아있는 종목의 뉴스"** 라는 편향은 남는다 — 모델이
"망하는 회사의 뉴스"를 덜 보게 된다. 결과를 읽을 때 이걸 기억해야 한다.

── 한계 ──────────────────────────────────────────────────────────────────
yfinance 는 **최근 1주일 정도**의 기사만 준다. 과거를 소급해 모을 수 없다.
그래서 이 스크립트는 **매일 돌려 쌓는 구조**다(append-only). 처음 한 번
돌리면 수백~수천 건이고, 하루마다 늘어난다.

실행:
  python collect.py                 # 수집 → data/headlines.jsonl 에 누적
  python collect.py --horizon 3     # 라벨 지평(거래일). 기본 3
  python collect.py --relabel       # 가격이 채워진 기존 행의 라벨만 다시 계산
  python collect.py --stats         # 쌓인 데이터 요약
"""
import argparse
import hashlib
import json
import re
import sys
import warnings
from datetime import datetime, timedelta, timezone
from pathlib import Path

warnings.filterwarnings("ignore")

import pandas as pd
import yfinance as yf

HERE = Path(__file__).resolve().parent
# 🔴 데이터는 **한 곳에만** 쌓는다.
# 체인은 운영 클론(~/orca/projects/quant_auto)에서 돌고 학습은 개발 클론에서
# 하는데, 스크립트 옆(HERE/data)에 쌓으면 두 벌로 갈라져 서로 다른 걸 본다.
# 다른 누적 데이터(book-log·regime-log)가 이미 사는 곳에 같이 둔다.
# 환경변수로 덮어쓸 수 있게 열어 둔다(테스트·다른 머신용).
import os
DATA = Path(os.environ.get(
    "HEADLINES_DATA",
    "/Users/gyuhyeongkim/orca/projects/quant_auto"
    "/personal/10-market/_headlines/headlines.jsonl"))
BENCH = "ACWI"
DEFAULT_HORIZON = 3        # 거래일. 1일은 잡음이 너무 크고 5일은 뉴스와 무관해진다

# 파이프라인의 유니버스·잡음필터를 **복사하지 않고 그대로 호출**한다(§bridge.py).
# 복사하면 운영본과 갈라지고, 그러면 베이스라인 비교가 무의미해진다.
import bridge


def fetch_news(ticker, max_age_days=7):
    """티커에 붙은 최근 기사.

    🔴 `Ticker.news` 를 쓰면 안 된다. 2026-10-23 확인 결과 **전 종목 0건**이고,
    그래서 운영 파이프라인의 센티멘트 절도 조용히 죽어 있었다(판정 불가 20/20).
    `yf.Search(..., news_count=N)` 는 같은 라이브러리인데 정상 동작하고,
    `relatedTickers` 까지 줘서 **티커 귀속**이 유지된다.

    Search 는 검색이라 느슨하게 걸리는 기사가 섞인다(AAPL 검색에 'Alliance for
    Open Media' 가 나왔다). relatedTickers 에 해당 티커가 있는 것만 남긴다.
    """
    try:
        raw = yf.Search(ticker, news_count=20).news or []
    except Exception:
        return []
    cutoff = datetime.now(timezone.utc) - timedelta(days=max_age_days)
    out = []
    for a in raw:
        if not isinstance(a, dict):
            continue
        title = (a.get("title") or "").strip()
        rel = a.get("relatedTickers") or []
        if not title or (rel and ticker not in rel):
            continue          # 검색에 얹혀온 무관한 기사를 뺀다
        ts = a.get("providerPublishTime")
        if not isinstance(ts, (int, float)):
            continue
        pub = datetime.fromtimestamp(ts, timezone.utc)
        if pub < cutoff:
            continue
        out.append(dict(title=title, published=pub, uid=a.get("uuid"),
                        publisher=(a.get("publisher") or "").strip(),
                        kind=(a.get("type") or "").strip(), rel=list(rel)))
    return out


def read_rows():
    if not DATA.exists():
        return []
    out = []
    for line in DATA.read_text().splitlines():
        try:
            out.append(json.loads(line))
        except Exception:
            continue
    return out


def write_rows(rows):
    DATA.parent.mkdir(parents=True, exist_ok=True)
    tmp = DATA.with_suffix(".tmp")
    with tmp.open("w") as f:
        for r in sorted(rows, key=lambda r: (r["date"], r["ticker"], r["id"])):
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    tmp.replace(DATA)


def forward_excess(px, bench, ticker, d0, horizon):
    """발행일 종가 → N거래일 뒤 종가, 벤치 대비 초과수익(%).

    🔴 발행일 당일 종가로 들어간다고 가정한다. 장중에 나온 뉴스면 이미 일부가
    반영된 가격이다 — 즉 **실제보다 어려운 문제**를 풀게 된다. 반대로 하면
    (전일 종가 진입) 미래를 보는 것이라 낙관 쪽으로 샌다. 보수적인 쪽을 택했다.
    """
    if ticker not in px.columns:
        return None
    s = px[ticker].dropna()
    b = bench.dropna()
    idx = s.index[s.index.date >= d0]
    if len(idx) < horizon + 1:
        return None                      # 아직 N일이 안 지났다 — 나중에 relabel
    t0, t1 = idx[0], idx[horizon]
    if t0 not in b.index or t1 not in b.index:
        return None
    r = float(s.loc[t1] / s.loc[t0] - 1) * 100
    rb = float(b.loc[t1] / b.loc[t0] - 1) * 100
    return r - rb


def collect(horizon):
    src = bridge.universe()
    noise_re = re.compile("|".join(bridge.noise_patterns()), re.I)
    tickers = sorted(src)
    print(f"[수집] 유니버스 {len(tickers)}종목에서 헤드라인을 긁는다")
    # 🔴 screen_universe 는 네트워크가 죽으면 예외 없이 {} 를 준다. 2026-11-01·11-04
    #   (배터리·절전으로 체인이 몇 시간 늘어진 날) 0종목을 긁고도 rc=0 → 체인 ✅ 였다.
    #   7일치를 다시 긁는 다음 날이 메웠지만, 이틀 넘게 이어지면 조용히 날짜가 빈다.
    #   라벨 단계도 같은 네트워크를 쓰니 건너뛰고 실패로 끝낸다 — 체인에 🔴 가 찍힌다.
    if not tickers:
        print("[수집] 🔴 유니버스 0종목 — 네트워크/절전 의심, 수집·라벨 건너뜀")
        return 2

    existing = read_rows()
    seen = {r["id"] for r in existing}
    fresh = []
    for i, t in enumerate(tickers, 1):
        if i % 40 == 0:
            print(f"  {i}/{len(tickers)} … 신규 {len(fresh)}건")
        for a in fetch_news(t, max_age_days=7):
            title = (a.get("title") or "").strip()
            if not title or len(title) < 15:
                continue
            if noise_re.search(title):
                continue                 # 클릭베이트·리스티클은 소스에서 뺀다
            pub = a.get("published")
            if isinstance(pub, (int, float)):
                pub = datetime.fromtimestamp(pub, timezone.utc)
            if not isinstance(pub, datetime):
                continue
            # 🔴 hash() 는 파이썬이 실행마다 시드를 바꿔서 같은 기사가 매번
            # 다른 id 를 받는다 — 재실행할수록 중복이 쌓인다. sha1 로 고정한다.
            rid = a.get("uid") or hashlib.sha1(
                f"{t}|{pub.date()}|{title}".encode()).hexdigest()[:16]
            if rid in seen:
                continue
            seen.add(rid)
            # 🔴 `published` 는 **날짜가 아니라 시각까지** 남긴다.
            # 라벨(forward_excess)은 발행일 **종가 진입**을 가정하는데, 장 마감
            # 뒤(16:00 ET 이후) 기사는 기사가 나오기 전 가격으로 들어간 것이
            # 되어 다음날 갭이 공짜 수익으로 들어간다 — **낙관 쪽 편향**이다.
            # 날짜만 저장하면 어느 행이 그런지 **구분조차 못 한다.** 그리고
            # yfinance 는 최근 ~1주일만 주므로 지난 행은 영영 복구가 안 된다
            # (2026-10-27 이전 3,457행이 그렇게 날아갔다).
            # 세션 구분(장전/장중/장후)은 이 값에서 언제든 다시 뽑을 수 있으니
            # 여기서는 **가공하지 않고 원본 그대로** 둔다.
            fresh.append(dict(id=rid, ticker=t, date=pub.date().isoformat(),
                              published=pub.isoformat(),
                              # 자동생성 매체(Zacks·24/7 Wall St.)와 Reuters 를
                              # 가르는 가장 싼 잡음 필터다.
                              publisher=a.get("publisher") or "",
                              kind=a.get("kind") or "",
                              # 한 종목 기사인지 5종목에 걸친 매크로 기사인지.
                              # 개수만 두면 어느 종목이었는지 못 되살린다.
                              rel=a.get("rel") or [],
                              title=title, excess=None,
                              horizon=horizon))
    print(f"[수집] 신규 헤드라인 {len(fresh)}건 (기존 {len(existing)}건)")
    rows = existing + fresh
    if fresh:
        write_rows(rows)
    return label(horizon, rows)


def label(horizon, rows=None):
    """가격이 확보된 행에 라벨을 채운다. 이미 채워진 건 건드리지 않는다."""
    rows = rows if rows is not None else read_rows()
    todo = [r for r in rows if r.get("excess") is None]
    if not todo:
        print("[라벨] 채울 게 없다")
        return 0
    tickers = sorted({r["ticker"] for r in todo})
    print(f"[라벨] {len(todo)}건 · {len(tickers)}종목 가격을 받는다")
    px = yf.download(tickers + [BENCH], period="6mo", interval="1d",
                     progress=False, auto_adjust=True)["Close"]
    if BENCH not in px.columns:
        print("벤치마크를 못 받았다", file=sys.stderr)
        return 1
    bench = px[BENCH]

    filled = pending = 0
    for r in todo:
        d0 = datetime.fromisoformat(r["date"]).date()
        e = forward_excess(px, bench, r["ticker"], d0, horizon)
        if e is None:
            pending += 1
            continue
        r["excess"] = round(e, 4)
        r["horizon"] = horizon
        filled += 1
    write_rows(rows)
    print(f"[라벨] 채움 {filled}건 · 아직 {horizon}거래일이 안 지난 것 {pending}건")
    return 0


def stats():
    rows = read_rows()
    if not rows:
        print("데이터가 없다 — `python collect.py` 를 먼저 돌린다")
        return 0
    done = [r for r in rows if r.get("excess") is not None]
    print(f"[데이터] 전체 {len(rows)}건 · 라벨 완료 {len(done)}건 "
          f"· 대기 {len(rows) - len(done)}건")
    if not done:
        return 0
    d = pd.DataFrame(done)
    d["date"] = pd.to_datetime(d["date"])
    print(f"  기간 {d.date.min().date()} ~ {d.date.max().date()}"
          f" · 종목 {d.ticker.nunique()}개")
    print(f"  초과수익 평균 {d.excess.mean():+.2f}% · 표준편차 {d.excess.std():.2f}%"
          f" · 중앙값 {d.excess.median():+.2f}%")
    q = d.excess.quantile([.33, .67])
    print(f"  3분위 경계: {q.iloc[0]:+.2f}% / {q.iloc[1]:+.2f}%"
          "   ← 학습 때 **훈련셋만으로** 다시 계산한다(누수 방지)")
    print("\n  날짜별:")
    for dt, n in d.groupby(d.date.dt.date).size().items():
        print(f"    {dt}  {n:>4}건  {'█' * min(40, n // 3)}")

    # ── 2026-10-27 부터 붙는 필드 ──────────────────────────────────────────
    # 🔴 **커버리지를 먼저 보여준다.** 그 전 행에는 이 값이 없는데, 그걸 모르고
    # publisher 로 거르면 "오래된 행이 통째로 빠진 것"을 "그 매체가 적은 것"으로
    # 읽게 된다. 몇 건에만 있는지가 숫자보다 먼저 보여야 한다.
    full = [r for r in rows if r.get("published")]
    print(f"\n  [신규필드] 발행시각 보유 {len(full)}/{len(rows)}건"
          f" ({len(full) / len(rows) * 100:.0f}%)")
    if not full:
        print("    아직 없다 — 다음 수집부터 쌓인다")
        return 0

    # 미국 동부 기준 세션. 장후 기사는 발행일 종가 진입이 **미래를 보는 것**이라
    # 라벨이 낙관 쪽으로 샌다(§collect 주석). 몇 건이나 되는지 눈으로 확인한다.
    f = pd.DataFrame(full)
    et = pd.to_datetime(f["published"], utc=True, format="mixed") \
           .dt.tz_convert("America/New_York")
    mins = et.dt.hour * 60 + et.dt.minute
    sess = pd.cut(mins, [-1, 569, 959, 1439],
                  labels=["장전(~9:29)", "장중(9:30~15:59)", "장후(16:00~)"])
    # 🔴 pd.cut 은 위 3개만 범주로 가진 Categorical 을 준다 — "주말" 을 미리
    #   범주에 넣지 않고 where 로 채우면 TypeError 로 --stats 가 통째로 죽는다.
    #   주말 발행 기사가 처음 들어온 2026-11-01 에 실제로 터졌다.
    sess = sess.cat.add_categories("주말").where(et.dt.dayofweek < 5, "주말")
    for k, n in sess.value_counts().items():
        mark = "  🔴 종가진입 가정이 낙관 편향" if k == "장후(16:00~)" else ""
        print(f"    {k:<18}{n:>5}건{mark}")
    top = f[f["publisher"].astype(bool)]["publisher"].value_counts()
    if len(top):
        print(f"    발행처 {len(top)}곳 · 상위: "
              + " · ".join(f"{k}({v})" for k, v in top.head(5).items()))
    nrel = f["rel"].apply(lambda x: len(x) if isinstance(x, list) else 0)
    print(f"    기사당 관련종목 평균 {nrel.mean():.1f}개"
          f" · 1종목 전용 {(nrel <= 1).sum()}건 · 3종목 이상 {(nrel >= 3).sum()}건")
    return 0


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--horizon", type=int, default=DEFAULT_HORIZON)
    p.add_argument("--relabel", action="store_true")
    p.add_argument("--stats", action="store_true")
    a = p.parse_args()
    if a.stats:
        return stats()
    if a.relabel:
        rows = read_rows()
        for r in rows:
            r["excess"] = None
        return label(a.horizon, rows)
    return collect(a.horizon)


if __name__ == "__main__":
    sys.exit(main())
