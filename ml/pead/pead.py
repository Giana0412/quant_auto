#!/usr/bin/env python3
"""PEAD — 실적 서프라이즈 뒤에 주가가 같은 방향으로 계속 흐르는가.

── 왜 ──────────────────────────────────────────────────────────────────────
헤드라인 실험(ml/headline-sentiment, 2026-10~11)의 결론: 제목 텍스트는 "실적 기사면 크게
움직인다"만 알고, 방향은 모른다. 방향 정보가 있다면 문장이 아니라 **숫자**(EPS 실제 vs 예상)
쪽이다. 그리고 실적 발표 뒤 며칠~몇 주 동안 서프라이즈 방향으로 초과수익이 이어지는 현상
(post-earnings announcement drift, Bernard & Thomas 1989)은 오래된 이상현상이다.
지금도 남아 있는지, 대형주에서도 그런지를 본다.

헤드라인과 달리 **과거를 소급할 수 있다**: yfinance get_earnings_dates 가 종목당 ~12년
(분기 ~48개)의 예상 EPS·실제 EPS·발표 시각을 준다. 독립 단위는 **실적 시즌(달력 분기)** —
같은 분기 발표들은 같은 시장 국면을 공유하므로 분기 안에서 횡단면 비교하고, 분기끼리
평균·t 를 낸다(Fama–MacBeth 식).

── 정의 ────────────────────────────────────────────────────────────────────
반응일 d0   발표 시각이 09:30 ET 이전이면 그날 세션, 이후(장중·장후)면 다음 세션.
            시각이 00:00 인 행은 모호해서 뺀다(개수는 출력).
SUE         (실제 − 예상) ÷ 발표 전날 종가. 분모를 예상 EPS 로 쓰면 예상치가 0 근처일 때 폭발한다.
EAR         d0 하루 초과수익 = (종목 − SPY), 전날 종가 → d0 종가.
drift(k)    d0+1 종가에 들어가 d0+k 종가까지의 누적 초과수익(일간 초과수익의 합).
            🔴 d0 종가가 아니라 하루 늦게 들어간다 — 발표 시각 오류·장후 체결 불가를 흡수하는 보수적 진입.
분위        분기 안에서 SUE(또는 EAR) 5분위. 스프레드 = Q5 − Q1.

── 한계 (출력에도 적는다) ─────────────────────────────────────────────────────
· 생존 편향: 지금 지수에 있는 종목만 본다(상폐·편출 종목 없음).
· 예상 EPS 는 Yahoo 가 저장한 발표 시점 컨센서스. 분할 조정돼 있다.
· 거래비용·차입비용 없음. 초과수익은 베타 1 가정(종목 − SPY).
· 매출 서프라이즈 이력은 yfinance 에 없다(앞으로 4분기 예상치뿐) → EPS 만.

실행:
  python pead.py                 # S&P 500 (실패하면 헤드라인 유니버스)
  python pead.py --refresh       # 실적·가격 다시 받기
  python pead.py --universe headlines
"""
from __future__ import annotations

import argparse
import json
import pickle
import sys
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, time as dtime
from pathlib import Path
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
RUNS = HERE / "runs"
ET = ZoneInfo("America/New_York")
START = "2013-06-01"
HORIZONS = (5, 20, 60)
HEADLINES = Path("/Users/gyuhyeongkim/orca/projects/quant_auto/personal/10-market/_headlines/headlines.jsonl")


# ── 데이터 ────────────────────────────────────────────────────────────────

WIKI = "https://en.wikipedia.org/w/index.php?title=List_of_S%26P_500_companies"
CHANGES_REV = 1340186477   # 2026-02-24 판. 이후 판에서 '편입·편출 변경' 표가 빠졌다


def _wiki(url):
    import io
    import urllib.request
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (research script)"})
    return pd.read_html(io.StringIO(urllib.request.urlopen(req, timeout=30).read().decode()))


def membership(refresh=False) -> tuple[dict, dict]:
    """({티커: [(편입일|NaT, 편출일|NaT), …]}, {티커: 업종}).

    🔴 지금 종목만 쓰면 두 편향이 생긴다.
      · 편입 전: 나중에 올라서 들어온 종목의 편입 전 서프라이즈 뒤 상승이 미래 정보다 → 편입일 이후만.
      · 생존: 편출된 종목(부진·피인수)이 빠진다 → 2013 이후 편출 종목을 편출일 전까지 넣는다.
    편출 종목의 티커가 나중에 다른 회사로 재사용돼도, 재사용은 편출 뒤라 편출일 컷에서 걸러진다.
    """
    f = RUNS / "membership.pkl"
    if f.exists() and not refresh:
        with open(f, "rb") as fh:
            return pickle.load(fh)
    cur = _wiki(WIKI)[0]
    cur["Symbol"] = cur["Symbol"].str.replace(".", "-", regex=False)
    win = {t: [(pd.to_datetime(d, errors="coerce"), pd.NaT)] for t, d in zip(cur["Symbol"], cur["Date added"])}
    sector = dict(zip(cur["Symbol"], cur["GICS Sector"]))
    ch = _wiki(f"{WIKI}&oldid={CHANGES_REV}")[1]
    ch.columns = ["date", "add", "add_name", "rem", "rem_name", "reason"][:len(ch.columns)]
    ch["date"] = pd.to_datetime(ch["date"], errors="coerce")
    for c in ("add", "rem"):
        ch[c] = ch[c].astype(str).str.strip().str.replace(".", "-", regex=False)
    ch = ch.dropna(subset=["date"]).sort_values("date")
    adds = ch[ch["add"].str.match(r"^[A-Z-]+$")].groupby("add")["date"].apply(list).to_dict()
    for _, r in ch[(ch["date"] >= START) & ch["rem"].str.match(r"^[A-Z-]+$")].iterrows():
        t, d = r["rem"], r["date"]
        before = [x for x in adds.get(t, []) if x < d]
        stint = (max(before) if before else pd.NaT, d)
        if t in win and pd.notna(win[t][0][0]) and win[t][0][0] > d:
            win[t].append(stint)                        # 빠졌다가 다시 들어온 종목
        elif t not in win:
            win[t] = [stint]
            sector[t] = "(편출)"
    RUNS.mkdir(exist_ok=True)
    with open(f, "wb") as fh:
        pickle.dump((win, sector), fh)
    return win, sector


