#!/usr/bin/env python3
"""PEAD 를 독립 전략이 아니라 **기존 스크리너 위의 조건**으로 — 스크리너 상위 종목 중 최근
양(+)의 서프라이즈 종목으로 좁히거나 더 실으면 나아지는가.

── 왜 ──────────────────────────────────────────────────────────────────────
pead.py 결론: SUE Q5−Q1 drift20 ≈ +0.65% (2020 이후만), 롱 Q5 손익분기 ~40bp 왕복이라 비용을
다 넣으면 독립 전략으로는 안 된다. 그런데 어차피 스크리너로 종목을 고르고 매매하고 있다면
PEAD 는 **추가 거래 없이** 고를 종목의 순서만 바꾸는 조건이 될 수 있다 — 비용 장벽이 독립
전략과 다르다(이미 내는 회전율 안에서 쓰거나, 회전율을 조금만 늘린다). 그걸 잰다.

── 스크리너를 어떻게 옮겼나 ─────────────────────────────────────────────────
저장소 안의 스크리너는 둘이고, screener_result.csv 를 만드는 코드는 저장소에 **없다**(.gitignore 에
출력만 있다). 그래서 둘 다 과거 데이터로 다시 만든다:

A. market_metrics.screen() [스크리닝] — 코드를 그대로 옮겼다.
   score = e1 ÷ rel_vol^0.5   (info_score, VOL_PENALTY=0.5)
     e1      = 21영업일 누적수익 − 벤치 21영업일 누적수익 (%p)
     rel_vol = (종목 − 벤치) 일간수익의 최근 60일 표준편차 × √252 × 100
   제외: 21일 고저폭 < 5% (MIN_SPAN21 — 인수합병 고정 종목 등), 가격 이력 70일 미만.
   ⚠️ 달라진 것: 벤치를 ACWI → SPY 로 (캐시에 ACWI 가 없고 유니버스가 S&P 500 이다).
      유니버스를 "섹터·스타일 ETF 의 오늘 상위 보유종목" → "그날의 S&P 500 편입 종목"으로
      (ETF 보유종목은 오늘 것만 받을 수 있어 소급 불가 — market_metrics 자체 주석이 그렇게 말한다).
      상위 5~6종목 북 대신 **상위 5분위**(~100종목)를 쓴다 — 6종목이면 잡음이 결과를 덮는다.
   리밸런스: 1개월(21거래일, 대회·e1 창과 같은 길이)과 1주(5거래일) 둘 다.

B. screener_result.csv (미국 실적 후 모멘텀 스크린) — **출력 열에서 역추정**했다.
   2026-11-12 파일 83행: RSI14 60.1~70.0, RVI 50.2~60.0 (둘 다 경계에 딱 붙어 있어 필터로 본다),
   recent_earnings=Y(발표 ≤~10일) 먼저, 그 안에서 ret_5d 내림차순.
   → 통과 조건 RSI14(Wilder) ∈ [60,70] 그리고 RVI(Dorsey, 10일 표준편차·14 Wilder) ∈ [50,60],
     통과 종목 전부 동일가중. 리밸런스 1주(ret_5d 창과 같은 길이).
   ⚠️ 옮기지 못한 것: sigma20(0.68~1.91) 의 정의, 거래대금 하한(최소 $38M — S&P 500 은 거의 다
      넘는다), S&P 400/600 종목(ESAB·RYN 등 — 우리 유니버스는 S&P 500 뿐). 근사다.
   이 스크린은 이미 '최근 발표 여부'를 정렬에 쓴다 → 여기서 묻는 건 "발표 **방향**(SUE)이
   발표 **여부**보다 더 주나"이기도 하다(변형 ④).

── 비교하는 것 (리밸런스 날짜마다 짝지어) ──────────────────────────────────────
① 기준     스크리너 상위 묶음 동일가중
② 한정     ① ∩ PEAD+ (최근 N=10거래일 안 발표 · 직전 90일 SUE 백분위 ≥ 80%, pead.py 의 Q5).
           5종목 미만이면 그 회차는 ①을 그대로 든다(실적 비수기) — 활성 비율을 같이 낸다.
③ 기울임   ① 에서 PEAD+ 종목 비중 2배
④ 발표만   ① ∩ 최근 N 거래일 안 발표(방향 무관) — B 의 recent_earnings 와 같은 대조군
⑤ 제외     ① − PEAD− (최근 N 일 안 발표 · 백분위 < 20%, Q1)
수익 = 보유기간 베타조정 초과수익의 합 (종목 − 직전 250일 β × SPY, pead.py 와 같은 정의)
     = β 만큼 SPY 를 숏했다고 본 수익. 비용 = 편도 c bp × Σ|Δw| (c = 0/10/25). 헤지 SPY 비용은 뺐다.
증분 = (변형 − 기준) 순수익의 리밸런스별 차이 → 평균과 Newey–West t.

── 🔴 미래 정보가 새는 곳과 막은 방법 ────────────────────────────────────────
🔴 신호 시점: 신호는 s = t−1 종가까지, 진입은 t 종가. 같은 종가로 신호를 만들고 체결하지 않는다.
🔴 발표 시각: 반응일 d0 = 09:30 ET 전 발표면 그날, 이후면 다음 세션 (pead.py 와 같다). 시각
   00:00 행은 장전/장후를 알 수 없어 뺀다.
🔴 진입 지연: PEAD 조건이 켜지는 첫 진입일은 d0+1 종가 (t ≥ i0+1). d0 반응 자체는 못 먹는다.
   → 아래 [점검 2] 가 d0·d0+1 수익에 큰 값을 심어도 증분이 0 인지로 확인한다.
🔴 분류: 같은 분기 5분위가 아니라 **그 발표 전 90일(달력)** 발표들 안에서의 SUE 백분위
   (같은 날 발표도 제외, 100건 미만이면 미분류). 극단값 클리핑은 하지 않는다 — pead.py 는 전체 표본
   1/99% 로 자르는데 그 경계 자체가 미래 정보다. 백분위는 단조변환에 불변이라 잃는 게 없다.
🔴 편입: 신호일 s 에 S&P 500 편입 중인 종목만 후보. 나중에 편입될 종목의 편입 전 상승을 빼고,
   2013 이후 편출 종목을 편출일 전까지 넣는다(yfinance 에 가격이 남은 것만).
🔴 베타: 직전 250일, shift(1) — 그날 수익이 그날 베타에 안 들어간다.
🔴 상장폐지: 보유 중 가격이 끊기면 그 뒤 초과수익을 0 으로 둔다 — 상폐 수익(대개 음수)이 빠져
   있어 기준·변형 모두 약간 낙관적이다. 짝지은 증분에는 대부분 상쇄된다.
· 컨센서스(est)는 Yahoo 가 지금 저장해 둔 값이다 — 발표 당시 화면과 다를 수 있다.
· 가중치는 리밸런스 때 동일가중으로 되돌린다고 보고, 보유 중 가격 변화로 인한 비중 표류와 그
  재조정 거래는 회전율에 넣지 않았다(약간 과소).

실행: ../headline-sentiment/.venv/bin/python overlay.py     (runs/*.pkl 캐시만 쓴다 · runs/overlay.txt 에 저장)
"""
from __future__ import annotations

