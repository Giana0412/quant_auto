#!/usr/bin/env python3
"""KAN-27 — KAN-23 의 유일한 신호("저베타·저변동성 종목이 이긴다")는 진짜인가, 라벨의 산물인가.

── 왜 ──────────────────────────────────────────────────────────────────────
KAN-23 의 모든 모델이 순열 중요도 상위로 beta · rvol_1m · rvol_3m 을 꼽았고, 원수익 롱숏은 SPY β −0.4 ~ −0.9
였다. 그런데 라벨 y_ex 는 "수익 − 수축 안 한 과거 250일 β × SPY" 다. 실현 β 는 1 쪽으로 평균회귀하므로
과거 β 가 큰 종목은 다음 달 β 가 그보다 작다 → 헤지를 너무 많이 한다 → 상승장(2017–2026, SPY 연 +14%)에서는
고베타 종목의 y_ex 가 기계적으로 낮아진다. 그러면 "저베타 롱 · 고베타 숏" 이 y_ex 기준으로는 돈을 번 것처럼
보이지만, 실제로는 시장 노출(음의 β × 양의 시장)을 덜 뺀 것일 수 있다.
같은 포트폴리오를 라벨만 바꿔 다시 재고, 무엇보다 **사후 실현 β 를 회귀로 뺀 α** 를 본다 — 이 α 는
라벨 정의와 무관하다(같은 종목 묶음이면 원수익 기준으로 같은 숫자).

── 정의 (실행 전에 고정) ─────────────────────────────────────────────────────
라벨 변형 (모두 일간 r − β̂_{d−1} × r_SPY 를 t+1 … t' 에서 합한다, β̂ 는 0~3 클립 — y_ex 와 같은 틀)
  a  raw   β̂ = 수축 없는 250일 OLS β (panel.y_ex 를 비트 단위로 재현 — assert).
  b1 vas   Vasicek(1973): β̂ = w·β + (1−w)·β̄_d,  w = τ²_d / (τ²_d + se²_i,d).
           β̄_d · τ²_d = 그날 편입 종목 β 의 횡단면 평균 · (분산 − 평균 se²) (하한 = 분산의 5%).
           se² = 잔차분산 / ((n−1)·var(r_SPY)),  잔차분산 = (var(r) − β²·var(r_SPY))·(n−1)/(n−2).
  b2 bbg   Bloomberg 조정 β = 0.67·β + 0.33.
  b3 cal   경험 보정: β̂ = a_k + b_k·β. (a_k, b_k) = 월말 t_j 의 β 로 그다음 달 실현 β(일간 OLS, ≥15일)를
           설명하는 풀링 OLS, **창이 t_k 이전에 끝난 쌍만**(확장창, 최소 12개월; 그 전은 bbg 계수).
           실현 β 는 [−3, 6] 으로 자른다(고정 규칙). Vasicek 이 추정오차만 고치는 데 반해 참 β 의 이동까지 고친다.
  c  mkt   β = 1 → r − r_SPY.
  d  xs    원수익 y_raw − 날짜 평균 (시장 성분을 아예 뺀다 — 롱숏 수익은 원수익 롱숏과 같다).
베타 보정 (e)  월말 t 의 ex-ante β 변형 → 다음 1개월 / 12개월(252세션, ≥120일) 실현 β. 날짜별 횡단면 OLS
           기울기의 시간 평균 (NW t, 12개월은 겹치므로 lag 12) · 풀링 기울기 · ex-ante β 10분위별 평균.
           기울기 1 = 잘 맞춘 예측, < 1 = 평균회귀(고베타 과대추정).
신호 (라벨마다 같은 것)
  단일 피처  −beta · −rvol_1m · −rvol_3m · −ivol_3m (부호를 뒤집어 '저위험 롱' 이 양의 IC).
  재학습     Ridge(baselines.RidgeCV) · GBM-d1(xsection.GBM(1)) — 그 라벨로 학습, 그 라벨로 평가.
             KAN-23 과 같은 피처 40열 · walk_forward(2017-01, refit 12, val 12) · 학습+검증 재학습.
  BAB        Frazzini–Pedersen 식: bbg β 10분위, 롱 저β 1/β_L 배 · 숏 고β 1/β_H 배 (ex-ante β 중립), 원수익.
평가       evaluate.summarize (라벨 기준 IC · 10분위 롱숏 0/10/25bp) +
           ① 라벨 롱숏(10bp)을 같은 달 SPY 수익에 회귀 → 남은 실현 β, α(연), NW t  ← **핵심**
           ② 원수익 롱숏을 SPY 에 회귀 → 실현 β·α (라벨과 무관한 기준)
           ③ 롱숏의 ex-ante β 차(raw β 기준) vs 실현 β — 과대 헤지의 크기.
다중검정   장부 kan-27-beta 의 줄 수 = N. Holm: 전 설정의 IC p · β 중립 α(10bp) p. DSR: ls_c10 · β 중립 α 각각.

── 🔴 미래 정보 ────────────────────────────────────────────────────────────
🔴 모든 β̂ 은 d−1 종가까지로 d 의 헤지를 정한다(shift 1). Vasicek 의 β̄·τ² 도 그날 편입 종목의 그날 β 만.
🔴 보정 계수 (a_k, b_k) 는 라벨 창이 t_k 까지 **끝난** 쌍만 쓴다 — 확장창, 미래 실현 β 를 안 본다.
🔴 (e) 의 실현 β 는 사후 진단이다 — 라벨·피처에는 (b3 의 과거 쌍 말고는) 들어가지 않는다.
🔴 "사후 β 중립 α" 는 전 표본 회귀 β 를 쓴다 — 거래 가능한 헤지가 아니라 '시장 노출을 빼면 남는가' 의
   진단이다. 거래 가능한 β 중립은 BAB(ex-ante 1/β 비중)로 따로 본다.

── 한계 ──────────────────────────────────────────────────────────────────
· 무위험 이자율 자료가 없다. 롱숏(달러 중립)은 rf 가 상쇄되지만 SPY 를 rf 빼지 않고 회귀하므로 α 는
  β_LS·rf 만큼 다르다(β −0.8, rf 연 ~2.5% → α 가 ~2%p 과대). BAB 의 rf 항 −rf·(1/β_L − 1/β_H) 도 없다.
  보고서에 rf = 연 2.5% 상수 근사(2017–2026 T-bill 평균 대략치, 저장소 밖 숫자)로 감도를 같이 낸다.
· 생존 편향 · 상폐 수익 0 · 차입비 없음 (README). 시가총액 가중 없음 — 동일가중 10분위.
· 117개월 · 대형주 ~450 — 월 α 1%/년 수준은 검정력 밖이다(α 표준오차 연 ~3–4%).
· 장부 시도들은 같은 포트폴리오를 라벨만 바꿔 잰 것이라 강하게 상관 — N 은 독립 시도 수의 상한.

실행 (ml/ 에서):
  ../headline-sentiment/.venv/bin/python -m research.beta_label           # 예측 캐시 있으면 재사용
  ... -m research.beta_label --fresh                                       # 전부 다시 (장부에 다시 적힌다)
"""
from __future__ import annotations

