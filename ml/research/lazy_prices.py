#!/usr/bin/env python3
"""KAN-32 — Lazy Prices: 10-K/10-Q 문장의 전년 대비 변화가 수익·변동성을 예측하는가 (Cohen–Malloy–Nguyen 2020).

── 왜 ──────────────────────────────────────────────────────────────────────
KAN-23 에서 가격·거래량·실적 피처만으로는 월 수익 OOS R² < 0 이었다. 교훈은 "모델보다 입력"이었다.
CMN(2020) 은 공시 문장을 전년과 다르게 고친 기업('변경자', 유사도 하위)이 이후 수익이 나쁘고, 그 반영이
몇 달에 걸쳐 느리다고 보고했다(1994–2014, 미국 전 종목, 5분위 롱숏 월 ~30–60bp). 가격에 없는 새 정보원이다.
여기서는 S&P 500 · 2014–2026 에서 그 신호가 (a) 베타조정 초과수익을 횡단면으로 예측하는지,
(b) HAR 위에 다음 1·3개월 실현변동성을 더 설명하는지 본다. 음성 결과도 결과다.

── 정의 (실행 전에 고정) ───────────────────────────────────────────────────
재료      research.edgar — 공시 한 건마다 전년 같은 종류 공시와의 유사도 (본문 전체 full, 위험요인 rf, MD&A mda;
          cos = 단어 빈도 코사인, jac = 단어 집합 자카드), dlen = log 길이 비.
패널      panel.monthly_panel() 의 월말 행 t 에 avail ≤ t 인 가장 최근 공시의 값을 붙인다(edgar.asof_features,
          200일 넘게 묵으면 결측). age_days = t − avail, is_10k = 그 공시가 10-K 인가.
          신호값은 (날짜, 공시 종류) 안 백분위 — 10-K·10-Q 의 유사도 수준이 달라 종류가 신호에 섞이지 않게.
신호      SIGNALS 7개: cos_full · jac_full · cos_rf · jac_rf · cos_mda · jac_mda (높을수록 '안 바꾼 기업' = 롱),
          −dlen_full (길어진 기업 = 숏, CMN 의 '변경은 대개 추가').
(a1) 포트폴리오  날짜별 신호 5분위 — 상위(유사) 롱 · 하위(변경) 숏, 다리별 동일가중(자본 1씩).
          보유 K ∈ {1, 3, 6}개월은 Jegadeesh–Titman 겹침 포트폴리오: 월 t 비중 = 최근 K개 코호트 비중의 평균.
          월 수익 = Σ 비중 × y_ex(t→t+1, 베타조정 초과수익). 회전 = Σ|ΔW|, 순수익 = 총수익 − c·회전 (c = 0, 10bp).
          그 달 패널에 없는 종목(편출)의 몫은 0 수익으로 둔다(재정규화 안 함 — 하네스의 상폐 0 과 같은 관례).
          NW t, 기간 2014–19 / 2020–26. 순위 IC(신호 vs 다음 달 y_ex).
(a2) 증분 ML  KAN-23 피처 21개(+_na) ± 텍스트 피처(SIGNALS 7개(종류 안 백분위) + age_days + is_10k), panel.prepare 로
          날짜별 순위·중앙값 대체. walk_forward(2017-01, 매년 재학습, 검증 12개월) — KAN-23 과 같은 분할.
          Ridge(baselines.RidgeCV) · GBM-d3(xsection.GBM) 각각 기준/텍스트. evaluate.summarize · compare.
(b) 변동성 월말 행에서 다음 22·66세션 실현분산(일간 r² 평균, 로그). vol.py 의 OLS(풀링)·_run(안쪽 학습 적합,
          검증으로 분산 배율만) 그대로. HAR(lv1·lv5·lv22) ± 텍스트, HARX-lin(vol.py 전체 피처, 실적 달력 포함) ± 텍스트.
          장부에는 텍스트 2개 × 기준 대비와 HARX vs HAR (참고) 를 h 마다 적는다(6행).
          텍스트 = 날짜별 순위 [−1,1] 의 SIGNALS 7개(결측은 학습 중앙값). 손실 QLIKE(1차)·MSE-log, 날짜별
          평균 손실의 DM(h = 1·3개월 겹침 → lag ≥ h−1).
다중검정  장부 kan-32-lazy 의 모든 행(포트폴리오 21 + ML 4 + 변동성 6 = 31)을 한 가족으로 Holm.
          행마다 대표 p(p_primary): 포트폴리오 = 10bp 롱숏 NW p, ML 텍스트 = 기준 대비 IC 차 p,
          변동성 텍스트 = 기준 대비 QLIKE DM p, 기준 모델 = 자기 IC p. DSR = 10bp 롱숏 (N = 장부 행 수).

── 🔴 미래 정보 ────────────────────────────────────────────────────────────
🔴 공시 이용 가능일은 접수 시각보다 엄격히 뒤의 첫 세션(edgar.avail_session) — t 장후 공시는 t 행에 없다.
🔴 유사도 순위·분위는 날짜 안에서만(rank_normalize·날짜별 분위). 전체 표본 정규화 없음.
🔴 겹침 포트폴리오의 코호트 t−k 는 그때의 신호로만 정한다. 월 t 수익은 t 종가 뒤의 y_ex.
🔴 ML·변동성 분할은 label_end 로 퍼지 (cv.walk_forward). 변동성 66세션 라벨은 label_end_66 = t+66 세션.
🔴 티커→CIK 는 오늘의 SEC 목록 + 편출 종목 회사명 보정 — 매핑 실패 종목은 텍스트 결측(생존 편향, edgar 참고).

── 한계 ──────────────────────────────────────────────────────────────────
· 대형주 ~450종목이라 5분위 다리가 ~90종목 — CMN(전 종목, 20년)보다 검정력이 훨씬 작다.
· 10-K/10-Q 를 섞은 '가장 최근 공시' 유사도다. 10-Q 의 rf 는 "변경 없음" 한 줄이 흔하다.
· 섹션 추출은 정규식 — 실패율은 edgar coverage 에 적는다. 단어 단위 bag-of-words(어간·불용어 처리 없음).
· 상폐 수익 0 · 헤지·차입비 없음 · 비용은 편도 c × 회전(하네스와 같음).

실행 (ml/ 에서, 먼저 research.edgar index → fetch → sims):
  ../headline-sentiment/.venv/bin/python -m research.lazy_prices          # 처음이면 장부에 적고, 다음부터는 재사용
  ... -m research.lazy_prices --fresh                                     # 다시 계산·장부에 다시 적는다(N 이 는다)
  LP_DEV=1 ... -m research.lazy_prices                                    # 점검 실행 (장부·캐시 분리)
"""
from __future__ import annotations