import sys
from datetime import time as dtime
from pathlib import Path

import numpy as np
import pandas as pd

from pead import ET, RUNS, events, member, membership, oos_buckets, pct, spread_by_bucket

N_RECENT = 10            # 발표 후 몇 거래일까지 'PEAD 조건'을 켜 두나 (B 의 recent_earnings ≈ 10일)
POS_PCT, NEG_PCT = 0.8, 0.2
MIN_NAMES = 5            # 한정 포트폴리오 최소 종목 수 — 못 채우면 기준 포트폴리오를 그대로
TOP_Q = 0.8              # 스크린 A 상위 묶음 = 점수 백분위 ≥ 80%
COSTS = (0, 10, 25)      # 편도 bp
START = "2014-01-01"
SPLITS = [("2014–19", "2014", "2020"), ("2020–", "2020", "2100"), ("전체", "2014", "2100")]


# ── 데이터 ────────────────────────────────────────────────────────────────

def load():
    win, sector = membership()
    E = pd.read_pickle(RUNS / "earnings.pkl")
    E = E[E["ticker"].isin(win)]
    # 🔴 pead.prices() 를 쓰지 않는다 — 캐시에 없는 편출 종목(yfinance 에서 사라진 것)이 있으면 매번 전부
    # 다시 받는다. 캐시를 그대로 읽는다.
    C, V = pd.read_pickle(RUNS / "px.pkl")
    sessions = C["SPY"].dropna().index
    C, V = C.loc[sessions], V.loc[sessions]
    return win, sector, E, C, V


