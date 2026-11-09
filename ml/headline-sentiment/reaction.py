#!/usr/bin/env python3
"""수익률 방향 말고 **다른 질문** 두 개 — 헤드라인에 무슨 정보라도 있는가.

── 왜 ──────────────────────────────────────────────────────────────────────
2026-11-06·08 워크포워드: purge·종목명 가림·주인공 필터를 다 해도 3일 초과수익
방향은 IC≈0, DistilBERT 34.6% vs 다수 33.5%(3승 3패). 방향을 3일 앞까지 맞히는
건 이 데이터 크기로는 안 된다. 그래서 질문을 바꾼다.

A. **중요도(크기)** — 이 기사가 '큰 움직임'을 동반하는가. 방향보다 훨씬 쉬운 문제다.
   · 정답: 반응창 |초과수익| ÷ 그 종목의 직전 20거래일 일간 초과수익 표준편차(z).
     🔴 변동성으로 나누지 않으면 "변동성 큰 종목 이름"을 맞히는 문제가 된다.
   · 날짜 안 상위 1/3 = 큰 움직임(1). AUC 로 본다(기준 0.5).
   · 비교: 규칙 이벤트 태그(실적·M&A·애널리스트·규제…) 하나만으로 낸 점수.
B. **장전 기사의 당일 방향** — 장 시작 전에 나온 기사로 그날 시가→종가 초과수익.
   시가에 읽고 들어갈 수 있으니 **실제로 거래 가능한** 질문이다.
   · 비교(상한): 전일 종가→당일 종가 — 기사가 반영되는 창 전체. 거래는 못 하지만
     여기서도 IC≈0 이면 헤드라인 문장에 방향 정보가 없는 것이다.

── 반응 세션 ────────────────────────────────────────────────────────────────
발행시각 p(ET) 이후 **종가(16:00)가 처음 오는 세션** d. 장후 기사는 다음 세션이다.
  반응창   = d-1 종가 → d 종가   (기사가 반영되는 창 전체; 설명용)
  장전여부 = p 가 d 의 09:30 이전 (주말·전날 장후 포함)
라벨이 진입 세션 안에서 끝나므로 날짜 < 테스트 날짜 로 자르면 purge 가 된다.
발행시각이 없는 옛 행(2026-10-27 이전 일부)은 쓸 수 없다.

실행:
  python reaction.py            # A·B 표
  python reaction.py --refresh  # 가격 다시 받기
"""
import argparse
import collections
import json
import re
from datetime import datetime, time as dtime

import numpy as np
import pandas as pd
from scipy.stats import spearmanr
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import roc_auc_score

from experiments import ET, RUNS, mask, mentions, rows_all, universe

PX2 = RUNS / "px-ohlc.pkl"
WARMUP = 3     # 발행시각이 있는 행은 10/27~ 뿐이라 거래일 9~10일. 6이면 폴드 3개
MIN_PER_DATE = 20
VOL_WIN = 20

# 이벤트 태그 — 순서대로 첫 매치 하나. 🔴 학습 라벨이 아니라 **비교 기준**이다.
EVENTS = [
    ("실적", r"\b(earnings|eps|revenue|sales|quarter(ly)?|q[1-4]|results|beats?|miss(es)?|profit|guidance|outlook|forecast)\b"),
    ("M&A", r"\b(acquir\w*|acquisition|merger|merge|buyout|takeover|deal to buy|to buy|bid for|stake in)\b"),
    ("애널리스트", r"\b(upgrades?|downgrades?|price target|initiat\w*|rating|overweight|underweight|outperform|underperform|neutral|buy rating|sell rating)\b"),
    ("규제·소송", r"\b(fda|sec|lawsuit|sues?|probe|investigation|antitrust|settle\w*|approv\w*|recall|fine[ds]?|doj|ftc)\b"),
    ("자본", r"\b(buyback|repurchase|dividend|offering|split|notes due|debt)\b"),
    ("경영진", r"\b(ceo|cfo|chief executive|resign\w*|steps down|appoint\w*|names .* (ceo|cfo))\b"),
    ("계약·제품", r"\b(contract|launch\w*|partnership|partners with|order|award\w*|unveil\w*|deal)\b"),
]
EVENT_RE = [(k, re.compile(p, re.I)) for k, p in EVENTS]


def event_of(title):
    for k, rx in EVENT_RE:
        if rx.search(title):
            return k
    return "기타"