import argparse
import contextlib
import io
import os
import sys
import time
import warnings

import numpy as np
import pandas as pd

from . import baselines, cv, evaluate, panel, registry
from .xsection import GBM

warnings.filterwarnings("ignore", message=".*eval_set.*")   # LightGBM 4.6 의 인자 이름 경고 (동작 같음)

DEV = os.environ.get("BL_DEV") == "1"                   # 점검 실행: 장부·캐시·보고서 분리
STUDY = "dev-kan-27" if DEV else "kan-27-beta"
OUT = panel.RUNS / ("beta_label_dev" if DEV else "beta_label")
REPORT = panel.RUNS / ("beta_label_dev.txt" if DEV else "beta_label.txt")
LEDGER = OUT / "ledger_dev.jsonl" if DEV else None        # None → 공용 장부
FIRST_TEST, REFIT, VAL = "2017-01-01", 12, 12
LABELS = ("unsh", "vas", "bbg", "cal", "mkt", "xs")      # y_raw(원수익)와 겹치지 않게 a = unsh
LABEL_DESC = {"unsh": "a 수축 없는 β (=y_ex)", "vas": "b1 Vasicek β", "bbg": "b2 0.67β+0.33",
              "cal": "b3 경험 보정 β", "mkt": "c β=1 (r−SPY)", "xs": "d 원수익−날짜평균"}
FEATS = ("beta", "rvol_1m", "rvol_3m", "ivol_3m")
MODELS = ("Ridge", "GBM-d1")
CAL_MIN_MONTHS, CAL_CLIP = 12, (-3.0, 6.0)
RF_APPROX = 0.025                      # 연, 감도 분석용 근사치 (자료 없음 — docstring 한계)


# ── β 변형 (일간) ────────────────────────────────────────────────────────────