def beta_excess(C: pd.DataFrame) -> pd.DataFrame:
    """pead.events 와 같은 식: 종목 − 직전 250일 β(shift 1, 0~3 클립) × SPY."""
    R = C.pct_change(fill_method=None)
    m = R["SPY"]
    cov = R.rolling(250, min_periods=120).cov(m)
    beta = cov.div(m.rolling(250, min_periods=120).var(), axis=0).shift(1).clip(0, 3)
    return R - beta.mul(m, axis=0)


def member_matrix(win: dict, cols, idx) -> np.ndarray:
    M = np.zeros((len(idx), len(cols)), bool)
    d = idx.to_numpy()
    for j, tk in enumerate(cols):
        for a, b in win.get(tk, []):
            lo = 0 if pd.isna(a) else np.searchsorted(d, np.datetime64(a), "left")
            hi = len(d) if pd.isna(b) else np.searchsorted(d, np.datetime64(b), "left")
            M[lo:hi, j] = True
    return M


def event_table(E: pd.DataFrame, C: pd.DataFrame, win: dict) -> pd.DataFrame:
    """발표 → 반응일 인덱스 i0, SUE, 직전 90일 SUE 백분위. pead.events 와 같은 d0 규칙이지만
    🔴 '앞으로 60일 가격이 있어야 한다'는 조건을 걸지 않는다 — 그건 미래 데이터 존재를 조건으로
    거는 것이라 최근 발표가 통째로 빠진다."""
    sessions = C.index
    E = E.dropna(subset=["est", "rep"])
    E = E[E["ticker"].isin(C.columns)].copy()
    ts = pd.to_datetime(E["ts"], utc=True).dt.tz_convert(ET)
    keep = ~((ts.dt.hour == 0) & (ts.dt.minute == 0))
    E, ts = E[keep], ts[keep]
    cols = {c: j for j, c in enumerate(C.columns)}
    Cv = C.to_numpy()
    rows = []
    for tk, est, rep, t in zip(E["ticker"], E["est"], E["rep"], ts):
        i = sessions.searchsorted(pd.Timestamp(t.date()), side="left" if t.time() < dtime(9, 30) else "right")
        if i < 1 or i >= len(sessions) - 1:
            continue
        if not member(win.get(tk, []), sessions[i]):
            continue
        p = Cv[i - 1, cols[tk]]
        if not np.isfinite(p) or p <= 0:
            continue
        rows.append((tk, cols[tk], i, sessions[i], (rep - est) / p))
    D = pd.DataFrame(rows, columns=["ticker", "j", "i0", "d0", "sue"]).sort_values("d0", kind="stable")
    D = D.reset_index(drop=True)
    d, v = D["d0"].to_numpy(), D["sue"].to_numpy()
    lo = np.searchsorted(d, d - np.timedelta64(90, "D"), "left")
    hi = np.searchsorted(d, d, "left")                   # 🔴 같은 날 발표 제외 — 엄격히 이전만
    pr = np.full(len(D), np.nan)
    for k in range(len(D)):
        w = v[lo[k]:hi[k]]
        if len(w) >= 100:
            pr[k] = (w < v[k]).mean()
    D["pct"] = pr
    D["q"] = [f"{x.year}Q{(x.month - 1) // 3 + 1}" for x in D["d0"]]
    return D