def ohlc(tickers, refresh):
    if PX2.exists() and not refresh:
        d = pd.read_pickle(PX2)
        if set(tickers) <= set(d["Close"].columns):
            return d
    import yfinance as yf
    # 변동성 창(20거래일) 때문에 헤드라인 시작(10/15)보다 한참 앞에서 받는다
    raw = yf.download(sorted(set(tickers)), start="2026-08-15", interval="1d",
                      progress=False, auto_adjust=True)
    d = {"Open": raw["Open"], "Close": raw["Close"]}
    RUNS.mkdir(exist_ok=True)
    pd.to_pickle(d, PX2)
    return d


def build(raw, px, names, only_mention=True):
    O, C = px["Open"], px["Close"]
    spy_c, spy_o = C["SPY"].dropna(), O["SPY"].dropna()
    sessions = list(spy_c.index.date)
    pos = {s: i for i, s in enumerate(sessions)}
    ret = C.pct_change(fill_method=None).sub(C["SPY"].pct_change(fill_method=None), axis=0) * 100
    vol = ret.rolling(VOL_WIN, min_periods=15).std().shift(1)   # 🔴 그날 전까지만
    out = []
    for r in raw:
        if not r.get("published") or r["ticker"] not in C.columns:
            continue
        if only_mention and not mentions(r, names):
            continue
        p = datetime.fromisoformat(r["published"]).astimezone(ET)
        d = next((s for s in sessions
                  if s > p.date() or (s == p.date() and p.time() < dtime(16, 0))), None)
        if d is None or pos[d] == 0:
            continue
        i = pos[d]
        ts, tp = pd.Timestamp(d), pd.Timestamp(sessions[i - 1])
        t = r["ticker"]
        try:
            c0, c1, o1 = C.at[tp, t], C.at[ts, t], O.at[ts, t]
            v = vol.at[ts, t]
        except KeyError:
            continue
        if not all(np.isfinite([c0, c1, o1])):
            continue
        react = (c1 / c0 - spy_c[ts] / spy_c[tp]) * 100
        intraday = (c1 / o1 - spy_c[ts] / spy_o[ts]) * 100
        pre = p < datetime.combine(d, dtime(9, 30), tzinfo=ET)
        out.append(dict(date=d.isoformat(), ticker=t, title=mask(r["title"], t, names),
                        raw_title=r["title"], event=event_of(r["title"]), pre=pre,
                        react=float(react), intraday=float(intraday),
                        z=float(abs(react) / v) if np.isfinite(v) and v > 0 else np.nan))
    return out


def thin(rows):
    c = collections.Counter(r["date"] for r in rows)
    return [r for r in rows if c[r["date"]] >= MIN_PER_DATE]


def xs_label(rows, key, kind):
    byd = collections.defaultdict(list)
    for r in rows:
        byd[r["date"]].append(r)
    for rs in byd.values():
        v = np.array([r[key] for r in rs])
        lo, hi = np.quantile(v, [1 / 3, 2 / 3])
        for r, x in zip(rs, v):
            r["y"] = int(x >= hi) if kind == "big" else (0 if x <= lo else (2 if x >= hi else 1))


def walk(rows, key, kind):
    """확장창 워크포워드. kind='big' → AUC, kind='dir' → IC."""
    rows = thin(rows)
    xs_label(rows, key, kind)
    dates = sorted({r["date"] for r in rows})
    res = []
    for i in range(WARMUP, len(dates)):
        tr = [r for r in rows if r["date"] < dates[i]]
        te = [r for r in rows if r["date"] == dates[i]]
        vec = TfidfVectorizer(ngram_range=(1, 2), min_df=2, sublinear_tf=True)
        Xtr, Xte = vec.fit_transform([r["title"] for r in tr]), vec.transform([r["title"] for r in te])
        ytr, yte = np.array([r["y"] for r in tr]), np.array([r["y"] for r in te])
        clf = LogisticRegression(C=0.5, max_iter=2000, class_weight="balanced").fit(Xtr, ytr)
        P = clf.predict_proba(Xte)
        cls = list(clf.classes_)
        if kind == "big":
            s = P[:, cls.index(1)]
            # 비교: 이벤트 태그만 — 훈련셋에서 태그별 '큰 움직임' 비율을 점수로
            rate = collections.defaultdict(list)
            for r in tr:
                rate[r["event"]].append(r["y"])
            base = np.mean(ytr)
            ev = np.array([np.mean(rate[r["event"]]) if rate[r["event"]] else base for r in te])
            if len(set(yte)) < 2:
                continue
            res.append(dict(date=dates[i], n=len(te), m=roc_auc_score(yte, s),
                            b=roc_auc_score(yte, ev) if ev.std() else 0.5))
        else:
            s = P[:, cls.index(2)] - P[:, cls.index(0)]
            ex = np.array([r[key] for r in te])
            res.append(dict(date=dates[i], n=len(te), m=float(spearmanr(s, ex).statistic), b=np.nan))
    return res, len(rows), len(dates)


