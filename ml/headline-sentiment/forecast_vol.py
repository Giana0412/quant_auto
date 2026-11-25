#!/usr/bin/env python3
"""헤드라인이 **앞으로의** 변동성을 더 잘 맞히게 해 주는가 — HAR 위 추가분.

── 왜 ──────────────────────────────────────────────────────────────────────
reaction.py(2026-11-10)의 A 는 '그날 반응창'의 크기였다. AUC 0.59 였지만
① 같은 날 가격과 기사가 함께 움직인 걸 잰 **설명**이지 예측이 아니고,
② 이벤트 태그 하나만으로 낸 점수(0.592)를 한 번도 못 넘었다.

여기서는 질문을 예측으로 바꾼다. **d 일 종가 시점에 알 수 있는 것**으로
d+1 ~ d+H 거래일의 실현 변동성을 맞힌다. 이 질문에는 강한 비교 기준이 있다 —
변동성은 뭉쳐 다니므로(volatility clustering) 과거 변동성만으로도 꽤 맞는다.
그 기준이 HAR(Corsi 2009): 어제·지난 5일·지난 20일 변동성의 선형 결합.
**헤드라인은 그 위에 얹었을 때 남는 몫만 인정한다.**

── 단위 ────────────────────────────────────────────────────────────────────
(종목, 세션 d) 패널. 헤드라인이 **없는** 종목-일도 넣는다 — '오늘 기사가 있었다'
자체가 정보인지 보려면 기사 없는 날이 대조군으로 있어야 한다.
  x_d   = 종목 일간수익 − SPY 일간수익 (%)
  정답  = log √(mean x² over d+1..d+H)
  HAR   = log|x_d|, log mean|x| (d-4..d), log mean|x| (d-19..d)
  뉴스  = 기사 수, 이벤트 태그(reaction.EVENTS), 가격묘사 제목 수
  본문  = 그날 기사 제목을 이어 붙여 TF-IDF (종목명 가림 — experiments.mask)
기사는 발행시각 이후 **종가가 처음 오는 세션**에 붙인다(장후 기사는 다음 세션).
발행시각이 없는 옛 행(~10/26)은 쓰지 않는다.

── 🔴 누수 ─────────────────────────────────────────────────────────────────
· 테스트 날짜 D 의 정답은 D+1..D+H. 훈련에는 **정답이 D 종가까지 확정된 행만**
  쓴다(d + H ≤ D) — purge.
· 폴드끼리 정답 창이 H-1 일 겹친다. 그래서 폴드 평균의 t 는 Newey-West(lag H-1)로 낸다.
  보통 t 를 쓰면 같은 움직임을 여러 번 센다.
· TF-IDF 사전·스케일러는 폴드 훈련셋에서만 맞춘다.

실행:
  .venv/bin/python forecast_vol.py              # H=3
  .venv/bin/python forecast_vol.py --h 5 --refresh
"""
import argparse
import collections
import json
from datetime import datetime, time as dtime

import numpy as np
import pandas as pd
import scipy.sparse as sp
from scipy.stats import spearmanr
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import Ridge
from sklearn.preprocessing import StandardScaler

from experiments import ET, RUNS, mask, mentions, rows_all, universe
from reaction import EVENTS, PRICE_WORDS, event_of, ohlc

EV_KEYS = [k for k, _ in EVENTS] + ["기타"]
EPS = 0.05          # %. 하루 |x| 가 0 인 날 log 가 터지지 않게
WARMUP = 8          # 훈련에 쓸 수 있는(purge 후) 세션이 최소 이만큼은 있어야 첫 폴드


def session_of(p, sessions):
    return next((s for s in sessions
                 if s > p.date() or (s == p.date() and p.time() < dtime(16, 0))), None)


def news_by_day(raw, sessions, names, tickers):
    """{(티커, 세션): [행...]} — 발행시각 있는 행만."""
    out = collections.defaultdict(list)
    for r in raw:
        if not r.get("published") or r["ticker"] not in tickers:
            continue
        p = datetime.fromisoformat(r["published"]).astimezone(ET)
        d = session_of(p, sessions)
        if d is None:
            continue
        out[(r["ticker"], d)].append(dict(
            title=mask(r["title"], r["ticker"], names), event=event_of(r["title"]),
            pricey=bool(PRICE_WORDS.search(r["title"])), lead=mentions(r, names)))
    return out