def flag_matrices(D: pd.DataFrame, T: int, J: int, n_recent=N_RECENT):
    """[t, j] = 진입일 t 에 켜진 PEAD 정보. 🔴 진입일 t ∈ [i0+1, i0+n] — d0+1 종가가 가장 이른 진입."""
    rec = np.zeros((T, J), bool)
    P = np.full((T, J), np.nan)
    for i0, j, p in zip(D["i0"].to_numpy(), D["j"].to_numpy(), D["pct"].to_numpy()):
        a, z = i0 + 1, min(i0 + n_recent, T - 1)
        if a > z:
            continue
        rec[a:z + 1, j] = True
        P[a:z + 1, j] = p                               # 날짜순이라 겹치면 최신 발표가 덮는다
    return rec, P


# ── 스크린 신호 (전부 '그날 종가까지' — 사용하는 쪽에서 s = t−1 행을 읽는다) ─────────────

def screen_a(C: pd.DataFrame) -> pd.DataFrame:
    """market_metrics.screen() 의 info_score. 고저폭 < 5% · 이력 70일 미만은 NaN."""
    b = C["SPY"]
    e1 = (C / C.shift(21) - 1).sub(b / b.shift(21) - 1, axis=0) * 100
    R = C.pct_change(fill_method=None)
    rel = R.sub(R["SPY"], axis=0)
    rv = rel.rolling(60, min_periods=60).std() * np.sqrt(252) * 100
    span = (C.rolling(21, min_periods=21).max() / C.rolling(21, min_periods=21).min() - 1) * 100
    ok = (span >= 5.0) & (C.rolling(70, min_periods=70).count() >= 70) & (rv > 0)
    return (e1 / rv ** 0.5).where(ok)


def _wilder(x: pd.DataFrame, n=14):
    return x.ewm(alpha=1 / n, adjust=False, min_periods=n).mean()


def screen_b(C: pd.DataFrame) -> pd.DataFrame:
    """screener_result.csv 역추정: RSI14 ∈ [60,70] 그리고 RVI ∈ [50,60] → 통과(1.0) / NaN."""
    dC = C.diff()
    up, dn = _wilder(dC.clip(lower=0)), _wilder((-dC).clip(lower=0))
    rsi = 100 - 100 / (1 + up / dn)
    sd = C.rolling(10, min_periods=10).std()
    u, d = _wilder(sd.where(dC > 0, 0.0).where(dC.notna())), _wilder(sd.where(dC < 0, 0.0).where(dC.notna()))
    rvi = 100 * u / (u + d)
    ok = (rsi >= 60) & (rsi <= 70) & (rvi >= 50) & (rvi <= 60)
    return pd.DataFrame(np.where(ok, 1.0, np.nan), index=C.index, columns=C.columns)


# ── 백테스트 ─────────────────────────────────────────────────────────────────

VARIANTS = ["① 기준", "② 한정 PEAD+", "③ 기울임 ×2", "④ 발표만", "⑤ PEAD− 제외"]


def weights(top: np.ndarray, rec: np.ndarray, p: np.ndarray) -> dict[str, np.ndarray]:
    pos = rec & (p >= POS_PCT)
    neg = rec & (p < NEG_PCT)

    def ew(mask, fallback=None):
        n = mask.sum()
        if n < MIN_NAMES and fallback is not None:
            return fallback, False
        return (mask / n if n else mask * 0.0), True

    base, _ = ew(top)
    w = {"① 기준": (base, False)}
    w["② 한정 PEAD+"] = ew(top & pos, base)
    t = top * (1.0 + pos)
    w["③ 기울임 ×2"] = (t / t.sum() if t.sum() else base, bool((top & pos).any()))
    w["④ 발표만"] = ew(top & rec, base)
    w["⑤ PEAD− 제외"] = ew(top & ~neg, base)
    w["⑤ PEAD− 제외"] = (w["⑤ PEAD− 제외"][0], bool((top & neg).any()))
    return w