def _window_beta(Rv: np.ndarray, m: np.ndarray, a: np.ndarray, b: np.ndarray, min_n: int) -> np.ndarray:
    """행 k 마다 세션 (a_k, b_k] 의 일간 OLS β (종목별, 수익이 있는 날만). a, b 는 세션 위치 배열."""
    I = np.isfinite(Rv)
    r0 = np.where(I, Rv, 0.0)
    mm = np.where(I, m[:, None], 0.0)
    z = np.zeros((1, Rv.shape[1]))
    S = {k: np.vstack([z, np.cumsum(v, axis=0)]) for k, v in
         (("n", I.astype(float)), ("r", r0), ("m", mm), ("rm", r0 * mm), ("mm", mm * mm))}
    d = {k: S[k][b + 1] - S[k][a + 1] for k in S}
    n = d["n"]
    with np.errstate(invalid="ignore", divide="ignore"):
        cov = d["rm"] - d["r"] * d["m"] / n
        var = d["mm"] - d["m"] ** 2 / n
        beta = cov / var
    beta[(n < min_n) | ~np.isfinite(beta)] = np.nan
    return beta


def beta_variants(raw: panel.Raw) -> dict:
    """세션 × 티커 β̂ 변형 4개(raw · vas · bbg · cal) + 보조(R, m, 월말, 보정 계수, 월별 실현 β)."""
    C = raw.C
    R, beta, _ = panel.beta_excess(C)
    m = R["SPY"]
    W, MN = panel.BETA_WIN, panel.BETA_MIN
    M = panel.member_mask(raw)
    # Vasicek
    n = R.rolling(W, min_periods=MN).count()
    var_r = R.rolling(W, min_periods=MN).var()
    var_m = m.rolling(W, min_periods=MN).var()
    resid = (var_r - beta.pow(2).mul(var_m, axis=0)).clip(lower=0) * (n - 1) / (n - 2)
    se2 = resid.div(var_m, axis=0) / (n - 1)
    Bm = beta.where(M)
    bbar, bvar = Bm.mean(axis=1), Bm.var(axis=1)
    mse = se2.where(M & beta.notna()).mean(axis=1)
    tau2 = np.maximum(bvar - mse, 0.05 * bvar)
    w = 1 / (1 + se2.div(tau2, axis=0))
    vas = w * beta + (1 - w).mul(bbar, axis=0)
    # 경험 보정 — 월말 t_j 의 β → (t_j, t_{j+1}] 실현 β
    ses = raw.sessions
    me_all = panel.month_ends(ses)
    pos = ses.get_indexer(me_all)
    Rv, mv = R.to_numpy(), m.to_numpy()
    real1 = _window_beta(Rv, mv, pos[:-1], pos[1:], 15)          # 행 j: 월말 j 다음 달
    real1 = np.clip(real1, *CAL_CLIP)
    Bv, Mv = beta.to_numpy(), M.to_numpy()
    coef = np.full((len(pos), 2), np.nan)                        # 월말 k 에 알려진 (a, b)
    xs, ys = [], []
    for k in range(len(pos)):
        if k >= 1:                                               # 쌍 j = k−1 의 창 (t_{k−1}, t_k] 가 t_k 에 끝났다
            j = k - 1
            x, y = Bv[pos[j]], real1[j]
            ok = Mv[pos[j]] & np.isfinite(x) & np.isfinite(y)
            xs.append(x[ok]), ys.append(y[ok])
        if len(xs) >= CAL_MIN_MONTHS:
            X, Y = np.concatenate(xs), np.concatenate(ys)
            b1, a1 = np.polyfit(X, Y, 1)
            coef[k] = (a1, b1)
    coef_s = pd.DataFrame(coef, index=me_all, columns=["a", "b"]).reindex(ses).ffill()
    coef_s = coef_s.fillna({"a": 0.33, "b": 0.67})               # 보정 전 구간 = bbg
    cal = beta.mul(coef_s["b"], axis=0).add(coef_s["a"], axis=0)
    B = {"raw": beta, "vas": vas, "bbg": 0.67 * beta + 0.33, "cal": cal}
    return dict(R=R, m=m, B=B, M=M, se2=se2, w=w, me_all=me_all, pos=pos, coef=coef_s, coef_me=coef,
                real1=real1)


def labels(P: pd.DataFrame, raw: panel.Raw, V: dict) -> pd.DataFrame:
    """P 의 (date, ticker) 행마다 라벨 변형 y_<label> 과 월말 ex-ante β̂ b_<variant>(0~3 클립)."""
    ses = raw.sessions
    R, m = V["R"], V["m"]
    t = ses.get_indexer(P["date"])
    t2 = ses.get_indexer(P["label_end"])
    assert (t >= 0).all() and (t2 > t).all()
    j = R.columns.get_indexer(P["ticker"].astype(str))
    assert (j >= 0).all()
    out = pd.DataFrame(index=P.index)
    for name in ("unsh", "vas", "bbg", "cal", "mkt"):
        if name == "mkt":
            ex = R.sub(m, axis=0)
        else:
            ex = R - V["B"]["raw" if name == "unsh" else name].shift(1).clip(0, 3).mul(m, axis=0)
        cs = np.cumsum(np.nan_to_num(ex.to_numpy()), axis=0)
        out[f"y_{name}"] = cs[t2, j] - cs[t, j]
    out["y_xs"] = P["y_raw"] - P.groupby("date")["y_raw"].transform("mean")
    for name, B in V["B"].items():
        out[f"b_{name}"] = np.clip(B.to_numpy()[t, j], 0, 3)
    return out