def member(windows, d) -> bool:
    return any((pd.isna(a) or d >= a) and (pd.isna(b) or d < b) for a, b in windows)


def headline_universe() -> list[str]:
    return sorted({json.loads(l)["ticker"] for l in HEADLINES.read_text().splitlines() if l.strip()})


def earnings(tickers, refresh) -> pd.DataFrame:
    f = RUNS / "earnings.pkl"
    have = pd.read_pickle(f) if f.exists() and not refresh else pd.DataFrame()
    todo = [t for t in tickers if have.empty or t not in set(have["ticker"])]
    if todo:
        import yfinance as yf

        def one(t):
            try:
                d = yf.Ticker(t).get_earnings_dates(limit=60)
            except Exception:
                return None
            if d is None or d.empty:
                return None
            d = d.rename(columns={"EPS Estimate": "est", "Reported EPS": "rep", "Surprise(%)": "surp_pct"})
            d = d.reset_index().rename(columns={d.index.name or "Earnings Date": "ts"})
            d["ticker"] = t
            return d[["ticker", "ts", "est", "rep", "surp_pct"]]

        with ThreadPoolExecutor(8) as ex:
            got = [x for x in ex.map(one, todo) if x is not None]
        print(f"[실적] {len(todo)}종목 요청 → {len(got)}종목 받음", file=sys.stderr)
        if got:
            have = pd.concat([have] + got, ignore_index=True) if not have.empty else pd.concat(got, ignore_index=True)
        RUNS.mkdir(exist_ok=True)
        have.to_pickle(f)
    return have[have["ticker"].isin(tickers)]


def prices(tickers, refresh) -> tuple[pd.DataFrame, pd.DataFrame]:
    """(수정종가, 거래량). 거래량은 시장충격 계산(일평균 거래대금)에 쓴다."""
    f = RUNS / "px.pkl"
    # 🔴 받아 봤는데 yfinance 에 없던 티커(편출·상폐로 사라진 것)를 따로 적어 둔다. 안 적으면
    # 그 티커가 캐시에 영영 없으니 `요청 ⊆ 캐시` 검사가 늘 실패해 **매번 전체를 다시 받는다**
    # (2026-11-26 overlay 작업 중 발견 — 25개 편출 종목 때문에 hypo.py 도 매 실행 재다운로드).
    gone_f = RUNS / "px-missing.json"
    gone = set(json.loads(gone_f.read_text())) if gone_f.exists() else set()
    if f.exists() and not refresh:
        c, v = pd.read_pickle(f)
        if set(tickers) <= set(c.columns) | gone:
            return c, v
    import yfinance as yf
    raw = yf.download(sorted(set(tickers) | {"SPY"}), start=START, auto_adjust=True, progress=False,
                      threads=True)
    c, v = raw["Close"], raw["Volume"]
    c.index = v.index = pd.to_datetime(c.index).tz_localize(None)
    c = c.dropna(axis=1, how="all")
    v = v[c.columns]
    RUNS.mkdir(exist_ok=True)
    pd.to_pickle((c, v), f)
    gone_f.write_text(json.dumps(sorted(set(tickers) - set(c.columns))))
    return c, v


# ── 이벤트 표 ──────────────────────────────────────────────────────────────

