#!/usr/bin/env python3
"""2020년부터 PEAD 가 생긴 이유 — 세 가설을 가진 데이터로 검정한다.

pead.py 결과: 발표일 반응(Q5−Q1 ~4%)은 그대로인데 이후 20일 drift 가 2014–19 +0.06% → 2020 이후
+0.9~1.0%. 업종·소형주·시장 변동성으로는 설명되지 않았다. 남은 가설과 여기서 쓰는 증거:

H1 개인 투자자(수수료 0 · 2020 유입)
   a. 시점: 분기 스프레드가 '계단'(2019Q4~2020Q2 근처에서 한 번에)인가 '추세'인가.
   b. 주의 분산: 같은 날 발표가 많을 때·금요일 발표에서 drift 가 더 큰가 (Hirshleifer–Lim–Teoh 2009).
      개인 유입이 주의 제약을 키웠다면 2020 이후 이 차이가 커져야 한다.
   c. 개인이 몰린 종목: 2020–21 주식 수 거래량이 2017–19 대비 가장 많이 늘어난 종목(사후 분류,
      거래 신호 아님)에서 drift 가 더 커졌나.
H2 패시브 비중
   a. 시점: 패시브 비중은 2014→2024 꾸준히 늘었다 → 스프레드가 선형 추세를 따라야 한다.
   b. 지수 동조: 발표 전 250일 SPY 와의 R²(가격 동조성)가 높은 종목 — 개별 정보보다 지수 흐름으로
      가격이 정해지는 종목 — 에서 drift 가 더 커졌나.
H3 애널리스트가 예상치를 천천히 올림
   a. 서프라이즈 지속성: 이번 분기 SUE 가 다음 분기 SUE 를 얼마나 예측하나(예상치 과소 조정의 직접 흔적).
   b. 다음 발표일 반응: 이번 SUE 5분위가 다음 발표일 반응(EAR)을 예측하나 (Bernard–Thomas 1990).
   c. 2020 이후 위 두 값이 커졌나.
   yfinance 엔 예상치 '수정 이력'이 없어서 수정 속도를 직접 볼 수는 없다 — 그 결과물(지속성)로 본다.

실행: ../headline-sentiment/.venv/bin/python hypo.py   (pead.py 캐시 runs/*.pkl 을 쓴다)
"""
from __future__ import annotations

import json

import numpy as np
import pandas as pd

from pead import (PERIODS, RUNS, by_period, events, membership, oos_buckets, pct, prices,
                  qspread, tstat)


def ols(y, X):
    coef, *_ = np.linalg.lstsq(X, y, rcond=None)
    r = y - X @ coef
    s2 = r @ r / (len(y) - X.shape[1])
    se = np.sqrt(np.diag(np.linalg.inv(X.T @ X)) * s2)
    return coef, coef / se, r @ r


def period_of(q: str) -> str | None:
    for lab, a_, b_ in PERIODS:
        if a_ <= q <= b_:
            return lab
    return None