def panel(px, news, h, first):
    C = px["Close"]
    x = C.pct_change(fill_method=None).sub(C["SPY"].pct_change(fill_method=None), axis=0) * 100
    x = x.drop(columns="SPY")
    a = x.abs()
    har = {"a1": np.log(a + EPS),
           "a5": np.log(a.rolling(5, min_periods=4).mean() + EPS),
           "a20": np.log(a.rolling(20, min_periods=15).mean() + EPS)}
    # 정답: d+1..d+h 의 RMS. shift(-h) 로 앞을 본다 — 정답에만 쓴다
    fwd = np.log(np.sqrt((x ** 2).rolling(h, min_periods=h).mean().shift(-h)) + EPS)
    sessions = [s.date() for s in x.index]
    rows = []
    for i, d in enumerate(sessions):
        if d < first:
            continue
        ts = x.index[i]
        for t in x.columns:
            f = [har[k].at[ts, t] for k in ("a1", "a5", "a20")]
            if not np.all(np.isfinite(f)):
                continue
            ns = news.get((t, d), [])
            ev = collections.Counter(n["event"] for n in ns)
            rows.append(dict(
                d=i, date=d.isoformat(), ticker=t, y=float(fwd.at[ts, t]),
                har=f,
                nw=[np.log1p(len(ns)), np.log1p(sum(n["lead"] for n in ns)),
                    np.log1p(sum(n["pricey"] for n in ns))] + [float(ev[k] > 0) for k in EV_KEYS],
                text=" ".join(n["title"] for n in ns), has=bool(ns)))
    return rows, sessions


def nw_t(v, lag):
    """Newey-West t (평균 ≠ 0). 폴드 정답창이 겹쳐 자기상관이 생기므로."""
    v = np.asarray(v, float)
    n = len(v)
    if n < 3:
        return np.nan
    e = v - v.mean()
    s = e @ e / n
    for k in range(1, min(lag, n - 1) + 1):
        s += 2 * (1 - k / (lag + 1)) * (e[k:] @ e[:-k]) / n
    return v.mean() / np.sqrt(s / n) if s > 0 else np.nan


def design(tr, te, use_news, use_text):
    def dense(rs):
        return np.array([r["har"] + (r["nw"] if use_news else []) for r in rs])
    sc = StandardScaler().fit(dense(tr))
    Xtr, Xte = sc.transform(dense(tr)), sc.transform(dense(te))
    if not use_text:
        return Xtr, Xte
    vec = TfidfVectorizer(ngram_range=(1, 2), min_df=3, sublinear_tf=True, max_features=20000)
    vec.fit([r["text"] for r in tr if r["has"]])
    Ttr, Tte = vec.transform([r["text"] for r in tr]), vec.transform([r["text"] for r in te])
    return sp.hstack([Xtr, Ttr]).tocsr(), sp.hstack([Xte, Tte]).tocsr()


MODELS = [("HAR", False, False), ("HAR+뉴스", True, False), ("HAR+뉴스+본문", True, True)]


def walk(rows, sessions, h, alpha):
    test_idx = sorted({r["d"] for r in rows if np.isfinite(r["y"])})
    res = []
    for D in test_idx:
        tr = [r for r in rows if r["d"] + h <= D and np.isfinite(r["y"])]
        if len({r["d"] for r in tr}) < WARMUP:
            continue
        te = [r for r in rows if r["d"] == D and np.isfinite(r["y"])]
        y_te = np.array([r["y"] for r in te])
        has = np.array([r["has"] for r in te])
        out = dict(date=sessions[D].isoformat(), n=len(te), n_news=int(has.sum()),
                   train_days=len({r["d"] for r in tr}))
        for name, un, ut in MODELS:
            Xtr, Xte = design(tr, te, un, ut)
            m = Ridge(alpha=alpha).fit(Xtr, np.array([r["y"] for r in tr]))
            p = m.predict(Xte)
            out[name] = float(spearmanr(p, y_te).statistic)
            out[name + "|뉴스있음"] = float(spearmanr(p[has], y_te[has]).statistic) if has.sum() > 10 else np.nan
            out[name + "|mse"] = float(np.mean((p - y_te) ** 2))
        res.append(out)
    return res