def events(E: pd.DataFrame, C: pd.DataFrame, V: pd.DataFrame, win: dict | None = None,
           sector: dict | None = None, beta_adj: bool = True) -> tuple[pd.DataFrame, dict, pd.DataFrame]:
    R = C.pct_change(fill_method=None)
    DV = (C * V).rolling(20, min_periods=10).mean().shift(1)      # 직전 20일 평균 거래대금($)
    m = R["SPY"]
    if beta_adj:
        # 직전 250거래일 베타(🔴 shift(1) — 그날 수익률이 베타에 안 들어가게). 고변동 종목이 상승장에서
        # 'SPY 초과'를 공짜로 얻는 효과를 뺀다.
        cov = R.rolling(250, min_periods=120).cov(m)
        beta = cov.div(m.rolling(250, min_periods=120).var(), axis=0).shift(1).clip(0, 3)
        ex = R - beta.mul(m, axis=0)
    else:
        ex = R.sub(m, axis=0)
        beta = pd.DataFrame(1.0, index=R.index, columns=R.columns)
    sessions = C["SPY"].dropna().index
    n_sess = len(sessions)
    info = dict(raw=len(E))
    E = E.dropna(subset=["est", "rep"]).copy()
    info["with_eps"] = len(E)
    ts = pd.to_datetime(E["ts"], utc=True).dt.tz_convert(ET)
    midnight = (ts.dt.hour == 0) & (ts.dt.minute == 0)
    info["midnight_dropped"] = int(midnight.sum())
    E, ts = E[~midnight], ts[~midnight]
    rows, pre_add = [], 0
    for (_, r), t in zip(E.iterrows(), ts):
        day = pd.Timestamp(t.date())
        before_open = t.time() < dtime(9, 30)
        i = sessions.searchsorted(day, side="left" if before_open else "right")
        if i < 2 or i + max(HORIZONS) >= n_sess or r["ticker"] not in C:
            continue
        tk = r["ticker"]
        if win is not None and not member(win.get(tk, []), sessions[i]):
            pre_add += 1
            continue
        p_prev = C[tk].iat[i - 1] if not np.isnan(C[tk].iat[i - 1]) else np.nan
        if not np.isfinite(p_prev) or p_prev <= 0:
            continue
        e = ex[tk].to_numpy()
        span = e[i - 1:i + max(HORIZONS) + 1]
        if np.isnan(span).mean() > 0.1:
            continue
        b0 = beta[tk].iat[i] if tk in beta else np.nan
        rec = dict(ticker=tk, i0=i, d0=sessions[i], sector=(sector or {}).get(tk, "?"),
                   removed=(sector or {}).get(tk) == "(편출)",
                   beta0=float(b0) if np.isfinite(b0) else 1.0,
                   vol20=float(np.nanstd(e[i - 21:i - 1])) if i > 21 else np.nan,
                   adv20=float(DV[tk].iat[i]) if tk in DV else np.nan, q=f"{sessions[i].year}Q{(sessions[i].month - 1) // 3 + 1}",
                   sue=(r["rep"] - r["est"]) / p_prev, surp_pct=r["surp_pct"],
                   pre=e[i - 1], ear=e[i], post1=e[i + 1])
        for k in HORIZONS:
            rec[f"drift{k}"] = np.nansum(e[i + 2:i + k + 1])   # d0+1 종가 진입 → d0+k 종가
        rows.append(rec)
    info["outside_membership"] = pre_add
    D = pd.DataFrame(rows)
    # 극단값: 분할·통화 오류성 SUE 를 1%/99% 로 자른다
    lo, hi = D["sue"].quantile([0.01, 0.99])
    D["sue"] = D["sue"].clip(lo, hi)
    info["events"] = len(D)
    return D, info, ex.loc[sessions]


# ── 검정 ────────────────────────────────────────────────────────────────────

def tstat(x):
    x = np.asarray(x, float)
    x = x[np.isfinite(x)]
    return (x.mean() / (x.std(ddof=1) / np.sqrt(len(x)))) if len(x) > 2 and x.std() else np.nan


def sorts(D: pd.DataFrame, key: str, ys: list[str], min_n=25):
    """분기마다 key 5분위 → 분위별 평균 y. 분기 평균과 Q5−Q1 의 분기간 t."""
    per_q = []
    for q, g in D.groupby("q"):
        if len(g) < min_n:
            continue
        b = pd.qcut(g[key].rank(method="first"), 5, labels=False) + 1
        per_q.append(g.assign(b=b).groupby("b")[ys].mean().assign(q=q))
    P = pd.concat(per_q)
    table = P.groupby(level=0)[ys].mean()
    spread = P[P.index == 5].set_index("q")[ys] - P[P.index == 1].set_index("q")[ys]
    return table, spread


def oos_buckets(D: pd.DataFrame, key: str, mode: str) -> pd.Series:
    """과거 정보만으로 5분위를 매긴다 — 같은 분기 전체로 경계를 잡으면 분기 초 발표가
    분기 말 발표의 서프라이즈를 보고 분류되는 미래 정보가 들어간다.
      prevq   : 직전 분기 발표들의 20/40/60/80% 경계
      trail90 : 그 발표 **전** 90일(달력) 동안의 발표들 안에서의 백분위
    """
    D = D.sort_values("d0")
    b = pd.Series(np.nan, index=D.index)
    if mode == "prevq":
        qs = sorted(D["q"].unique())
        for prev, cur in zip(qs, qs[1:]):
            cut = D.loc[D["q"] == prev, key].quantile([0.2, 0.4, 0.6, 0.8]).to_numpy()
            m = D["q"] == cur
            b[m] = np.searchsorted(cut, D.loc[m, key].to_numpy(), side="right") + 1
    else:
        d = D["d0"].to_numpy()
        v = D[key].to_numpy()
        lo = np.searchsorted(d, d - np.timedelta64(90, "D"), side="left")
        hi = np.searchsorted(d, d, side="left")              # 🔴 같은 날 발표도 제외 — 엄격히 이전만
        for j in range(len(D)):
            w = v[lo[j]:hi[j]]
            if len(w) >= 100:
                pr = (w < v[j]).mean()
                b.iat[j] = min(int(pr * 5) + 1, 5)
    return b