# ── 베타 보정 (e) ─────────────────────────────────────────────────────────────

def calibration(raw: panel.Raw, V: dict, P: pd.DataFrame) -> dict:
    """월말 ex-ante β 변형 → 다음 1개월 · 12개월 실현 β. 날짜별 기울기·절편, 풀링, 10분위 표."""
    ses = raw.sessions
    pos = V["pos"]
    me = V["me_all"]
    Rv, mv = V["R"].to_numpy(), V["m"].to_numpy()
    end12 = pos + 252
    ok12 = end12 < len(ses)
    real12 = np.full((len(pos), Rv.shape[1]), np.nan)
    real12[ok12] = _window_beta(Rv, mv, pos[ok12], end12[ok12], 120)
    real1 = np.vstack([_window_beta(Rv, mv, pos[:-1], pos[1:], 15), np.full((1, Rv.shape[1]), np.nan)])
    Mv = V["M"].to_numpy()
    keep = me >= pd.Timestamp(panel.START)
    res = {}
    for h, Y in (("1m", real1), ("12m", real12)):
        for name, B in V["B"].items():
            Bv = B.to_numpy()
            sl, ic, rows = [], [], []
            for k in np.flatnonzero(keep):
                x, y = Bv[pos[k]], Y[k]
                ok = Mv[pos[k]] & np.isfinite(x) & np.isfinite(y)
                if ok.sum() < 50:
                    continue
                b1, a1 = np.polyfit(x[ok], np.clip(y[ok], *CAL_CLIP), 1)
                sl.append((me[k], b1, a1))
                rows.append(pd.DataFrame({"date": me[k], "x": x[ok], "y": y[ok]}))
            S = pd.DataFrame(sl, columns=["date", "slope", "icpt"]).set_index("date")
            D = pd.concat(rows, ignore_index=True)
            lag = 12 if h == "12m" else None
            bp, ap = np.polyfit(D["x"], np.clip(D["y"], *CAL_CLIP), 1)
            D["dec"] = D.groupby("date")["x"].rank(pct=True).mul(10).clip(upper=9.999).astype(int)
            dec = D.groupby("dec").agg(ante=("x", "mean"), real=("y", "median"), real_mean=("y", "mean"))
            res[(h, name)] = dict(slope=S["slope"].mean(), slope_t1=evaluate.nw_t(S["slope"] - 1, lag),
                                  icpt=S["icpt"].mean(), pooled=bp, pooled_icpt=ap, n_dates=len(S),
                                  bias=float((D["y"].clip(*CAL_CLIP) - D["x"]).mean()),
                                  mse=float(((D["y"].clip(*CAL_CLIP) - D["x"]) ** 2).mean()),
                                  dec=dec, S=S)
    return res


# ── 평가 ────────────────────────────────────────────────────────────────────

def _reg(y: pd.Series, x: pd.Series) -> tuple[float, pd.Series]:
    ok = y.notna() & x.notna()
    b, a = np.polyfit(x[ok].to_numpy(float), y[ok].to_numpy(float), 1)
    return float(b), (y[ok] - b * x[ok])


def ls_diag(R: pd.DataFrame, info: pd.DataFrame) -> tuple[dict, pd.DataFrame]:
    """라벨 롱숏 · 원수익 롱숏의 SPY 회귀(β, α, NW t) + 롱숏 ex-ante β 차."""
    M = R[["date", "ticker", "pred", "y"]].merge(info, on=["date", "ticker"])
    pf = evaluate.portfolios(M, costs=(0, 10))
    spy = M.groupby("date")["spy_fwd"].first().reindex(pf.index)
    out = {}
    for col, key in (("ls_net0", "lab0"), ("ls_net10", "lab10")):
        b, e = _reg(pf[col], spy)
        out[f"{key}_beta"] = b
        out[f"{key}_alpha_ann"] = float(e.mean() * 12)
        out[f"{key}_alpha_t"] = float(evaluate.nw_t(e))
        out[f"{key}_alpha_p"] = evaluate._p_norm(out[f"{key}_alpha_t"])
        if key == "lab10":
            for k, v in evaluate.series_stats(e, 12).items():
                out[f"alpha10_{k}"] = v
    pr = evaluate.portfolios(M.assign(y=M["y_raw"]), costs=(0,))
    b, e = _reg(pr["ls"], spy)
    out.update(raw_beta=b, raw_alpha_ann=float(e.mean() * 12), raw_alpha_t=float(evaluate.nw_t(e)),
               raw_alpha_rf_ann=float(e.mean() * 12 + b * RF_APPROX))
    for leg in ("top", "bot"):
        out[f"raw_{leg}_beta"] = _reg(pr[leg], spy)[0]
    for v in ("raw", "vas", "bbg", "cal"):
        pb = evaluate.portfolios(M.assign(y=M[f"b_{v}"]), costs=(0,))
        out[f"ante_{v}_beta"] = float(pb["ls"].mean())
    pf["spy"] = spy
    pf["raw_ls"] = pr["ls"]
    return out, pf