def line(name, res, n, nd, kind):
    if not res:
        print(f"  {name:<26} {n:>5}건 {nd:>2}일  폴드 0")
        return {}
    m = np.array([r["m"] for r in res])
    t = (m.mean() - (0.5 if kind == "big" else 0)) / (m.std(ddof=1) / np.sqrt(len(m))) if len(m) > 1 else np.nan
    s = (f"  {name:<26} {n:>5}건 {nd:>2}일 폴드{len(res):>2}  "
         + (f"AUC {m.mean():.3f} (t={t:+.2f}, {sum(m > .5)}/{len(m)}폴드 >0.5)" if kind == "big"
            else f"IC {m.mean():+.3f} (t={t:+.2f}, {sum(m > 0)}/{len(m)}폴드 >0)"))
    if kind == "big":
        b = np.array([r["b"] for r in res])
        s += f"  | 이벤트태그만 AUC {b.mean():.3f}"
    print(s)
    return dict(name=name, rows=n, dates=nd, folds=len(res), mean=float(m.mean()), t=float(t),
                folds_detail=res)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--refresh", action="store_true")
    a = ap.parse_args()
    raw = rows_all()
    tickers = sorted({r["ticker"] for r in raw}) + ["SPY"]
    px = ohlc(tickers, a.refresh)
    names = universe(False, tickers[:-1])
    rows = build(raw, px, names)
    last = px["Close"]["SPY"].dropna().index[-1].date()
    print(f"[데이터] 발행시각 있고 주인공인 기사 {len(rows)}건 · 마지막 종가 {last}"
          f" · 장전 {sum(r['pre'] for r in rows)}건")

    # 이벤트별 기술통계 — 학습 없이 '태그가 큰 움직임과 붙어 있나'
    print("\n[이벤트 태그별 반응 크기]  z = |반응창 초과수익| ÷ 직전 20일 변동성")
    zs = [r for r in rows if np.isfinite(r["z"])]
    allz = np.median([r["z"] for r in zs])
    by = collections.defaultdict(list)
    for r in zs:
        by[r["event"]].append(r)
    for k in [e for e, _ in EVENTS] + ["기타"]:
        g = by.get(k, [])
        if g:
            z = np.array([r["z"] for r in g])
            print(f"  {k:<8} {len(g):>5}건  z 중앙값 {np.median(z):.2f}  z>2 비율 {np.mean(z > 2):5.1%}"
                  f"  평균 반응 {np.mean([r['react'] for r in g]):+.2f}%")
    print(f"  {'전체':<8} {len(zs):>5}건  z 중앙값 {allz:.2f}  z>2 비율 {np.mean([r['z'] > 2 for r in zs]):5.1%}")

    out = {}
    print("\n[A. 중요도 — 큰 움직임(날짜 안 상위 1/3 z) 맞히기]")
    out["A"] = line("전체 기사", *walk([dict(r) for r in zs], "z", "big"), "big")
    out["A_pre"] = line("장전 기사만", *walk([dict(r) for r in zs if r["pre"]], "z", "big"), "big")

    print("\n[B. 방향 — 날짜 안 3분위]")
    pre = [r for r in rows if r["pre"]]
    out["B_trade"] = line("장전 → 시가~종가 (거래가능)", *walk([dict(r) for r in pre], "intraday", "dir"), "dir")
    out["B_react_pre"] = line("장전 → 전일종가~종가 (상한)", *walk([dict(r) for r in pre], "react", "dir"), "dir")
    out["B_react_all"] = line("전체 → 반응창 (상한)", *walk([dict(r) for r in rows], "react", "dir"), "dir")

    print("\n  AUC 0.5 = 무작위. IC 0 = 무관. 폴드(=거래일)가 10개 안팎이라 |t|<2 는 잡음으로 읽는다.")
    (RUNS / "reaction.json").write_text(json.dumps(
        dict(run=datetime.now().isoformat(timespec="minutes"), last_close=str(last), **out),
        ensure_ascii=False, indent=1, default=float))


if __name__ == "__main__":
    main()