import argparse
import os
import pickle
import sys
import time

import numpy as np
import pandas as pd

from . import baselines, cv, edgar, evaluate, panel, registry

DEV = os.environ.get("LP_DEV") == "1"                    # 점검 실행: 장부·캐시·보고서 분리
STUDY = "dev-kan-32" if DEV else "kan-32-lazy"
OUT = panel.RUNS / ("lazy_prices_dev" if DEV else "lazy_prices")
REPORT = panel.RUNS / ("lazy_prices_dev.txt" if DEV else "lazy_prices.txt")
LEDGER = OUT / "ledger_dev.jsonl" if DEV else None        # None → 공용 장부
FIRST_TEST, REFIT, VAL = "2017-01-01", 12, 12
SIGNALS = ["cos_full", "jac_full", "cos_rf", "jac_rf", "cos_mda", "jac_mda", "neg_dlen_full"]
TEXT_ML = SIGNALS + ["age_days", "is_10k"]
HOLDS = (1, 3, 6)
COSTS = (0, 10)
N_Q = 5
PERIODS = {"2014–19": ("2014-01-01", "2019-12-31"), "2020–26": ("2020-01-01", "2026-12-31")}
MAX_AGE = 200


# ── 패널 ───────────────────────────────────────────────────────────────────

def text_panel(P: pd.DataFrame | None = None) -> pd.DataFrame:
    """월말 패널 + 텍스트 피처(가장 최근 공시 as-of)."""
    P = panel.monthly_panel() if P is None else P
    P = P.reset_index(drop=True).copy()
    P["ticker"] = P["ticker"].astype(str)
    S = edgar.load_sims()
    S["neg_dlen_full"] = -S["dlen_full"]
    S["is_10k"] = (S["form"] == "10-K").astype(float)
    cols = [c for c in SIGNALS if c != "neg_dlen_full"] + ["neg_dlen_full", "is_10k"]
    A = edgar.asof_features(P, S, cols, max_age_days=MAX_AGE)
    for c in cols + ["age_days"]:
        P[c] = A[c].to_numpy()
    # 10-K 끼리의 유사도가 10-Q 끼리보다 체계적으로 높다(점검 실행: jac_full 중앙값 0.89 vs 0.81). 그대로 섞어
    # 순위를 매기면 '최근 공시가 10-Q 인가' 가 신호가 된다. 그래서 신호는 (날짜, 공시 종류) 안 백분위로 쓴다.
    # 🔴 날짜 안에서만 — 원값은 <c>_raw 로 남긴다.
    g = P.groupby(["date", "is_10k"], observed=True, sort=False)
    for c in SIGNALS:
        P[f"{c}_raw"] = P[c]
        P[c] = g[c].rank(pct=True)
    return P