def report(res, h):
    print(f"\n폴드 {len(res)}개 ({res[0]['date']} ~ {res[-1]['date']})  · 폴드당 종목 ~{int(np.mean([r['n'] for r in res]))}"
          f" · 그중 기사 있는 종목 ~{int(np.mean([r['n_news'] for r in res]))}")
    print(f"  t 는 Newey-West(lag {h - 1}) — 정답창이 폴드끼리 겹친다\n")
    summ = {}
    for scope in ("", "|뉴스있음"):
        print("  [전체 종목]" if not scope else "  [그날 기사가 있는 종목만]")
        base = np.array([r["HAR" + scope] for r in res])
        for name, _, _ in MODELS:
            v = np.array([r[name + scope] for r in res])
            ok = np.isfinite(v) & np.isfinite(base)
            s = f"    {name:<14} IC {np.nanmean(v):+.3f} (t={nw_t(v[ok], h - 1):+.2f})"
            if name != "HAR":
                d = v[ok] - base[ok]
                s += f"   HAR 대비 {d.mean():+.4f} (t={nw_t(d, h - 1):+.2f}, {int((d > 0).sum())}/{len(d)}폴드 +)"
                summ[name + scope] = dict(ic=float(np.nanmean(v)), inc=float(d.mean()), inc_t=float(nw_t(d, h - 1)))
            else:
                summ[name + scope] = dict(ic=float(np.nanmean(v)))
            print(s)
    base = np.array([r["HAR|mse"] for r in res])
    print("\n  [예측오차 — log 변동성 MSE, 낮을수록 좋음]")
    for name, _, _ in MODELS:
        v = np.array([r[name + "|mse"] for r in res])
        rel = v.mean() / base.mean() - 1
        print(f"    {name:<14} {v.mean():.4f}" + ("" if name == "HAR" else f"   HAR 대비 {rel:+.1%} (−면 개선)"))
    print("\n  IC 0 = 순위 무관. |t|<2 는 잡음으로 읽는다. 판정은 'HAR 대비' 줄이다.")
    return summ


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--h", type=int, default=3, help="앞으로 몇 거래일의 변동성인가")
    ap.add_argument("--alpha", type=float, default=10.0, help="Ridge 정규화")
    ap.add_argument("--refresh", action="store_true", help="가격 다시 받기")
    a = ap.parse_args()

    raw = rows_all()
    tickers = sorted({r["ticker"] for r in raw})
    px = ohlc(tickers + ["SPY"], a.refresh)
    tickers = [t for t in tickers if t in px["Close"].columns]
    names = universe(False, tickers)
    sessions_all = [s.date() for s in px["Close"]["SPY"].dropna().index]
    news = news_by_day(raw, sessions_all, names, set(tickers))
    first = min(d for _, d in news)
    rows, sessions = panel(px, news, a.h, first)
    last = sessions[-1]
    lab = [r for r in rows if np.isfinite(r["y"])]
    print(f"[데이터] 종목 {len(tickers)} · 세션 {first} ~ {last} · 종목-일 {len(rows)}"
          f" (정답 확정 {len(lab)}) · 기사 있는 종목-일 {sum(r['has'] for r in rows)}")
    print(f"[설정] H={a.h} · Ridge α={a.alpha} · warmup {WARMUP}세션 · purge d+H ≤ 테스트일")

    res = walk(rows, sessions, a.h, a.alpha)
    if not res:
        raise SystemExit("폴드가 없다 — 세션이 모자란다.")
    summ = report(res, a.h)
    tag = datetime.now().strftime("%m%d")
    (RUNS / f"forecast-vol-{tag}-h{a.h}.json").write_text(json.dumps(
        dict(run=datetime.now().isoformat(timespec="minutes"), last_close=str(last), h=a.h,
             alpha=a.alpha, summary=summ, folds=res), ensure_ascii=False, indent=1, default=float))


if __name__ == "__main__":
    main()