def bab(info: pd.DataFrame, beta_col: str = "b_bbg") -> tuple[dict, pd.Series]:
    """Frazzini–Pedersen 식 10분위 BAB: 롱 저β 분위 ÷ β_L, 숏 고β 분위 ÷ β_H (ex-ante β 중립), 원수익.
    회전 비용은 넣지 않는다(교체율만 낸다) — 진단용."""
    D = info.dropna(subset=[beta_col, "y_raw"])
    g = D.groupby("date")
    q = g[beta_col].rank(method="first", pct=True)
    lo, hi = D[q <= 0.1], D[q > 0.9]
    rl, rh = lo.groupby("date")["y_raw"].mean(), hi.groupby("date")["y_raw"].mean()
    bl, bh = lo.groupby("date")[beta_col].mean(), hi.groupby("date")[beta_col].mean()
    r = rl / bl - rh / bh
    rf_adj = RF_APPROX / 12 * (1 / bl - 1 / bh)
    spy = g["spy_fwd"].first().reindex(r.index)
    b, e = _reg(r, spy)
    out = dict(ann=float(r.mean() * 12), t=float(evaluate.nw_t(r)), beta=b, alpha_ann=float(e.mean() * 12),
               alpha_t=float(evaluate.nw_t(e)), ann_rf=float((r - rf_adj).mean() * 12),
               t_rf=float(evaluate.nw_t(r - rf_adj)), lev_l=float((1 / bl).mean()), lev_h=float((1 / bh).mean()))
    return out, r


class Ctx:
    def __init__(self):
        self.raw = raw = panel.load_raw()
        P = panel.monthly_panel().dropna(subset=["y_ex"]).reset_index(drop=True)
        self.V = V = beta_variants(raw)
        L = labels(P, raw, V)
        d = np.abs(L["y_unsh"].to_numpy() - P["y_ex"].to_numpy(float))
        assert np.nanmax(d) < 1e-5, f"라벨 a 가 panel.y_ex 와 다르다 (최대 차 {np.nanmax(d)})"
        self.P = pd.concat([P, L], axis=1)
        self.Q, self.cols = panel.prepare(P)
        for c in L.columns:
            if c.startswith("y_"):
                self.Q[c] = L[c].to_numpy()
        self.folds = cv.walk_forward(self.Q["date"], self.Q["label_end"], first_test=FIRST_TEST,
                                     refit_months=REFIT, val_months=VAL)
        if DEV:
            self.folds = self.folds[:2]
        self.test = np.concatenate([f.test for f in self.folds])
        info = self.P[["date", "ticker", "y_raw", "spy_fwd"] + [f"b_{v}" for v in ("raw", "vas", "bbg", "cal")]]
        self.info = info.assign(ticker=info["ticker"].astype(str)).iloc[self.test].reset_index(drop=True)
        self.bench = {lb: evaluate.hist_mean(self.Q, f"y_{lb}", self.Q["date"]) for lb in LABELS}
        self.res: dict[tuple, dict] = {}
        self.pf: dict[tuple, pd.DataFrame] = {}

    def oos(self, label: str, sig: str, fresh: bool) -> tuple[pd.DataFrame, bool]:
        """(예측 R, 새로 만들었나). 피처 신호는 −피처 원값, 모델은 그 라벨로 walk-forward."""
        f = OUT / f"{label}__{sig}.parquet"
        if f.exists() and not fresh:
            return pd.read_parquet(f), False
        y = f"y_{label}"
        if sig in FEATS:
            R = pd.DataFrame({"date": self.Q["date"].to_numpy()[self.test],
                              "ticker": self.Q["ticker"].astype(str).to_numpy()[self.test],
                              "y": self.Q[y].to_numpy(float)[self.test],
                              "pred": -self.P[sig].to_numpy(float)[self.test]})
        else:
            make = (lambda: baselines.RidgeCV()) if sig == "Ridge" else (lambda: GBM(1))
            R = cv.predict_oos(self.Q, self.folds, self.cols, y, make, refit_on_val=True)
            R["ticker"] = R["ticker"].astype(str)
            R = R[["date", "ticker", "y", "pred"]]
        OUT.mkdir(parents=True, exist_ok=True)
        R.to_parquet(f, index=False)
        return R, True

    def run(self, label: str, sig: str, fresh: bool):
        t0 = time.time()
        R, new = self.oos(label, sig, fresh)
        s = evaluate.summarize(R, bench=self.bench[label])
        d, pf = ls_diag(R, self.info)
        s.update(d)
        self.res[(label, sig)] = s
        self.pf[(label, sig)] = pf
        if new:
            params = dict(label=label, label_desc=LABEL_DESC[label], signal=sig,
                          kind="feature" if sig in FEATS else "model", first_test=FIRST_TEST, refit=REFIT, val=VAL)
            if sig == "GBM-d1":
                params.update({k: v for k, v in GBM(1).kw.items() if k not in ("n_jobs", "verbose")})
            registry.log(STUDY, f"{label}:{sig}", params, {**s, "fit_secs": time.time() - t0}, path=LEDGER)
            print(f"  [새로 계산] {label}:{sig} {time.time() - t0:.0f}s", flush=True)