# ── (a1) 겹침 5분위 롱숏 ──────────────────────────────────────────────────────

def cohort_weights(S: pd.DataFrame, n_q: int = N_Q) -> tuple[pd.DataFrame, pd.DataFrame]:
    """S (날짜 × 티커 신호) → (롱 비중, 숏 비중). 날짜별 상위·하위 1/n_q, 다리별 합 1."""
    q = S.rank(axis=1, method="first", pct=True)
    top, bot = (q > 1 - 1 / n_q).astype(float), (q <= 1 / n_q).astype(float)
    return top.div(top.sum(axis=1).replace(0, np.nan), axis=0).fillna(0), \
        bot.div(bot.sum(axis=1).replace(0, np.nan), axis=0).fillna(0)


def overlap_ls(D: pd.DataFrame, sig: str, K: int, costs=COSTS, n_q: int = N_Q, y: str = "y_ex") -> pd.DataFrame:
    """Jegadeesh–Titman 겹침 롱숏. 반환 (월 t 행): ls(총), ls_net{c}, to(Σ|ΔW| 두 다리), n_long, n_short.
    🔴 코호트 t−k 의 비중은 t−k 의 신호로만. 월 t 수익은 y(t→t+1)."""
    S = D.pivot_table(index="date", columns="ticker", values=sig)
    Y = D.pivot_table(index="date", columns="ticker", values=y).reindex(index=S.index, columns=S.columns)
    WL, WS = cohort_weights(S, n_q)
    L = sum(WL.shift(k).fillna(0) for k in range(K)) / K
    Sh = sum(WS.shift(k).fillna(0) for k in range(K)) / K
    Yz = Y.fillna(0.0)
    out = pd.DataFrame(index=S.index)
    out["ls"] = (L * Yz).sum(axis=1) - (Sh * Yz).sum(axis=1)
    to = L.diff().abs().sum(axis=1) + Sh.diff().abs().sum(axis=1)
    to.iloc[0] = L.iloc[0].abs().sum() + Sh.iloc[0].abs().sum()
    out["to"] = to
    for c in costs:
        out[f"ls_net{c}"] = out["ls"] - c / 1e4 * out["to"]
    out["n_long"], out["n_short"] = (WL > 0).sum(axis=1), (WS > 0).sum(axis=1)
    out = out.iloc[K - 1:]                     # 코호트가 K 개 다 찬 달부터
    return out[Y.reindex(out.index).notna().any(axis=1)]   # 마지막 월말(라벨 없음) 제외


def signal_ic(D: pd.DataFrame, sig: str, y: str = "y_ex") -> pd.Series:
    return evaluate.rank_ic(D.rename(columns={sig: "pred", y: "y"})[["date", "pred", "y"]])