def run(score: pd.DataFrame, EXv: np.ndarray, Cv: np.ndarray, M: np.ndarray, rec, P, H: int,
        idx: pd.DatetimeIndex, top_rule: str) -> pd.DataFrame:
    """리밸런스마다 (변형별 총수익, Σ|Δw|, 활성 여부). 진입 t 종가 → t+1..t+H 초과수익 합."""
    T, J = EXv.shape
    cs = np.vstack([np.zeros(J), np.cumsum(np.nan_to_num(EXv), axis=0)])   # cs[k] = Σ_{<k}
    S = score.to_numpy()
    t0 = idx.searchsorted(pd.Timestamp(START))
    prev = {v: np.zeros(J) for v in VARIANTS}
    out = []
    for t in range(max(t0, 252), T - H, H):
        s = t - 1                                                       # 🔴 신호는 전날 종가까지
        elig = M[s] & np.isfinite(S[s]) & np.isfinite(Cv[t])           # 편입(신호일) · 진입일 가격 존재
        if elig.sum() < 20:
            continue
        if top_rule == "quintile":
            sc = np.where(elig, S[s], np.nan)
            top = elig & (sc >= np.nanquantile(sc, TOP_Q))
        else:
            top = elig
        if top.sum() < MIN_NAMES:
            continue
        fwd = cs[t + H + 1] - cs[t + 1]                                 # 일 t+1 … t+H
        row = dict(date=idx[t], n_top=int(top.sum()), n_pos=int((top & rec[t] & (P[t] >= POS_PCT)).sum()))
        for v, (w, act) in weights(top, rec[t], P[t]).items():
            row[f"{v}|g"] = float(w @ fwd)
            row[f"{v}|to"] = float(np.abs(w - prev[v]).sum())
            row[f"{v}|act"] = act
            prev[v] = w
        out.append(row)
    return pd.DataFrame(out).set_index("date")


# ── 통계 ────────────────────────────────────────────────────────────────────

def nw_t(x, lag=None) -> float:
    x = np.asarray(x, float)
    x = x[np.isfinite(x)]
    n = len(x)
    if n < 5 or not x.std():
        return np.nan
    if lag is None:
        lag = int(np.floor(4 * (n / 100) ** (2 / 9)))
    e = x - x.mean()
    s = e @ e / n
    for k in range(1, lag + 1):
        s += 2 * (1 - k / (lag + 1)) * (e[k:] @ e[:-k]) / n
    return x.mean() / np.sqrt(s / n)


def report(res: pd.DataFrame, H: int, title: str, out: list):
    ppy = 252 / H
    print(f"\n[{title}]  리밸런스 {len(res)}회 · 보유 {H}거래일 · 평균 상위묶음 {res['n_top'].mean():.0f}종목"
          f" · 그중 PEAD+ 평균 {res['n_pos'].mean():.1f}종목")
    print("  연수익·샤프는 SPY 대비 베타조정 초과수익 기준. 회전 = 회당 편도 교체율(Σ|Δw|/2).")
    hdr = f"  {'':<14}{'기간':<8}{'활성':>5}{'회전':>6}" + "".join(
        f"{f'연{c}bp':>9}{'샤프':>6}" for c in COSTS) + f"{'증분10bp':>10}{'NW t':>7}{'증분25bp':>10}{'NW t':>7}"
    print(hdr)
    for v in VARIANTS:
        for lab, a, b in SPLITS:
            r = res[(res.index >= a) & (res.index < b)]
            if r.empty:
                continue
            g, to, act = r[f"{v}|g"], r[f"{v}|to"], r[f"{v}|act"]
            cells = ""
            stats = {}
            for c in COSTS:
                net = g - c / 1e4 * to
                ann, sh = net.mean() * ppy, net.mean() / net.std() * np.sqrt(ppy) if net.std() else np.nan
                cells += f"{ann * 100:>+8.2f}%{sh:>6.2f}"
                stats[c] = (ann, sh)
            inc = ""
            if v != "① 기준":
                for c in (10, 25):
                    d = (g - c / 1e4 * to) - (r["① 기준|g"] - c / 1e4 * r["① 기준|to"])
                    inc += f"{d.mean() * ppy * 100:>+9.2f}%{nw_t(d):>+7.2f}"
                    stats[f"inc{c}"] = (d.mean() * ppy, nw_t(d))
            print(f"  {v if lab == SPLITS[0][0] else '':<14}{lab:<8}{act.mean():>5.0%}{to.mean() / 2:>6.0%}"
                  + cells + inc)
            out.append(dict(test=title, variant=v, period=lab, active=act.mean(), turnover=to.mean() / 2, **{
                f"ann{c}": stats[c][0] for c in COSTS}, **{f"sh{c}": stats[c][1] for c in COSTS},
                **{k: val for k, val in stats.items() if isinstance(k, str)}))