def spread_by_bucket(D: pd.DataFrame, b: pd.Series, ys: list[str], min_n=10):
    """버킷이 주어졌을 때 분기별 버킷 평균 → 표와 Q5−Q1 분기 시계열."""
    G = D.assign(b=b).dropna(subset=["b"])
    per_q = []
    for q, g in G.groupby("q"):
        cnt = g["b"].value_counts()
        if cnt.get(1, 0) < min_n or cnt.get(5, 0) < min_n:
            continue
        per_q.append(g.groupby("b")[ys].mean().assign(q=q, n=g.groupby("b").size()))
    P = pd.concat(per_q)
    table = P.groupby(level=0)[ys + ["n"]].mean()
    spread = P[P.index == 5].set_index("q")[ys] - P[P.index == 1].set_index("q")[ys]
    return table, spread


# ── 거래비용 · 달력시간 포트폴리오 ─────────────────────────────────────────────
#
# 이벤트별 평균(위 표)은 "발표 하나에 얼마"다. 실제로는 실적 시즌에 포지션이 몰리고 비수기엔
# 거의 없다 → 날짜별로 열린 포지션을 동일가중한 포트폴리오(달력시간)로 다시 잰다.
# 진입 d0+1 종가, 보유 d0+2 … d0+H 종가. 베타 헤지(β×SPY 숏)를 가정해 수익은 베타조정 초과수익.
# 비용: 종목 왕복 c bp (진입 c/2, 청산 c/2) + 헤지 SPY 왕복 1bp. 포지션이 MIN_POS 개 미만인 날은 현금(0).

HOLD = 20
MIN_POS = 10
COSTS_BP = (0, 5, 10, 20, 30, 50)


def calendar(D: pd.DataFrame, EX: pd.DataFrame, b: pd.Series, legs: dict[int, float], cost_bp: float,
             hold: int = HOLD, hedge_bp: float = 0.0, borrow_stock: float = 0.0, borrow_spy: float = 0.0,
             capital: float | None = None, impact_y: float = 1.0) -> pd.Series:
    """달력시간 포트폴리오 일간 수익. legs: {버킷: 부호} — 롱 Q5 = {5: +1}, 롱숏 = {5: +1, 1: -1}
    (다리마다 자본 절반). 포지션 비중은 그날 열린 포지션 수로 동일가중, MIN_POS 미만이면 현금.

    비용 (모두 포지션 금액 대비 비율):
      cost_bp       종목 왕복 스프레드 (진입·청산 반씩)
      hedge_bp      SPY 거래 1단위당 비용. 진입·청산 때 β만큼, 그리고 매일 헤지 비율을 맞추느라
                    β·|초과수익| 만큼 거래한다고 본다(가격이 벌어진 만큼 헤지를 다시 맞춘다).
      borrow_stock  공매도 종목 차입비(연). 숏 다리에만.
      borrow_spy    SPY 공매도 차입비(연). 롱 다리의 헤지(β×SPY 숏)에만 — 숏 다리 헤지는 SPY 롱이다.
      capital       총자본($). 주면 제곱근 시장충격 = Y·σ일·√(주문금액 ÷ 일평균 거래대금) 을 진입·청산에.
    """
    T, X = len(EX), EX.to_numpy()
    cols = {c: j for j, c in enumerate(EX.columns)}
    out = np.zeros(T)
    w_leg = 1.0 / len(legs)
    for bk, sign in legs.items():
        g = D[b == bk]
        spans = []
        n_open = np.zeros(T)
        for i0, tk, be, vo, adv in zip(g["i0"].to_numpy(), g["ticker"].to_numpy(), g["beta0"].to_numpy(),
                                       g["vol20"].to_numpy(), g["adv20"].to_numpy()):
            a_, z_ = i0 + 2, min(i0 + hold, T - 1)
            if a_ <= z_:
                spans.append((a_, z_, cols[tk], be, vo, adv))
                n_open[a_:z_ + 1] += 1
        ret_sum, cost = np.zeros(T), np.zeros(T)
        for a_, z_, j, be, vo, adv in spans:
            r = np.nan_to_num(X[a_:z_ + 1, j])
            ret_sum[a_:z_ + 1] += r
            side = cost_bp / 2 / 1e4 + be * hedge_bp / 2 / 1e4
            if capital and np.isfinite(adv) and adv > 0 and np.isfinite(vo):
                for t_ in (a_, z_):
                    q = capital * w_leg / max(n_open[t_], MIN_POS)
                    cost[t_] += min(impact_y * vo * np.sqrt(q / adv), 0.05)
            cost[a_] += side
            cost[z_] += side
            daily = be * hedge_bp / 1e4 * np.abs(r)
            if sign < 0:
                daily = daily + borrow_stock / 252
            else:
                daily = daily + be * borrow_spy / 252
            cost[a_:z_ + 1] += daily
        with np.errstate(invalid="ignore", divide="ignore"):
            leg = np.where(n_open >= MIN_POS, (sign * ret_sum - cost) / n_open, 0.0)
        out += w_leg * leg
    return pd.Series(out, index=EX.index)


def perf(r: pd.Series) -> dict:
    r = r[r.index >= "2014-01-01"]
    inv = (r != 0).mean()
    ann = r.mean() * 252
    vol = r.std() * np.sqrt(252)
    eq = (1 + r).cumprod()
    mdd = (eq / eq.cummax() - 1).min()
    return dict(ann=ann, vol=vol, sharpe=ann / vol if vol else np.nan, mdd=mdd, invested=inv)