# ── 보고 ────────────────────────────────────────────────────────────────────

def report(fresh: bool):
    ctx = Ctx()
    V, P = ctx.V, ctx.P
    print("KAN-27 — 저베타 신호는 라벨의 산물인가 (S&P 500 월말 패널, 시험 2017-01 ~)")
    print(f"패널 {len(P):,}행 · 시험 {len(ctx.test):,}행 · {ctx.info['date'].nunique()}개월")

    # (e) 보정
    print("\n[1] 베타 보정 — 월말 ex-ante β 로 다음 기간 실현 β 를 회귀 (날짜별 기울기의 평균; t 는 기울기=1 검정)")
    cal = calibration(ctx.raw, V, P)
    print("  기간  변형  날짜수  기울기 (t vs 1)  절편   풀링기울기  평균편향(실현−예측)  MSE")
    for h in ("1m", "12m"):
        for v in ("raw", "vas", "bbg", "cal"):
            c = cal[(h, v)]
            print(f"  {h:<4} {v:<4} {c['n_dates']:5d}   {c['slope']:.3f} ({c['slope_t1']:+5.1f})   {c['icpt']:+.3f}"
                  f"   {c['pooled']:.3f}       {c['bias']:+.3f}             {c['mse']:.3f}")
    print("\n  raw β 10분위별: ex-ante 평균 → 다음 12개월 실현(중앙값/평균) · 다음 1개월 실현(중앙값)")
    d12, d1 = cal[("12m", "raw")]["dec"], cal[("1m", "raw")]["dec"]
    for k in d12.index:
        print(f"   {k + 1:2d}  {d12.loc[k, 'ante']:.2f} → {d12.loc[k, 'real']:.2f} / {d12.loc[k, 'real_mean']:.2f}"
              f"   · 1m {d1.loc[k, 'real']:.2f}")
    w = V["w"].where(V["M"])
    print(f"  Vasicek 가중 w 중앙값 {np.nanmedian(w.to_numpy()):.3f} (10% {np.nanpercentile(w.to_numpy(), 10):.3f}) — "
          "250일 일간 β 는 추정오차가 작아 Vasicek 은 거의 수축하지 않는다")
    cm = pd.DataFrame(V["coef_me"], index=V["me_all"], columns=["a", "b"]).dropna()
    print(f"  경험 보정 계수 b_k (1개월 앞): 첫 {cm.index[0].date()} {cm['b'].iloc[0]:.2f} · "
          f"2017-01 {cm.loc[:'2017-01-31', 'b'].iloc[-1]:.2f} · 마지막 {cm['b'].iloc[-1]:.2f} (a {cm['a'].iloc[-1]:.2f})")

    # 라벨 간 상관
    ycols = [f"y_{lb}" for lb in LABELS]
    print("\n  라벨 상관(시험 행):")
    print(P.iloc[ctx.test][ycols].corr().round(3).to_string())

    # [2] 설정 전부
    print("\n[2] 라벨 × 신호 (IC = 라벨 기준 순위 IC; LS = 10분위 롱숏 10bp; β/α = LS 10bp 를 SPY 에 회귀)")
    for lb in LABELS:
        for sig in FEATS + MODELS:
            ctx.run(lb, sig, fresh)
    print("  라벨 신호      IC (t)          LS10 연/샤프       실현β   α연 (t)          원수익LS β  α연 (t)    ex-ante Δβ raw/vas/cal")
    for lb in LABELS:
        for sig in FEATS + MODELS:
            s = ctx.res[(lb, sig)]
            print(f"  {lb:<4} {sig:<8} {s['ic_mean']:+.4f} ({s['ic_t']:+.1f})   {s['ls_c10_ann'] * 100:+6.1f}% {s['ls_c10_sr']:+.2f}"
                  f"   {s['lab10_beta']:+.2f}  {s['lab10_alpha_ann'] * 100:+6.1f}% ({s['lab10_alpha_t']:+.2f})"
                  f"   {s['raw_beta']:+.2f}  {s['raw_alpha_ann'] * 100:+6.1f}% ({s['raw_alpha_t']:+.2f})"
                  f"   {s['ante_raw_beta']:+.2f}/{s['ante_vas_beta']:+.2f}/{s['ante_cal_beta']:+.2f}")
        print()

    # 요약 표
    print("[3] 요약 표 (라벨별)")
    print("  라벨  IC(−β)   IC(−rvol1m) IC(−rvol3m) IC(−ivol)  IC Ridge  IC GBM-d1 | Ridge: LS10 연  실현β   α t "
          "| −β 정렬: LS10 연  실현β  α연 (t)")
    for lb in LABELS:
        r = lambda s: ctx.res[(lb, s)]
        print(f"  {lb:<4} " + " ".join(f"{r(s)['ic_mean']:+.4f}({r(s)['ic_t']:+.1f})" for s in FEATS + MODELS)
              + f" | {r('Ridge')['ls_c10_ann'] * 100:+5.1f}%  {r('Ridge')['lab10_beta']:+.2f}  {r('Ridge')['lab10_alpha_t']:+.2f}"
              + f" | {r('beta')['ls_c10_ann'] * 100:+5.1f}%  {r('beta')['lab10_beta']:+.2f}"
              f"  {r('beta')['lab10_alpha_ann'] * 100:+5.1f}% ({r('beta')['lab10_alpha_t']:+.2f})")

    # 과대 헤지 분해 (−β 정렬 롱숏)
    s = ctx.res[("unsh", "beta")]
    print("\n[4] 과대 헤지 분해 — −β 정렬 10분위 롱숏 (롱 저β · 숏 고β)")
    print(f"  ex-ante Δβ (롱−숏): raw {s['ante_raw_beta']:+.2f} · Vasicek {s['ante_vas_beta']:+.2f} · "
          f"bbg {s['ante_bbg_beta']:+.2f} · 경험보정 {s['ante_cal_beta']:+.2f}")
    print(f"  사후 실현 β: 롱 {s['raw_top_beta']:.2f} · 숏 {s['raw_bot_beta']:.2f} → 롱숏 {s['raw_beta']:+.2f}")
    pf = ctx.pf[("unsh", "beta")]
    spy_ann = pf["spy"].mean() * 12
    print(f"  SPY 평균 연 {spy_ann * 100:+.1f}% → unsh 라벨이 더해 주는 기계적 수익 ≈ (실현 − ex-ante)Δβ × SPY = "
          f"{(s['raw_beta'] - s['ante_raw_beta']) * spy_ann * 100:+.1f}%/년")
    for lb in LABELS:
        x = ctx.res[(lb, "beta")]
        print(f"   {lb:<4} 라벨 LS(0bp) 연 {x['ls_c0_ann'] * 100:+6.1f}% · 남은 실현 β {x['lab0_beta']:+.2f} · "
              f"β 뺀 α {x['lab0_alpha_ann'] * 100:+5.1f}% (t {x['lab0_alpha_t']:+.2f})")
    print(f"  원수익 LS 사후 α (rf=0) {s['raw_alpha_ann'] * 100:+.1f}%/년 (t {s['raw_alpha_t']:+.2f}) · "
          f"SPY−rf 로 회귀하면(rf 연 {RF_APPROX:.1%} 근사) {s['raw_alpha_rf_ann'] * 100:+.1f}%/년")

    # 기간별
    print("\n[5] 기간별 — −β 정렬 · Ridge(unsh / cal / mkt 라벨), 원수익 LS 의 사후 β·α")
    for nm in (("unsh", "beta"), ("unsh", "rvol_1m"), ("unsh", "ivol_3m"), ("unsh", "Ridge"), ("cal", "Ridge"),
               ("mkt", "Ridge")):
        pf = ctx.pf[nm]
        row = []
        for a, b in (("2017", "2020"), ("2021", "2026"), ("2017", "2026")):
            x = pf.loc[a:b]
            if len(x) < 12:
                continue
            bb, e = _reg(x["raw_ls"], x["spy"])
            row.append(f"{a}–{b[2:]} β {bb:+.2f} α {e.mean() * 1200:+5.1f}% (t {evaluate.nw_t(e):+.1f})")
        print(f"  {nm[0]}:{nm[1]:<8} " + " · ".join(row))
    up = pf["spy"] > 0
    print(f"  (참고 Ridge-mkt 라벨 LS: SPY 상승 달 평균 {pf.loc[up, 'ls_net10'].mean() * 100:+.2f}% · 하락 달 "
          f"{pf.loc[~up, 'ls_net10'].mean() * 100:+.2f}%, 상승 {up.mean():.0%})")

    # BAB
    print("\n[6] BAB (Frazzini–Pedersen 식, ex-ante β 중립 · 원수익 · 비용 없음)")
    new_bab = not (OUT / "bab.done").exists() or fresh
    for bc in ("b_bbg", "b_cal"):
        o, r = bab(ctx.info, bc)
        print(f"  {bc}: 연 {o['ann'] * 100:+.1f}% (t {o['t']:+.2f}) · rf {RF_APPROX:.1%} 근사 반영 {o['ann_rf'] * 100:+.1f}% "
              f"(t {o['t_rf']:+.2f}) · 사후 β {o['beta']:+.2f} · α {o['alpha_ann'] * 100:+.1f}% (t {o['alpha_t']:+.2f}) · "
              f"레버리지 롱 {o['lev_l']:.2f} 숏 {o['lev_h']:.2f}")
        if new_bab:
            st = evaluate.series_stats(r, 12)
            registry.log(STUDY, f"BAB:{bc}", dict(kind="bab", beta=bc, deciles=10, costs="none"),
                         {**o, **{f"ls_c10_{k}": v for k, v in st.items()},
                          "lab10_alpha_t": o["alpha_t"], "lab10_alpha_p": evaluate._p_norm(o["alpha_t"]), "ic_p": np.nan}, path=LEDGER)
    if new_bab:
        OUT.mkdir(parents=True, exist_ok=True)
        (OUT / "bab.done").write_text("1")

    # 다중검정
    L = registry.load(STUDY, LEDGER).drop_duplicates("name", keep="last").reset_index(drop=True)
    N = registry.n_trials(STUDY, LEDGER)
    print(f"\n[7] 다중검정 — 장부 {STUDY} {N}줄 (고유 설정 {len(L)})")
    L["ic_p_holm"] = registry.holm(L["ic_p"])
    L["a_p_holm"] = registry.holm(L["lab10_alpha_p"])
    Ld = registry.deflate(L, "ls_c10", n_trials=N)
    La = registry.deflate(L.dropna(subset=["alpha10_srpp"]), "alpha10", n_trials=N)
    Ld["alpha10_dsr"] = La["alpha10_dsr"]
    Ld["alpha10_sr0"] = La["alpha10_sr0"]
    show = Ld.sort_values("lab10_alpha_t", ascending=False)
    print("  설정             IC p → Holm      β중립 α10 t   p → Holm       LS10 DSR  α10 DSR")
    for _, r in show.iterrows():
        print(f"  {r['name']:<16} {r['ic_p']:.3f} → {r['ic_p_holm']:.3f}    {r['lab10_alpha_t']:+5.2f}   "
              f"{r['lab10_alpha_p']:.3f} → {r['a_p_holm']:.3f}    {r['ls_c10_dsr']:.2f}     "
              + (f"{r['alpha10_dsr']:.2f}" if np.isfinite(r.get("alpha10_dsr", np.nan)) else "—"))
    b = Ld.loc[Ld["ls_c10_srpp"].idxmax()]
    print(f"  최고 LS10: {b['name']} 월 SR {b['ls_c10_srpp']:.3f}, SR0 {b['ls_c10_sr0']:.3f} → DSR {b['ls_c10_dsr']:.2f}")
    ba = Ld.loc[Ld["alpha10_srpp"].idxmax()]
    print(f"  최고 β중립 α: {ba['name']} 월 SR {ba['alpha10_srpp']:.3f}, SR0 {ba['alpha10_sr0']:.3f} → DSR {ba['alpha10_dsr']:.2f}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--fresh", action="store_true")
    a = ap.parse_args()
    buf = io.StringIO()

    class Tee(io.TextIOBase):
        def write(self, s):
            sys.__stdout__.write(s)
            buf.write(s)
            return len(s)

        def flush(self):
            sys.__stdout__.flush()

    t0 = time.time()
    with contextlib.redirect_stdout(Tee()):
        report(a.fresh)
        print(f"\n[총 {time.time() - t0:.0f}s]")
    REPORT.parent.mkdir(parents=True, exist_ok=True)
    REPORT.write_text(buf.getvalue())
    print(f"[저장] {REPORT}")


if __name__ == "__main__":
    main()