def portfolio_metrics(D: pd.DataFrame, sig: str, K: int) -> tuple[dict, pd.DataFrame]:
    pf = overlap_ls(D, sig, K)
    m = {}
    for c in COSTS:
        for k, v in evaluate.series_stats(pf[f"ls_net{c}"], 12).items():
            m[f"ls_c{c}_{k}"] = v
        for nm, (a, b) in PERIODS.items():
            x = pf.loc[a:b, f"ls_net{c}"]
            st = evaluate.series_stats(x, 12)
            m[f"ls_c{c}_{nm}_ann"], m[f"ls_c{c}_{nm}_t"] = st["ann"], st["t"]
    m["turnover"] = float(pf["to"].iloc[1:].mean() / 4)           # 회당 교체율 (두 다리 총자본 2)
    m["n_leg"] = float(pf[["n_long", "n_short"]].mean().mean())
    m.update(evaluate.ic_summary(signal_ic(D, sig)))
    m["p_primary"] = m["ls_c10_p"]
    return m, pf


# ── (a2) 증분 ML ──────────────────────────────────────────────────────────────

def _gbm():
    from .xsection import GBM
    return GBM(3, n_jobs=6)


def ml_runs(P: pd.DataFrame) -> dict:
    """KAN-23 피처 ± 텍스트, Ridge · GBM-d3. 반환 {이름: R}."""
    import warnings
    warnings.filterwarnings("ignore", message=".*eval_set.*")
    P = P.dropna(subset=["y_ex"]).reset_index(drop=True)
    base_feats = list(panel.FEATURES)
    Q, cols_all = panel.prepare(P, base_feats + TEXT_ML)
    cols_base = [c for c in cols_all if c.removesuffix("_na") in base_feats]
    folds = cv.walk_forward(Q["date"], Q["label_end"], first_test=FIRST_TEST, refit_months=REFIT, val_months=VAL)
    out = {}
    for nm, make in (("Ridge", baselines.RidgeCV), ("GBM-d3", _gbm)):
        for tag, cols in (("base", cols_base), ("text", cols_all)):
            t0 = time.time()
            R = cv.predict_oos(Q, folds, cols, "y_ex", make, refit_on_val=True)
            R["ticker"] = R["ticker"].astype(str)
            out[f"{nm}-{tag}"] = R
            print(f"  [ML] {nm}-{tag}: 열 {len(cols)} · {time.time() - t0:.0f}s", flush=True)
    out["_bench"] = evaluate.hist_mean(Q, "y_ex", Q["date"])
    out["_cols"] = (cols_base, cols_all)
    return out


# ── (b) 변동성 ────────────────────────────────────────────────────────────────

VOL_H = (22, 66)          # 세션 — 1·3개월
VOL_TXT = [f"r_{c}" for c in SIGNALS]


def vol_frame(P: pd.DataFrame) -> pd.DataFrame:
    """vol.build() 의 일간 패널을 월말 행으로 줄이고 66세션 라벨과 텍스트 순위를 붙인다."""
    from . import vol
    D = vol.build(verbose=False)
    me = set(panel.month_ends(panel.load_raw().sessions))
    D = D[D["date"].isin(me)].reset_index(drop=True)
    raw = panel.load_raw()
    R = raw.C.pct_change(fill_method=None)
    f66 = (R ** 2).rolling(66, min_periods=66).mean().shift(-66).to_numpy("float64")
    D["rv_66"] = f66[D["t"].to_numpy(), D["j"].to_numpy()]
    D["y_66"] = np.log(np.maximum(D["rv_66"], vol.FLOOR))
    T = len(raw.sessions)
    e = D["t"].to_numpy() + 66
    D["label_end_66"] = pd.DatetimeIndex(np.where(e < T, raw.sessions.to_numpy()[np.minimum(e, T - 1)],
                                                  np.datetime64("NaT", "ns")))
    X = P[["date", "ticker", *SIGNALS]].copy()
    X = panel.rank_normalize(X, SIGNALS)                    # 🔴 날짜 안에서만
    X = X.rename(columns={c: f"r_{c}" for c in SIGNALS})
    D["ticker"] = D["ticker"].astype(str)
    D = D.merge(X, on=["date", "ticker"], how="left")
    return D