def fmb(D: pd.DataFrame, y: str, xs: list[str], min_n=25):
    """분기별 횡단면 회귀(순위를 [-.5,.5]로) → 계수의 분기 평균·t (Fama–MacBeth)."""
    co = []
    for q, g in D.groupby("q"):
        g = g.dropna(subset=[y] + xs)
        if len(g) < min_n:
            continue
        X = np.column_stack([np.ones(len(g))] + [g[x].rank(pct=True).to_numpy() - 0.5 for x in xs])
        b, *_ = np.linalg.lstsq(X, g[y].to_numpy(), rcond=None)
        co.append(b[1:])
    co = np.array(co)
    return {x: (co[:, j].mean(), tstat(co[:, j])) for j, x in enumerate(xs)}, len(co)


def pct(x):
    return f"{x * 100:+.2f}%"


# ── 2020 년부터 생긴 이유 ───────────────────────────────────────────────────────

PERIODS = [("2014–2019", "2014", "2019Q4"), ("2020–2022", "2020", "2022Q4"), ("2023–", "2023", "2099")]
TECH = {"Information Technology", "Communication Services", "Consumer Discretionary"}
MAG7 = {"AAPL", "MSFT", "AMZN", "GOOGL", "GOOG", "META", "NVDA", "TSLA"}


def qspread(G: pd.DataFrame, y="drift20", min_each=3) -> pd.Series:
    """분기별 Q5 평균 − Q1 평균 (버킷 b 는 직전 90일 백분위)."""
    s = {}
    for q, g in G.groupby("q"):
        a, z = g[g["b"] == 5][y], g[g["b"] == 1][y]
        if len(a) >= min_each and len(z) >= min_each:
            s[q] = a.mean() - z.mean()
    return pd.Series(s, dtype=float)


def by_period(sp: pd.Series) -> str:
    cells = []
    for lab, a_, b_ in PERIODS:
        x = sp[(sp.index >= a_) & (sp.index <= b_)]
        cells.append(f"{pct(x.mean()):>8} (t={tstat(x):+5.1f})" if len(x) > 2 else f"{'–':>17}")
    return "  ".join(cells)