# ── 점검 ────────────────────────────────────────────────────────────────────

def check_reproduce(E, C, V, win, sector, D, EX):
    """pead.py 의 알려진 숫자(직전 90일 분류 drift20 Q5−Q1 ≈ +0.65%) 재현."""
    Dp, _, _ = events(E, C, V, win, sector)
    qs = Dp["q"].value_counts()
    Dp = Dp[Dp["q"].isin(qs[qs >= 25].index)]
    _, sp = spread_by_bucket(Dp, oos_buckets(Dp, "sue", "trail90"), ["drift20"])
    print(f"  (a) pead.py 함수 그대로: drift20 Q5−Q1 {pct(sp['drift20'].mean())} ({len(sp)}분기) — 알려진 값 +0.65% (가격 캐시가 2026-11-25 까지로 갱신돼 생긴 소수점 차이)")
    # (b) 이 파일의 이벤트 표(클리핑 없음 · 미래 60일 조건 없음)로 같은 숫자
    X = np.nan_to_num(EX.to_numpy())
    cs = np.vstack([np.zeros(X.shape[1]), np.cumsum(X, axis=0)])
    G = D.dropna(subset=["pct"]).copy()
    G = G[G["i0"] + 20 < len(EX)]
    G["drift20"] = cs[G["i0"] + 21, G["j"]] - cs[G["i0"] + 2, G["j"]]
    G["b"] = np.minimum((G["pct"] * 5).astype(int) + 1, 5)
    G = G[G["q"].isin(Dp["q"].unique())]
    _, sp2 = spread_by_bucket(G, G["b"], ["drift20"])
    print(f"  (b) overlay 이벤트 표:     drift20 Q5−Q1 {pct(sp2['drift20'].mean())} ({len(sp2)}분기)"
          " — SUE 클리핑·'미래 60일 가격 존재' 조건을 뺀 차이")