def vol_runs(D: pd.DataFrame) -> dict:
    from . import vol
    out = {}
    for h in VOL_H:
        folds = cv.walk_forward(D["date"], D[f"label_end_{h}"], first_test=FIRST_TEST, refit_months=12, val_months=12)
        harx = vol.features("HARX-lin", 22)
        for nm, cols in (("HAR", vol.HAR), ("HAR+text", vol.HAR + VOL_TXT),
                         ("HARX", harx), ("HARX+text", harx + VOL_TXT)):
            out[(nm, h)] = vol._run(D, folds, cols, h, vol.OLS)
    return out


def vol_metrics(D, h, preds, nm, base):
    from . import vol
    mask = np.isfinite(D[f"y_{h}"].to_numpy())
    for k in ((nm, h), (base, h)):
        mask &= np.isfinite(preds[k][0]) & np.isfinite(preds[k][1])
    y, rv = D[f"y_{h}"].to_numpy(), np.maximum(D[f"rv_{h}"].to_numpy(), vol.FLOOR)
    dates = D["date"].to_numpy()[mask]

    def per_date(pl, pv):
        lq = evaluate.loss_qlike(rv, pv)[mask]
        lm = evaluate.loss_mse(y, pl)[mask]
        return pd.Series(lq).groupby(dates).mean(), pd.Series(lm).groupby(dates).mean()

    qa, ma = per_date(*preds[(nm, h)])
    qb, mb = per_date(*preds[(base, h)])
    hm = h // 22
    dq, dm = evaluate.diebold_mariano(qa, qb, h=hm), evaluate.diebold_mariano(ma, mb, h=hm)
    Rr = pd.DataFrame({"date": dates, "pred": preds[(nm, h)][0][mask], "y": rv[mask]})
    ic = evaluate.ic_summary(evaluate.rank_ic(Rr))
    return dict(qlike=float(qa.mean()), mse_log=float(ma.mean()), qlike_base=float(qb.mean()),
                mse_base=float(mb.mean()), qlike_gain=float(1 - qa.mean() / qb.mean()),
                mse_gain=float(1 - ma.mean() / mb.mean()), dm_qlike=dq["stat"], dm_qlike_p=dq["p"],
                dm_mse=dm["stat"], dm_mse_p=dm["p"], n_dates=int(len(qa)), n_rows=int(mask.sum()), **ic)


# ── 실행 ────────────────────────────────────────────────────────────────────