def why(D: pd.DataFrame, b: pd.Series, C: pd.DataFrame, out: dict):
    G = D.assign(b=b).dropna(subset=["b"])
    hdr = "  ".join(f"{lab:>17}" for lab, _, _ in PERIODS)
    print("\n[5. 왜 2020년부터인가]  지표 = drift20 Q5−Q1 (직전 90일 분류), 괄호는 분기간 t")
    print(f"  {'':<26}{hdr}")
    rows = {}

    def row(lab, mask):
        sp = qspread(G[mask])
        rows[lab] = {p: float(sp[(sp.index >= a_) & (sp.index <= b_)].mean()) for p, a_, b_ in PERIODS}
        print(f"  {lab:<26}{by_period(sp)}")

    row("전체", G["b"].notna())
    print("  · 업종")
    row("기술·통신·경기소비재", G["sector"].isin(TECH))
    row("그 외 업종", ~G["sector"].isin(TECH) & (G["sector"] != "(편출)"))
    row("매그니피센트 7 제외", ~G["ticker"].isin(MAG7))
    for sec in sorted(set(G["sector"]) - {"?", "(편출)"}):
        n = (G["sector"] == sec).sum()
        if n >= 600:
            row(f"  {sec[:22]}", G["sector"] == sec)
    print("  · 크기 (분기 안 거래대금 3분위)")
    G["size3"] = G.groupby("q")["adv20"].transform(lambda x: pd.qcut(x.rank(method="first"), 3, labels=False))
    for k, lab in [(0, "소형(거래대금 하위)"), (1, "중형"), (2, "대형(거래대금 상위)")]:
        row(lab, G["size3"] == k)
    out["why_rows"] = rows

    # 서프라이즈 자체가 바뀌었나
    print("\n  · 서프라이즈와 즉시 반응의 변화")
    print(f"  {'':<26}{hdr}")
    stats = {}
    for lab, a_, b_ in PERIODS:
        g = G[(G["q"] >= a_) & (G["q"] <= b_)]
        e5, e1 = g[g["b"] == 5], g[g["b"] == 1]
        stats[lab] = dict(beat=float((g["sue"] > 0).mean()), med_abs=float(g["sue"].abs().median() * 1e4),
                          ear_spread=float(e5["ear"].mean() - e1["ear"].mean()),
                          drift_spread=float(e5["drift20"].mean() - e1["drift20"].mean()))
        stats[lab]["ratio"] = stats[lab]["drift_spread"] / stats[lab]["ear_spread"] if stats[lab]["ear_spread"] else np.nan
    for key, lab, f in [("beat", "예상 상회 비율", lambda v: f"{v:.0%}"),
                        ("med_abs", "|SUE| 중앙값 (주가 대비 bp)", lambda v: f"{v:.1f}bp"),
                        ("ear_spread", "발표일 반응 Q5−Q1", pct),
                        ("drift_spread", "20일 drift Q5−Q1 (건수 가중)", pct),
                        ("ratio", "drift ÷ 발표일 반응", lambda v: f"{v:.2f}")]:
        print(f"  {lab:<26}" + "  ".join(f"{f(stats[p][key]):>17}" for p, _, _ in PERIODS))
    out["why_stats"] = stats

    # 시장 국면 — 분기 스프레드가 변동성·시장 수익과 같이 움직이나
    sp = qspread(G)
    spy = C["SPY"].pct_change(fill_method=None)
    qv = spy.groupby(spy.index.to_period("Q")).agg(lambda x: x.std() * np.sqrt(252))
    qr = (1 + spy).groupby(spy.index.to_period("Q")).prod() - 1
    qv.index = qr.index = [str(i) for i in qv.index]
    M = pd.DataFrame({"sp": sp, "vol": qv.reindex(sp.index), "ret": qr.reindex(sp.index)}).dropna()
    post = (M.index >= "2020").astype(float)
    X = np.column_stack([np.ones(len(M)), (M["vol"] - M["vol"].mean()) / M["vol"].std(),
                         (M["ret"] - M["ret"].mean()) / M["ret"].std(), post])
    coef, *_ = np.linalg.lstsq(X, M["sp"].to_numpy(), rcond=None)
    resid = M["sp"].to_numpy() - X @ coef
    se = np.sqrt(np.diag(np.linalg.inv(X.T @ X)) * (resid @ resid) / (len(M) - X.shape[1]))
    print("\n  · 시장 국면 회귀 (분기 스프레드 ~ SPY 변동성 + SPY 수익 + 2020 이후 더미, 변수는 표준화)")
    for nm, c_, s_ in zip(["상수", "SPY 변동성 1σ", "SPY 분기수익 1σ", "2020 이후"], coef, se):
        print(f"    {nm:<16} {pct(c_)}  (t={c_ / s_:+.2f})")
    hv = M["vol"] > M["vol"].median()
    print(f"    고변동 분기 평균 {pct(M.loc[hv, 'sp'].mean())} ({hv.sum()}분기) · 저변동 {pct(M.loc[~hv, 'sp'].mean())}"
          f" ({(~hv).sum()}분기)")
    out["why_regime"] = dict(coef=dict(zip(["const", "vol", "ret", "post2020"], map(float, coef))),
                             t=dict(zip(["const", "vol", "ret", "post2020"], map(float, coef / se))))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--refresh", action="store_true")
    ap.add_argument("--universe", choices=["sp500", "headlines"], default="sp500")
    ap.add_argument("--keep-pre-inclusion", action="store_true", help="편입 기간 무시(편향 비교용)")
    ap.add_argument("--current-only", action="store_true", help="편출 종목 빼기(생존 편향 비교용)")
    ap.add_argument("--no-beta", action="store_true", help="초과수익 = 종목 − SPY (베타 1)")
    a = ap.parse_args()

    win, sector = None, None
    if a.universe == "sp500":
        win, sector = membership(a.refresh)
        if a.current_only:
            win = {t: w for t, w in win.items() if sector.get(t) != "(편출)"}
        tickers = sorted(win)
        uni = ("S&P 500 " + ("현재 종목만" if a.current_only else "현재 + 2013 이후 편출 종목")
               + (", 편입 기간 무시" if a.keep_pre_inclusion else ", 편입 기간 안의 발표만"))
        if a.keep_pre_inclusion:
            win = None
    else:
        tickers, uni = headline_universe(), "헤드라인 유니버스"

    E = earnings(tickers, a.refresh)
    C, V = prices(sorted(set(E["ticker"])), a.refresh)
    D, info, EX = events(E, C, V, win, sector, beta_adj=not a.no_beta)
    qs = D["q"].value_counts()
    D = D[D["q"].isin(qs[qs >= 25].index)]
    ys = ["pre", "ear", "post1"] + [f"drift{k}" for k in HORIZONS]

    print(f"[데이터] {uni} · {D['ticker'].nunique()}종목 · 발표 {len(D):,}건 · 실적 시즌 {D['q'].nunique()}개 "
          f"({D['q'].min()}~{D['q'].max()})")
    print(f"  원자료 {info['raw']:,}행 → EPS 있음 {info['with_eps']:,} → 시각 00:00 제외 {info['midnight_dropped']:,}"
          f" → 편입 기간 밖 제외 {info['outside_membership']:,} → 가격 맞춘 이벤트 {info['events']:,}")
    if sector:
        rem = [t for t, s_ in sector.items() if s_ == "(편출)"]
        got = D[D["removed"]]
        print(f"  편출 종목: 2013 이후 {len(rem)}개 중 실적·가격이 있는 {got['ticker'].nunique()}개 · 이벤트 {len(got):,}건"
              f" ({len(got) / len(D):.1%})")
    print(f"  초과수익 = " + ("종목 − 직전 250일 베타 × SPY" if not a.no_beta else "종목 − SPY (베타 1)"))

    # 0. 반응일 점검 — d0 의 |초과수익|이 앞뒤 날보다 커야 시각 매핑이 맞다
    print("\n[0. 반응일 점검]  평균 |초과수익|  d0−1 {:.2f}% · d0 {:.2f}% · d0+1 {:.2f}%".format(
        D["pre"].abs().mean() * 100, D["ear"].abs().mean() * 100, D["post1"].abs().mean() * 100))

    out = dict(run=datetime.now().isoformat(timespec="minutes"), universe=uni, n=len(D),
               quarters=int(D["q"].nunique()))
    for key, title in [("sue", "1. SUE(EPS 서프라이즈) 5분위"), ("ear", "2. EAR(발표일 주가 반응) 5분위")]:
        table, spread = sorts(D, key, ys)
        print(f"\n[{title}]  분기 안에서 나눠 분기끼리 평균")
        print("  분위   " + "  ".join(f"{c:>8}" for c in ["d0반응", "drift5", "drift20", "drift60"]))
        for b, r in table.iterrows():
            print(f"  Q{b}    " + "  ".join(f"{pct(r[c]):>8}" for c in ["ear", "drift5", "drift20", "drift60"]))
        line = "  Q5−Q1  " + "  ".join(f"{pct(spread[c].mean()):>8}" for c in ["ear", "drift5", "drift20", "drift60"])
        print(line)
        print("  t      " + "  ".join(f"{tstat(spread[c]):>+8.2f}" for c in ["ear", "drift5", "drift20", "drift60"]))
        print("  양수분기 " + "  ".join(f"{(spread[c] > 0).mean():>8.0%}" for c in ["ear", "drift5", "drift20", "drift60"]))
        out[key] = dict(table=table.to_dict(), spread_mean=spread.mean().to_dict(),
                        spread_t={c: tstat(spread[c]) for c in ys},
                        spread_by_q=spread.to_dict())

    # 1b. 경계를 과거만으로 — 실제로 그 시점에 분류할 수 있었나
    out["oos"] = {}
    for mode, lab in [("prevq", "직전 분기 경계"), ("trail90", "직전 90일 백분위")]:
        b = oos_buckets(D, "sue", mode)
        table, spread = spread_by_bucket(D, b, ys)
        print(f"\n[1b. SUE 5분위 · {lab}]  분류에 그 발표 이후 정보를 쓰지 않는다 · {spread.shape[0]}분기")
        print("  분위   " + "  ".join(f"{c:>8}" for c in ["d0반응", "drift5", "drift20", "drift60"]) + "   분기당 건수")
        for k_, r in table.iterrows():
            print(f"  Q{int(k_)}    " + "  ".join(f"{pct(r[c]):>8}" for c in ["ear", "drift5", "drift20", "drift60"])
                  + f"   {r['n']:>6.0f}")
        print("  Q5−Q1  " + "  ".join(f"{pct(spread[c].mean()):>8}" for c in ["ear", "drift5", "drift20", "drift60"]))
        print("  t      " + "  ".join(f"{tstat(spread[c]):>+8.2f}" for c in ["ear", "drift5", "drift20", "drift60"]))
        print("  양수분기 " + "  ".join(f"{(spread[c] > 0).mean():>8.0%}" for c in ["ear", "drift5", "drift20", "drift60"]))
        per = {}
        for plab, a_, b_ in [("2014–2019", "2014", "2019Q4"), ("2020–2022", "2020", "2022Q4"), ("2023–", "2023", "2099")]:
            x = spread[(spread.index >= a_) & (spread.index <= b_)]["drift20"]
            if len(x) > 2:
                per[plab] = dict(n=len(x), mean=float(x.mean()), t=float(tstat(x)))
        print("  drift20 시기별: " + " · ".join(f"{k} {pct(v['mean'])} (t={v['t']:+.2f})" for k, v in per.items()))
        out["oos"][mode] = dict(table=table.to_dict(), spread_mean=spread.mean().to_dict(),
                                spread_t={c: tstat(spread[c]) for c in ys}, by_period=per)

    # 1c. 거래비용 — 직전 90일 백분위(실시간으로 가능한 분류)
    b = oos_buckets(D, "sue", "trail90")
    G = D.assign(b=b).dropna(subset=["b"])
    g5, g1 = G[G["b"] == 5]["drift20"], G[G["b"] == 1]["drift20"]
    print(f"\n[1c. 거래비용]  분류 = 직전 90일 백분위 · 보유 {HOLD}거래일 (d0+1 종가 진입) · 베타 헤지")
    print(f"  이벤트당 총수익: 롱 Q5 {pct(g5.mean())} ({len(g5):,}건) · 롱숏 Q5−Q1 {pct(g5.mean() - g1.mean())}")
    print(f"  손익분기 비용(왕복, 헤지 1bp 포함): 롱 Q5 {(g5.mean() * 1e4 - 1):.0f}bp · "
          f"롱숏 {((g5.mean() - g1.mean()) * 1e4 / 2 - 1):.0f}bp (다리마다)")
    print("\n  달력시간 포트폴리오 (2014~, 열린 포지션 동일가중, 10개 미만이면 현금) — 스프레드만")
    print(f"  {'전략':<10}{'왕복비용':>8}{'연수익':>9}{'연변동':>9}{'샤프':>7}{'최대낙폭':>9}{'투자일':>7}")
    out["costs"] = {}
    for name, legs in [("롱 Q5", {5: +1}), ("롱숏", {5: +1, 1: -1})]:
        for c in COSTS_BP:
            pf = perf(calendar(D, EX, b, legs, c))
            out["costs"][f"{name} {c}bp"] = pf
            print(f"  {name:<10}{c:>6}bp{pct(pf['ann']):>9}{pf['vol'] * 100:>8.1f}%{pf['sharpe']:>7.2f}"
                  f"{pf['mdd'] * 100:>8.1f}%{pf['invested']:>7.0%}")

    # 전체 비용: 스프레드 10bp 에서 하나씩 더한다
    print("\n  [전체 비용] 종목 왕복 10bp 에서 시작해 하나씩 더한다")
    print("    헤지: SPY 1bp/거래단위, 매일 β·|초과수익| 만큼 재조정 · 차입: 종목 연 0.5%, SPY 연 0.25%")
    print("    시장충격: Y·σ일·√(주문 ÷ 20일 평균 거래대금), Y=1 · 주문 = 다리 자본 ÷ 그날 열린 포지션 수")
    steps = [("스프레드 10bp", {}),
             ("+ 헤지 비용", dict(hedge_bp=1)),
             ("+ 차입비", dict(hedge_bp=1, borrow_stock=0.005, borrow_spy=0.0025)),
             ("+ 충격 $1M", dict(hedge_bp=1, borrow_stock=0.005, borrow_spy=0.0025, capital=1e6)),
             ("+ 충격 $10M", dict(hedge_bp=1, borrow_stock=0.005, borrow_spy=0.0025, capital=1e7)),
             ("+ 충격 $100M", dict(hedge_bp=1, borrow_stock=0.005, borrow_spy=0.0025, capital=1e8)),
             ("+ 충격 $1B", dict(hedge_bp=1, borrow_stock=0.005, borrow_spy=0.0025, capital=1e9))]
    print(f"  {'':<16}" + "".join(f"{n:>22}" for n in ["롱 Q5 연수익 · 샤프", "롱숏 연수익 · 샤프"]))
    out["full_costs"] = {}
    for lab, kw in steps:
        cells = []
        for name, legs in [("롱 Q5", {5: +1}), ("롱숏", {5: +1, 1: -1})]:
            pf = perf(calendar(D, EX, b, legs, 10, **kw))
            out["full_costs"][f"{name} {lab}"] = pf
            cells.append(f"{pct(pf['ann']):>13} · {pf['sharpe']:5.2f}")
        print(f"  {lab:<16}" + "".join(f"{c:>22}" for c in cells))

    print("\n  시기별 (롱 Q5, 전체 비용 · 자본 $10M)")
    r = calendar(D, EX, b, {5: +1}, 10, hedge_bp=1, borrow_spy=0.0025, capital=1e7)
    for lab, a_, b_ in [("2014–2019", "2014", "2020"), ("2020–2022", "2020", "2023"), ("2023–", "2023", "2100")]:
        pf = perf(r[(r.index >= a_) & (r.index < b_)])
        print(f"  {lab:<10} 연수익 {pct(pf['ann'])} · 샤프 {pf['sharpe']:.2f} · 최대낙폭 {pf['mdd'] * 100:.1f}%")
        out["full_costs"][f"롱 Q5 $10M {lab}"] = pf

    why(D, b, C, out)

    # 3. SUE 와 EAR 를 같이 — drift 가 서프라이즈 때문인가, 그냥 반응 모멘텀인가
    print("\n[3. 분기별 횡단면 회귀 (Fama–MacBeth)]  설명변수는 분기 안 순위(−0.5~+0.5) → 계수 = 최하위→최상위 차이")
    out["fmb"] = {}
    for k in HORIZONS:
        res, nq = fmb(D, f"drift{k}", ["sue", "ear"])
        print(f"  drift{k:<3} SUE {pct(res['sue'][0])} (t={res['sue'][1]:+.2f})   EAR {pct(res['ear'][0])} (t={res['ear'][1]:+.2f})"
              f"   · {nq}분기")
        out["fmb"][f"drift{k}"] = {x: dict(coef=v[0], t=v[1]) for x, v in res.items()}

    # 4. 시기별 — 이상현상이 알려진 뒤 줄었는가
    print("\n[4. 시기별 SUE Q5−Q1 drift20]")
    _, spread = sorts(D, "sue", ys)
    out["by_period"] = {}
    for lab, a_, b_ in [("2014–2019", "2014", "2019Q4"), ("2020–2022", "2020", "2022Q4"), ("2023–", "2023", "2099")]:
        s = spread[(spread.index >= a_) & (spread.index <= b_)]["drift20"]
        if len(s) > 2:
            print(f"  {lab:<10} {len(s):>2}분기  평균 {pct(s.mean())}  t={tstat(s):+.2f}  양수 {(s > 0).mean():.0%}")
            out["by_period"][lab] = dict(n=len(s), mean=float(s.mean()), t=float(tstat(s)))

    print("\n  한계: 편출 종목은 yfinance 에 이력이 남은 것만(피인수·상폐 종목 상당수는 없다) · EPS 만(매출 없음).")
    print("  drift 는 d0+1 종가 진입. 분기(실적 시즌)가 독립 단위라 |t|<2 는 잡음으로 읽는다.")
    RUNS.mkdir(exist_ok=True)
    tag = ("-preinc" if a.keep_pre_inclusion else "") + ("-nobeta" if a.no_beta else "") + \
        ("-current" if a.current_only else "")
    (RUNS / f"pead{tag}.json").write_text(json.dumps(out, ensure_ascii=False, indent=1, default=float))


if __name__ == "__main__":
    main()