def main():
    win, sector = membership()
    E = pd.read_pickle(RUNS / "earnings.pkl")          # 캐시만 — earnings() 는 이력 없는 편출 종목을 매번 다시 묻는다
    E = E[E["ticker"].isin(win)]
    C, V = prices(sorted(set(E["ticker"])), False)
    D, _, _ = events(E, C, V, win, sector)
    qs = D["q"].value_counts()
    D = D[D["q"].isin(qs[qs >= 25].index)].copy()
    D["b"] = oos_buckets(D, "sue", "trail90")
    D = D.dropna(subset=["b"]).copy()
    out = {}
    hdr = "  ".join(f"{lab:>17}" for lab, _, _ in PERIODS)

    # ── 이벤트별 추가 변수 ──
    R = C.pct_change(fill_method=None)
    m = R["SPY"]
    r2 = (R.rolling(250, min_periods=120).corr(m) ** 2).shift(1)
    sessions = C["SPY"].dropna().index
    r2 = r2.reindex(sessions)
    Vs = V.reindex(sessions)
    vavg = Vs.rolling(20, min_periods=10).mean().shift(1)
    cols = {c: j for j, c in enumerate(C.columns)}
    r2a, va, vb = r2.to_numpy(), Vs.to_numpy(), vavg.to_numpy()
    j = D["ticker"].map(cols).to_numpy()
    i = D["i0"].to_numpy()
    D["r2"] = r2a[i, j]
    D["abvol"] = va[i, j] / vb[i, j]
    D["busy"] = D.groupby("d0")["ticker"].transform("size")       # 같은 반응일 발표 수
    D["fri"] = pd.to_datetime(D["d0"]).dt.dayofweek == 4          # 반응일 금요일 ≈ 목요일 장후 발표
    # 개인 유입 대리변수: 주식 수 거래량 2020-03~2021-12 평균 ÷ 2017–2019 평균
    pre = Vs.loc["2017":"2019"].mean()
    post = Vs.loc["2020-03":"2021-12"].mean()
    vg = np.log(post / pre).replace([np.inf, -np.inf], np.nan)
    D["vgrow"] = D["ticker"].map(vg)

    # ── 다음 분기 ──
    D = D.sort_values(["ticker", "d0"])
    nx = D.groupby("ticker")[["sue", "ear", "d0"]].shift(-1)
    gap = (nx["d0"] - D["d0"]).dt.days
    ok = gap.between(45, 135)
    D["sue_next"] = nx["sue"].where(ok)
    D["ear_next"] = nx["ear"].where(ok)

    # ══ H1a / H2a. 시점: 계단인가 추세인가 ══
    sp = qspread(D).sort_index()
    t = np.arange(len(sp), dtype=float)
    y = sp.to_numpy()
    print(f"[시점] 분기 drift20 Q5−Q1 {len(sp)}분기 ({sp.index[0]}~{sp.index[-1]})")
    one = np.ones(len(y))
    step = (sp.index >= "2020").astype(float)
    models = {"상수만": np.column_stack([one]),
              "선형 추세 (패시브형)": np.column_stack([one, t]),
              "2020 계단 (개인 유입형)": np.column_stack([one, step]),
              "추세 + 계단": np.column_stack([one, t, step])}
    res = {}
    for nm, X in models.items():
        coef, tt, ssr = ols(y, X)
        n, k = len(y), X.shape[1]
        bic = n * np.log(ssr / n) + k * np.log(n)
        res[nm] = dict(bic=float(bic), coef=coef.tolist(), t=tt.tolist())
        extra = ""
        if nm == "선형 추세 (패시브형)":
            extra = f"  기울기 {pct(coef[1] * 4)}/년 (t={tt[1]:+.2f})"
        if nm == "2020 계단 (개인 유입형)":
            extra = f"  계단 {pct(coef[1])} (t={tt[1]:+.2f})"
        if nm == "추세 + 계단":
            extra = f"  기울기 {pct(coef[1] * 4)}/년 (t={tt[1]:+.2f}) · 계단 {pct(coef[2])} (t={tt[2]:+.2f})"
        print(f"  {nm:<22} BIC {bic:7.1f}{extra}")
    # 단절 시점 찾기: 어느 분기에 계단을 두면 가장 잘 맞나
    cand = [q for q in sp.index if "2016" <= q <= "2023Q4"]
    ssr_k = {}
    for q in cand:
        s_ = (sp.index >= q).astype(float)
        ssr_k[q] = ols(y, np.column_stack([one, s_]))[2]
    best = min(ssr_k, key=ssr_k.get)
    ranked = sorted(ssr_k, key=ssr_k.get)[:5]
    print(f"  계단 위치 탐색: 가장 잘 맞는 분기 {best} · 상위 5개 {', '.join(ranked)}")
    # 누적합으로 꺾이는 곳 보기 (연도별 평균)
    yr = sp.groupby(sp.index.str[:4]).mean()
    print("  연도별 평균: " + " · ".join(f"{k} {pct(v)}" for k, v in yr.items()))
    out["timing"] = dict(models=res, best_break=best, top5=ranked, by_year=yr.to_dict())

    def row(lab, mask, store):
        s_ = qspread(D[mask])
        store[lab] = {p: float(s_[(s_.index >= a_) & (s_.index <= b_)].mean()) for p, a_, b_ in PERIODS}
        print(f"  {lab:<28}{by_period(s_)}")
        return s_

    def diff_row(lab, s_hi, s_lo, store):
        d_ = (s_hi - s_lo).dropna()
        store[lab] = {p: dict(mean=float(d_[(d_.index >= a_) & (d_.index <= b_)].mean()),
                              t=float(tstat(d_[(d_.index >= a_) & (d_.index <= b_)]))) for p, a_, b_ in PERIODS}
        print(f"  {lab:<28}{by_period(d_)}")
        post_ = d_[d_.index >= "2020"]
        pre_ = d_[d_.index < "2020"]
        dd = post_.mean() - pre_.mean()
        se = np.sqrt(post_.var(ddof=1) / len(post_) + pre_.var(ddof=1) / len(pre_))
        print(f"  {'  └ 2020 이후 − 이전':<28}{pct(dd):>8} (t={dd / se:+.1f})")
        store[lab]["post_minus_pre"] = dict(mean=float(dd), t=float(dd / se))

    # ══ H1b. 주의 분산 ══
    print(f"\n[H1b 주의 분산]  지표 = drift20 Q5−Q1, 괄호는 분기간 t\n  {'':<28}{hdr}")
    st = {}
    D["busy3"] = D.groupby("q")["busy"].transform(lambda x: pd.qcut(x.rank(method="first"), 3, labels=False))
    s_hi = row("발표 몰린 날 (분기 내 상위 1/3)", D["busy3"] == 2, st)
    s_lo = row("한산한 날 (하위 1/3)", D["busy3"] == 0, st)
    diff_row("몰린 날 − 한산한 날", s_hi, s_lo, st)
    s_f = row("금요일 반응", D["fri"], st)
    s_nf = row("월~목 반응", ~D["fri"], st)
    diff_row("금요일 − 월~목", s_f, s_nf, st)
    D["abv3"] = D.groupby("q")["abvol"].transform(lambda x: pd.qcut(x.rank(method="first"), 3, labels=False))
    s_lv = row("발표일 거래량 급증 적음", D["abv3"] == 0, st)
    s_hv = row("발표일 거래량 급증 많음", D["abv3"] == 2, st)
    diff_row("관심 적음 − 많음", s_lv, s_hv, st)
    out["H1b"] = st

    # ══ H1c. 개인이 몰린 종목 ══
    print(f"\n[H1c 개인 유입 종목]  2020-03~21 거래량 ÷ 2017–19 (종목 3분위, 사후 분류)\n  {'':<28}{hdr}")
    st = {}
    vq = pd.qcut(vg.dropna().rank(method="first"), 3, labels=False)
    D["vg3"] = D["ticker"].map(vq)
    print(f"  거래량 증가 중앙값: 하위 {np.exp(vg[vq[vq == 0].index].median()):.2f}배 · "
          f"상위 {np.exp(vg[vq[vq == 2].index].median()):.2f}배")
    s_hi = row("거래량 많이 는 종목", D["vg3"] == 2, st)
    s_lo = row("거래량 덜 는 종목", D["vg3"] == 0, st)
    diff_row("많이 − 덜", s_hi, s_lo, st)
    out["H1c"] = st

    # ══ H2b. 지수 동조성 ══
    print(f"\n[H2b 지수 동조성]  발표 전 250일 SPY R² (분기 내 3분위)\n  {'':<28}{hdr}")
    st = {}
    D["r23"] = D.groupby("q")["r2"].transform(lambda x: pd.qcut(x.rank(method="first"), 3, labels=False))
    med = D.groupby(D["q"].map(period_of))["r2"].median()
    print("  R² 중앙값: " + " · ".join(f"{k} {v:.2f}" for k, v in med.items()))
    s_hi = row("R² 높음 (지수 따라 움직임)", D["r23"] == 2, st)
    s_lo = row("R² 낮음 (개별 움직임)", D["r23"] == 0, st)
    diff_row("높음 − 낮음", s_hi, s_lo, st)
    out["H2b"] = st

    # ══ H3. 서프라이즈 지속성 ══
    print("\n[H3 서프라이즈 지속성]  다음 분기 같은 종목 발표 (45~135일 뒤)")
    print(f"  {'':<34}{hdr}")
    st = {}
    H = D.dropna(subset=["sue_next"])
    rho, beat_beat, beat_miss, nxt_ear = {}, {}, {}, {}
    for q, g in H.groupby("q"):
        if len(g) < 50:
            continue
        rho[q] = g["sue"].rank().corr(g["sue_next"].rank())
        nb = g["sue_next"] > 0
        beat_beat[q] = nb[g["sue"] > 0].mean()
        beat_miss[q] = nb[g["sue"] < 0].mean() if (g["sue"] < 0).sum() >= 5 else np.nan
        a, z = g[g["b"] == 5]["ear_next"], g[g["b"] == 1]["ear_next"]
        if len(a) >= 3 and len(z) >= 3:
            nxt_ear[q] = a.mean() - z.mean()
    series = {"SUE 순위상관 (이번→다음)": (pd.Series(rho), lambda v: f"{v:+.3f}"),
              "이번 상회 → 다음도 상회": (pd.Series(beat_beat), lambda v: f"{v:.0%}"),
              "이번 하회 → 다음은 상회": (pd.Series(beat_miss), lambda v: f"{v:.0%}"),
              "다음 발표일 반응 Q5−Q1": (pd.Series(nxt_ear), pct)}
    for lab, (s_, f) in series.items():
        cells = []
        st[lab] = {}
        for p, a_, b_ in PERIODS:
            x = s_[(s_.index >= a_) & (s_.index <= b_)].dropna()
            st[lab][p] = dict(mean=float(x.mean()), t=float(tstat(x)), n=len(x))
            cells.append(f"{f(x.mean()):>8} (t={tstat(x):+5.1f})")
        print(f"  {lab:<34}" + "  ".join(cells))
    for lab, (s_, f) in series.items():
        s_ = s_.dropna()
        post_, pre_ = s_[s_.index >= "2020"], s_[s_.index < "2020"]
        dd = post_.mean() - pre_.mean()
        se = np.sqrt(post_.var(ddof=1) / len(post_) + pre_.var(ddof=1) / len(pre_))
        print(f"  {'└ ' + lab + ' 2020 이후−이전':<34}{f(dd):>8} (t={dd / se:+.1f})")
        st[lab]["post_minus_pre"] = dict(mean=float(dd), t=float(dd / se))

    # 지속성이 drift 를 설명하나: 지속성 큰 종목(과거 4분기 SUE 자기상관 대신, 다음 SUE 같은 부호)에서 drift
    print("\n  · drift 가 '다음 서프라이즈를 미리 반영'하는가 (사후 분해, 거래 신호 아님)")
    print(f"  {'':<34}{hdr}")
    s_same = qspread(H[np.sign(H["sue_next"]) == np.sign(H["sue"])])
    s_flip = qspread(H[np.sign(H["sue_next"]) != np.sign(H["sue"])])
    print(f"  {'다음 분기도 같은 방향':<34}{by_period(s_same)}")
    print(f"  {'다음 분기 방향 바뀜':<34}{by_period(s_flip)}")
    # drift20 를 다음 SUE 로 설명: 분기별 횡단면 회귀 drift20 ~ rank(sue) + rank(sue_next)
    co = {}
    for q, g in H.groupby("q"):
        if len(g) < 50:
            continue
        X = np.column_stack([np.ones(len(g)), g["sue"].rank(pct=True) - .5, g["sue_next"].rank(pct=True) - .5])
        b_, *_ = np.linalg.lstsq(X, g["drift20"].to_numpy(), rcond=None)
        b1, *_ = np.linalg.lstsq(X[:, :2], g["drift20"].to_numpy(), rcond=None)
        co[q] = (b1[1], b_[1], b_[2])
    co = pd.DataFrame(co, index=["sue_only", "sue_ctrl", "sue_next"]).T
    print(f"\n  · 분기별 회귀 drift20 ~ 순위(이번 SUE) [+ 순위(다음 SUE)]  계수 = 최하위→최상위 차이")
    print(f"  {'':<34}{hdr}")
    for c, lab in [("sue_only", "이번 SUE 만"), ("sue_ctrl", "이번 SUE (다음 SUE 통제)"), ("sue_next", "다음 SUE")]:
        print(f"  {lab:<34}{by_period(co[c])}")
    st["fmb_next"] = {c: {p: float(co[c][(co.index >= a_) & (co.index <= b_)].mean()) for p, a_, b_ in PERIODS}
                      for c in co}
    out["H3"] = st

    RUNS.mkdir(exist_ok=True)
    (RUNS / "hypo.json").write_text(json.dumps(out, ensure_ascii=False, indent=1, default=float))


if __name__ == "__main__":
    main()