def _logged() -> set:
    L = registry.load(STUDY, path=LEDGER)
    return set(L["name"]) if len(L) else set()


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--fresh", action="store_true", help="계산을 다시 하고 장부에 다시 적는다")
    a = ap.parse_args(argv)
    OUT.mkdir(parents=True, exist_ok=True)
    t0 = time.time()
    lines: list[str] = []

    def say(s=""):
        print(s, flush=True)
        lines.append(s)

    P = text_panel()
    have = _logged() if not a.fresh else set()

    def log(name, params, metrics):
        if name not in have:
            registry.log(STUDY, name, params, metrics, path=LEDGER)

    # 커버리지 (패널 기준)
    say(f"KAN-32 Lazy Prices — {pd.Timestamp.now():%Y-%m-%d %H:%M}")
    say(f"패널 {len(P):,}행 · 월말 {P['date'].nunique()} · 텍스트 as-of 있는 행 {P['cos_full'].notna().mean():.1%}"
        f" (rf {P['cos_rf'].notna().mean():.1%}, mda {P['cos_mda'].notna().mean():.1%}) · 정보 나이 중앙값 "
        f"{P['age_days'].median():.0f}일")
    yr = P.assign(y=P["date"].dt.year).groupby("y")[["cos_full", "cos_rf", "cos_mda"]].agg(lambda s: s.notna().mean())
    say("  연도별 커버리지 full/rf/mda: " + " · ".join(f"{y} {r.cos_full:.0%}/{r.cos_rf:.0%}/{r.cos_mda:.0%}"
                                                    for y, r in yr.iterrows()))
    say("  유사도 분포(패널 행): " + " · ".join(f"{c} 중앙 {P[c].median():.3f} (p10 {P[c].quantile(.1):.3f})"
                                          for c in SIGNALS[:6]))
    say("  신호 간 순위상관(날짜 평균 아님, 풀링): ")
    say("    " + P[SIGNALS].rank().corr().round(2).to_string().replace("\n", "\n    "))

    # (a1) 포트폴리오
    say("\n[a1] 5분위 롱숏 (유사 롱 · 변경 숏), y_ex, 겹침 보유 K개월")
    say(f"  {'신호':<14}{'K':>2}  IC (t)          0bp 연 (t)      10bp 연 (t)  샤프  2014–19 10bp (t)  2020–26 10bp (t)  교체  다리")
    D = P.dropna(subset=["y_ex"])[["date", "ticker", "y_ex", *SIGNALS]]
    D = pd.concat([D, P[P["y_ex"].isna()][["date", "ticker", "y_ex", *SIGNALS]]])
    pfs = {}
    for sig in SIGNALS:
        for K in HOLDS:
            m, pf = portfolio_metrics(D, sig, K)
            pfs[(sig, K)] = pf
            log(f"LS-{sig}-K{K}", dict(kind="portfolio", signal=sig, hold=K, n_q=N_Q, label="y_ex",
                                       max_age=MAX_AGE), m)
            say(f"  {sig:<14}{K:>2}  {m['ic_mean']:+.4f} ({m['ic_t']:+.2f})  {m['ls_c0_ann']:+6.2%} ({m['ls_c0_t']:+.2f})  "
                f"{m['ls_c10_ann']:+6.2%} ({m['ls_c10_t']:+.2f})  {m['ls_c10_sr']:+.2f}  "
                f"{m['ls_c10_2014–19_ann']:+6.2%} ({m['ls_c10_2014–19_t']:+.2f})  "
                f"{m['ls_c10_2020–26_ann']:+6.2%} ({m['ls_c10_2020–26_t']:+.2f})  {m['turnover']:.0%}  {m['n_leg']:.0f}")
    pickle.dump(pfs, open(OUT / "portfolios.pkl", "wb"))

    # (a2) ML
    say("\n[a2] 증분 ML (KAN-23 피처 ± 텍스트, walk-forward 2017-01, 매년 재학습)")
    f_ml = OUT / "ml.pkl"
    if f_ml.exists() and not a.fresh:
        ML = pickle.loads(f_ml.read_bytes())
    else:
        ML = ml_runs(P)
        f_ml.write_bytes(pickle.dumps(ML))
    bench = ML["_bench"]
    for nm in ("Ridge", "GBM-d3"):
        sb = evaluate.summarize(ML[f"{nm}-base"], bench=bench, costs=COSTS)
        st = evaluate.summarize(ML[f"{nm}-text"], bench=bench, costs=COSTS)
        cmp = evaluate.compare(ML[f"{nm}-text"], ML[f"{nm}-base"], costs=COSTS)
        sb["p_primary"] = sb["ic_p"]
        st.update({f"vs_base_{k}": v for k, v in cmp.items()})
        st["p_primary"] = cmp["ic_diff_p"]
        log(f"ML-{nm}-base", dict(kind="ml", model=nm, features="kan23", first_test=FIRST_TEST, refit=REFIT, val=VAL), sb)
        log(f"ML-{nm}-text", dict(kind="ml", model=nm, features="kan23+text", text=TEXT_ML, first_test=FIRST_TEST,
                                  refit=REFIT, val=VAL), st)
        for tag, s in (("base", sb), ("text", st)):
            say(f"  {nm}-{tag:<4} R²(0) {s['r2_zero']:+.2%} · R²(hist) {s['r2_hist']:+.2%} · IC {s['ic_mean']:+.4f} "
                f"(t {s['ic_t']:+.2f}) · 10분위 LS 10bp 연 {s['ls_c10_ann']:+.2%} (t {s['ls_c10_t']:+.2f})")
        say(f"    텍스트 − 기준: IC 차 {cmp['ic_diff_ann']:+.4f} (t {cmp['ic_diff_t']:+.2f}, p {cmp['ic_diff_p']:.2f}) · "
            f"LS10 차 연 {cmp['ls_c10_diff_ann']:+.2%} (t {cmp['ls_c10_diff_t']:+.2f}) · DM(MSE) {cmp['dm_stat']:+.2f}")

    # (b) 변동성
    say("\n[b] 변동성 (월말 행, 다음 22·66세션 실현분산) — 텍스트 순위 추가 효과")
    f_vol = OUT / "vol.pkl"
    VD = vol_frame(P)
    if f_vol.exists() and not a.fresh:
        VP = pickle.loads(f_vol.read_bytes())
    else:
        VP = vol_runs(VD)
        f_vol.write_bytes(pickle.dumps(VP))
    for h in VOL_H:
        for nm, base in (("HAR", None), ("HAR+text", "HAR"), ("HARX", "HAR"), ("HARX+text", "HARX")):
            if base is None:
                continue
            m = vol_metrics(VD, h, VP, nm, base)
            m["p_primary"] = m["dm_qlike_p"]
            log(f"VOL-{nm}-vs-{base}-h{h}", dict(kind="vol", model=nm, base=base, h=h, text=VOL_TXT), m)
            say(f"  h={h:<2} {nm:<10} vs {base:<5} QLIKE {m['qlike']:.4f} vs {m['qlike_base']:.4f} ({m['qlike_gain']:+.2%}, "
                f"DM {m['dm_qlike']:+.2f}, p {m['dm_qlike_p']:.3f}) · MSE-log {m['mse_gain']:+.2%} (DM {m['dm_mse']:+.2f}) · "
                f"IC {m['ic_mean']:.3f} · {m['n_dates']}개월")
        # 텍스트 단독 방향: 변경자(유사도 하위) → HAR 예측보다 높은 변동성? (HAR 잔차와의 순위 IC)
        # 잔차 5분위 차 = 변경자(하위 유사도) − 비변경자 의 평균 log 잔차 (≈ 분산 비 −1)
        for c in ("cos_full", "jac_full"):
            for base in ("HAR", "HARX"):
                pl = VP[(base, h)][0]
                ok = (np.isfinite(VD[f"y_{h}"]) & np.isfinite(pl) & VD[f"r_{c}"].notna()).to_numpy()
                res = pd.DataFrame({"date": VD["date"].to_numpy()[ok], "pred": -VD[f"r_{c}"].to_numpy()[ok],
                                    "y": VD[f"y_{h}"].to_numpy()[ok] - pl[ok]})
                ic = evaluate.ic_summary(evaluate.rank_ic(res).dropna())
                q = res.groupby("date")["pred"].rank(pct=True)
                spread = res.loc[q > 0.8, "y"].mean() - res.loc[q <= 0.2, "y"].mean()
                msg = ""
                if base == "HAR":
                    raw_ic = evaluate.ic_summary(evaluate.rank_ic(res.assign(y=VD[f"y_{h}"].to_numpy()[ok])).dropna())
                    msg = f"log RV_h 순위 IC {raw_ic['ic_mean']:+.4f} (t {raw_ic['ic_t']:+.2f}) · "
                say(f"    진단 −{c}: {msg}{base} 잔차 IC {ic['ic_mean']:+.4f} (t {ic['ic_t']:+.2f}) · "
                    f"변경−비변경 5분위 잔차 차 {spread:+.3f} log")

    # 다중검정
    L = registry.load(STUDY, path=LEDGER)
    L = registry.adjust(L, "p_primary")
    Lp = registry.deflate(L[L["name"].str.startswith("LS-")], "ls_c10", n_trials=len(L))
    say(f"\n[다중검정] 장부 {STUDY} N = {len(L)} 행 (Holm 가족 = 전체)")
    for _, r in L.sort_values("p_primary").head(8).iterrows():
        say(f"  {r['name']:<32} p {r['p_primary']:.4f} → Holm {r['p_primary_holm']:.3f} · BH {r['p_primary_bh']:.3f}")
    best = Lp.sort_values("ls_c10_srpp", ascending=False).head(3)
    for _, r in best.iterrows():
        say(f"  DSR {r['name']:<28} 월 SR {r['ls_c10_srpp']:+.3f} · SR0 {r['ls_c10_sr0']:.3f} · DSR {r['ls_c10_dsr']:.2f}")
    say(f"\n총 {time.time() - t0:.0f}s")
    REPORT.write_text("\n".join(lines) + "\n")
    print(f"[저장] {REPORT}")


if __name__ == "__main__":
    sys.exit(main())