def main():
    lines = []

    class Tee:
        def write(self, s):
            sys.__stdout__.write(s)
            lines.append(s)

        def flush(self):
            sys.__stdout__.flush()

    sys.stdout = Tee()
    win, sector, E, C, V = load()
    EX = beta_excess(C)
    D = event_table(E, C, win)
    T, J = C.shape
    M = member_matrix(win, C.columns, C.index)
    M[:, list(C.columns).index("SPY")] = False
    rec, P = flag_matrices(D, T, J)
    EXv, Cv = EX.to_numpy(), C.to_numpy()
    print(f"[데이터] S&P 500 (편입 이력 반영, 편출 포함) · 가격 {J - 1}종목 · {C.index[0].date()}~{C.index[-1].date()}")
    print(f"  발표 {len(D):,}건 (직전 90일 백분위 있음 {D['pct'].notna().sum():,}) · PEAD 조건 창 = 반응일+1 ~ +{N_RECENT}거래일")
    print(f"  PEAD+ = 백분위 ≥ {POS_PCT:.0%} · PEAD− = < {NEG_PCT:.0%} · 한정 최소 {MIN_NAMES}종목(못 채우면 기준 그대로)")

    SA, SB = screen_a(C), screen_b(C)
    out = []
    tests = [("A. info_score 상위 5분위 · 월간", SA, 21, "quintile"),
             ("A. info_score 상위 5분위 · 주간", SA, 5, "quintile"),
             ("B. RSI·RVI 통과 전부 · 주간", SB, 5, "all")]
    results = {}
    for title, sc, H, rule in tests:
        res = run(sc, EXv, Cv, M, rec, P, H, C.index, rule)
        results[title] = res
        report(res, H, title, out)

    # ── 점검 ────────────────────────────────────────────────────────────
    print("\n[점검 1. pead.py 재현]")
    check_reproduce(E, C, V, win, sector, D, EX)

    print("\n[점검 2. 심은 신호]  스크린 A 주간 · ② 한정 증분(0bp)의 변화")
    base_res = results["A. info_score 상위 5분위 · 주간"]
    base_inc = base_res["② 한정 PEAD+|g"] - base_res["① 기준|g"]
    pos_ev = D[D["pct"] >= POS_PCT]
    delta = 0.002   # 20bp/일

    def planted(days):
        X = EXv.copy()
        for i0, j in zip(pos_ev["i0"].to_numpy(), pos_ev["j"].to_numpy()):
            for k in days:
                if 0 <= i0 + k < T and np.isfinite(X[i0 + k, j]):
                    X[i0 + k, j] += delta
        r = run(SA, X, Cv, M, rec, P, 5, C.index, "quintile")
        return (r["② 한정 PEAD+|g"] - r["① 기준|g"]) - base_inc, r["② 한정 PEAD+|g"] - base_res["② 한정 PEAD+|g"]

    # (a) 진입 이후(d0+2 … d0+N+H)에 심으면 잡혀야 한다
    lift, _ = planted(range(2, N_RECENT + 6))
    act = base_res["② 한정 PEAD+|act"]
    print(f"  (a) d0+2 이후 +20bp/일 심음 → 활성 회차 증분 변화 평균 {lift[act].mean() * 1e4:+.0f}bp/주"
          f" (보유 5일 × 20bp = 100bp 상한, 기준에도 PEAD+ 가 섞여 그보다 작아야 정상) · NW t {nw_t(lift[act]):+.1f}")
    # (b) d0·d0+1 (진입 전) 에 심으면 0 이어야 한다 — 진입 지연이 지켜지는지
    # 기준(①)은 발표 **전**에 산 종목을 들고 있다가 d0 를 맞을 수 있어 바뀌는 게 정상이다. 진입 지연을
    # 보는 건 ② 가 PEAD 조건으로 담은 회차(활성)의 수익 변화 — 이게 정확히 0 이어야 한다.
    _, leak2 = planted([0, 1])
    print(f"  (b) d0·d0+1 에 +20bp/일 심음 → ② 활성 회차 수익 변화 최대 |{np.abs(leak2[act]).max() * 1e4:.2f}|bp"
          f" (0 이어야 진입 전 수익을 못 먹는다)")
    # (c) 위약: 발표-백분위 짝을 섞으면 증분 t 가 0 근처여야 한다
    ts_ = []
    rng = np.random.default_rng(0)
    for _ in range(20):
        Dsh = D.copy()
        Dsh["pct"] = rng.permutation(D["pct"].to_numpy())
        rec_s, P_s = flag_matrices(Dsh, T, J)
        r = run(SA, EXv, Cv, M, rec_s, P_s, 5, C.index, "quintile")
        ts_.append(nw_t(r["② 한정 PEAD+|g"] - r["① 기준|g"]))
    ts_ = np.array(ts_)
    print(f"  (c) SUE 백분위를 섞은 위약 20회: 증분 NW t 평균 {ts_.mean():+.2f} · |t|>2 {int((np.abs(ts_) > 2).sum())}회")

    print("\n  한계: 스크린 A 는 벤치 SPY·유니버스 S&P 500 으로 바꿨고, B 는 출력 열에서 역추정한 근사다(sigma20 미반영)."
          "\n  상폐 수익 없음(0 처리) · 헤지 SPY 비용 없음 · 비중 표류 재조정 거래 없음 · 컨센서스는 Yahoo 저장값."
          "\n  증분은 변형 4 × 스크린·주기 3 × 기간 2 = 24개를 동시에 본다 — |t|≈2 하나는 우연으로 읽는다.")
    RUNS.mkdir(exist_ok=True)
    pd.DataFrame(out).to_csv(RUNS / "overlay.csv", index=False)
    sys.stdout = sys.__stdout__
    (RUNS / "overlay.txt").write_text("".join(lines))


if __name__ == "__main__":
    main()
