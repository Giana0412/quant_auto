#!/usr/bin/env python3
"""KAN-24 — 종목 실현변동성 예측: ML(LightGBM·LSTM) 이 HAR 를 이기는가, 이긴다면 어디서.

── 왜 ──────────────────────────────────────────────────────────────────────
KAN-8(ml/headline-sentiment/forecast_vol.py)은 1개월 패널에서 HAR 의 IC 가 0.33~0.54 이고 헤드라인
피처가 아무것도 더하지 못했다. 표본이 너무 짧아 "ML 이 HAR 위에 뭔가 더하나"는 답하지 못했다.
여기서는 12년 S&P 500 일간 패널(편입 이력 반영)로 같은 질문을 제대로 묻는다. 문헌 기대치
(Christensen, Siggaard & Veliyev 2023): 이득은 작지만 유의하고, 주로 비선형·레버리지 효과에서 온다.
여기에 일간 데이터에서 가장 큰 예측 가능한 변동성 사건 — **실적 발표** — 를 더한다(HAR 는 달력을 모른다).

── 정의 ────────────────────────────────────────────────────────────────────
행          panel.daily_panel 의 (세션 t, 편입 종목). 피처는 전부 t 종가까지.
라벨        RV_h = rv_fwd_h² = (t+1 … t+h 세션 r²)의 평균 (분산, 일간 단위).
            y_h = log(max(RV_h, FLOOR)), FLOOR = 1e-7 (≈ 3bp 일간 움직임). h=1 은 r²_{t+1} 하나라서
            log 는 매우 시끄럽다(log χ²₁) — h=1 의 1차 손실은 QLIKE 로 읽는다(Patton 2011: 시끄러운 대용치에서도
            순위가 보존되는 손실은 MSE(분산)·QLIKE 뿐, log-MSE 는 아니다).
손실        MSE-logRV = (y − ŷ_log)²,  QLIKE(RV, f) = RV/f − log(RV/f) − 1 (분산 단위, evaluate.loss_qlike).
            두 예측을 낸다: ŷ_log(로그 단위 예측) 과 f = exp(ŷ_raw)·c (분산 예측).
            c = 검증 구간에서 mean(RV / exp(ŷ_raw)) — QLIKE 를 최소로 하는 배율(젠센 보정). 모든 모델 동일.
CV          cv.walk_forward(date, label_end_h, first_test=2017-01, refit 12개월, val 12개월).
            🔴 퍼지: 학습 행은 label_end_h ≤ 검증·시험 시작. 모든 모델은 **안쪽 학습(train)** 으로만 적합,
            검증(val)은 LightGBM·LSTM 조기 종료와 배율 c 에만 쓴다 — 선형 모델도 같은 데이터만 본다(공정 비교).
비교        날짜별 횡단면 평균 손실 → evaluate.diebold_mariano(h=h, HLN 보정) vs HAR(pooled).
            순위 IC = 날짜별 스피어만(ŷ, RV) → NW t. Holm 은 DM p 전부(모델 × h × 손실)를 한 가족으로.

모델 (전부 같은 행·같은 폴드)
  HAR        y_h ~ 1 + lv1 + lv5 + lv22,  lv_n = log(rv_n²) (lv1 = log r_t²), 종목 풀링 OLS (Corsi 2009)
  HAR-stock  같은 식을 종목별 OLS (학습 250행 미만 종목은 풀링 계수)
  HAR-mkt    HAR + SPY 의 lv1·lv5·lv22
  EWMA       RiskMetrics σ²_t = 0.94 σ²_{t−1} + 0.06 r_t², 모든 h 에 같은 값. 로그 예측 = log σ² + 검증 평균 잔차.
  HARX-lin   아래 전체 피처를 넣은 선형 OLS — "정보"와 "비선형"을 가르는 대조군
  LGBM-HAR   HAR 피처 3개만 넣은 LightGBM — 비선형만의 몫
  LGBM-full  HAR + lv66 + 시장 + β + 레버리지 + 실적 + 거래대금
  LGBM-noearn / LGBM-nolev   전체에서 실적 묶음 / 레버리지 묶음을 뺀 것 (어디서 이득이 오나)
  LGBM-sched 전체 + "확정 발표일" 피처 (아래 🔴 가정, 민감도 분석 — 주 결과 아님)
  LSTM       종목별 최근 60세션 [r, log r², r_SPY] → 1층 LSTM(32) → 세 h 동시 출력. 종목 풀링,
             폴드마다 학습 15만 행 표본, 검증 3만 행 조기 종료. h=22 폴드(가장 엄격한 퍼지)로 학습.

피처 묶음
  레버리지   r, min(r,0), 5·22세션 누적수익, 5·22세션 하방 준분산 √mean(r²·1{r<0}) (Patton–Sheppard),
             SPY r·min(r,0)·5세션 누적
  실적       days_to_exp, sess_to_exp, exp_near_h, days_since_ann (아래)
  기타       lv66, β(250일), log 22세션 평균 거래대금

── 🔴 실적 발표일: 사전에 알려진 것만 ─────────────────────────────────────────
events 의 d0 는 **실제** 반응일이다. "다음 발표까지 며칠"을 실제 다음 d0 로 계산하면 미래 정보다
(회사는 보통 2~5주 전에 일정을 공지하지만, 연기·변경도 있고 공지 시점 이력은 우리에게 없다).
그래서 주 피처는 t 에 이미 일어난 발표만으로 **투영**한다:
  next_exp = d0_{n−3} + 364일   (n = t 까지의 마지막 발표, n−3 = 1년 전 같은 분기 발표)
             그 값이 d0_n + 30일 이하이거나 이력이 4건 미만이면  d0_n + 91일
  days_to_exp = next_exp − t (달력일, 음수 = 예정일을 지났는데 아직 발표 없음 = 임박)
  sess_to_exp = next_exp 이상 첫 세션까지의 세션 수 (거래소 휴장일은 미리 알려진 달력이다)
  exp_near_h = sess_to_exp ∈ [−3, h+2]
투영 정확도는 출력에 적는다(실제 다음 d0 와의 오차).
LGBM-sched (민감도): 실제 다음 d0 가 14달력일 이내면 그 날까지 세션 수, 아니면 NaN.
  🔴 가정: S&P 500 기업은 발표일을 최소 2주 전에 확정·공지한다. 대부분 맞지만 보장되지 않는다
  (공지 이력이 없어 검증 불가) → 이 모델은 주 결과·Holm 가족에서 빼고 따로 적는다.

── 손실 분해 (어디서 이기나) ──────────────────────────────────────────────────
pre-earn   라벨 창 t+1…t+h 안에 **실제** 발표 반응일이 있는 행 (평가용 그룹 — 사후 정보로 나눠도 된다)
high-vol   mkt_rv_22 가 시험 기간 날짜들 중 상위 10% 인 날
size       날짜별 22세션 거래대금 상위 1/3 vs 하위 1/3
그룹마다 날짜별 평균 손실 → HAR 대비 손실 변화율과 DM t.

── VaR (경제적 가치) ──────────────────────────────────────────────────────────
1일 99% VaR = q·σ̂ (σ̂ = h=1 분산 예측의 √). q 는 정규(2.326)와 필터드 HS(검증 구간 r_{t+1}/σ̂ 의 1% 분위)
둘 다. 위반 = r_{t+1} < −VaR. 풀링 위반율, Kupiec POF LR(🔴 종목끼리 위반이 같은 날 몰리므로 풀링 검정은
과대 유의 — 참고용), 종목별 Kupiec 기각 비율(5%).

── 한계 ──────────────────────────────────────────────────────────────────
· RV 는 일간 수익 제곱으로 만든 대용치(장중 자료 없음) — h=1 라벨은 r² 하나라 잡음이 크다.
· 생존 편향(편출 종목 중 가격이 남은 것만), 상폐 직전 라벨 창은 NaN.
· 시가총액 대신 거래대금, 업종 없음. 발표일 이력은 Yahoo 가 지금 저장한 값.
· 블록(1년) 안에서 모델 고정, 최근 12개월(검증)은 적합에 안 쓴다 — 모든 모델이 같다.

실행 (ml/ 에서):
  ../headline-sentiment/.venv/bin/python -m research.vol fit            # 예측 계산·캐시·장부 기록
  ../headline-sentiment/.venv/bin/python -m research.vol fit --only LSTM
  ../headline-sentiment/.venv/bin/python -m research.vol report         # DM·분해·VaR·Holm → runs/vol.txt
"""
from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd

from . import cv, evaluate, panel, registry

STUDY = "kan-24-vol"
HORIZONS = (1, 5, 22)
FLOOR = 1e-7
FIRST_TEST = "2017-01-01"
SEED = 24
OUT = panel.RUNS / "vol"

HAR = ["lv1", "lv5", "lv22"]
MKT = ["mlv1", "mlv5", "mlv22"]
LEV = ["r", "r_neg", "ret_5", "ret_22", "rsn_5", "rsn_22", "mkt_r", "mkt_r_neg", "mkt_ret_5"]
EARN = ["days_to_exp", "sess_to_exp", "exp_near_{h}", "days_since_ann"]
OTHER = ["lv66", "beta", "ldvol"]


def _log_var(x):
    return np.log(np.maximum(np.asarray(x, "float64") ** 2, FLOOR)).astype("float32")


# ── 데이터 ────────────────────────────────────────────────────────────────

def _earnings(raw: panel.Raw, t_idx: np.ndarray, j_idx: np.ndarray, sessions: pd.DatetimeIndex) -> dict:
    """행별 실적 피처 (사전 투영) + 평가용 실제 다음 반응일까지 세션 수."""
    E = panel._events(raw)
    n = len(t_idx)
    out = {k: np.full(n, np.nan) for k in ("days_to_exp", "sess_to_exp", "days_since_ann", "sess_to_actual",
                                           "days_to_actual", "proj_err")}
    sess = sessions.to_numpy().astype("datetime64[D]")
    rows = pd.Series(np.arange(n)).groupby(j_idx)
    ev = {j: g.sort_values("i0") for j, g in E.groupby("j")}
    for j, ix in rows:
        ix = ix.to_numpy()
        g = ev.get(j)
        if g is None or not len(g):
            continue
        i0 = g["i0"].to_numpy()
        d0 = g["d0"].to_numpy().astype("datetime64[D]")
        t = t_idx[ix]
        td = sess[t]
        pos = np.searchsorted(i0, t, side="right") - 1          # 🔴 i0 ≤ t 인 마지막 발표 (t 종가에 이미 반응)
        has = pos >= 0
        p = np.maximum(pos, 0)
        d_last = d0[p]
        ya_ok = has & (pos >= 3)
        ya = np.where(ya_ok, d0[np.maximum(pos - 3, 0)] + np.timedelta64(364, "D"), np.datetime64("NaT", "D"))
        q91 = d_last + np.timedelta64(91, "D")
        use_ya = ya_ok & (ya > d_last + np.timedelta64(30, "D"))
        nxt = np.where(use_ya, ya, q91)
        dte = (nxt - td).astype(float)
        ste = np.searchsorted(sess, nxt, side="left").astype(float) - t
        o = has
        out["days_to_exp"][ix[o]] = dte[o]
        out["sess_to_exp"][ix[o]] = ste[o]
        out["days_since_ann"][ix[o]] = (td - d_last).astype(float)[o]
        # 평가·민감도용: 실제 다음 반응일 (🔴 피처로는 LGBM-sched 의 14일 창 안에서만)
        nx = pos + 1
        ok = nx < len(i0)
        k = ix[ok]
        out["sess_to_actual"][k] = i0[nx[ok]] - t[ok]
        out["days_to_actual"][k] = (d0[nx[ok]] - td[ok]).astype(float)
        out["proj_err"][ix[ok & has]] = (nxt[ok & has] - d0[nx[ok & has]]).astype(float)
    return out


def build(verbose: bool = True) -> pd.DataFrame:
    """일간 패널 + 피처·라벨·분해 변수. 행 순서는 daily_panel 과 같다(핵심 피처가 있는 행만)."""
    t0 = time.time()
    P = panel.daily_panel(horizons=HORIZONS)
    P = P[np.isfinite(P[["abs_r", "rv_5", "rv_22", "rv_66"]]).all(axis=1)].reset_index(drop=True)
    raw = panel.load_raw()
    C, V = raw.C, raw.V
    sessions = raw.sessions
    t_idx = sessions.get_indexer(pd.DatetimeIndex(P["date"]))
    j_idx = C.columns.get_indexer(P["ticker"].astype(str))
    assert (t_idx >= 0).all() and (j_idx >= 0).all()
    R = C.pct_change(fill_method=None)
    R2 = R ** 2
    neg2 = R2.where(R < 0, 0.0).where(R.notna())
    W = {
        "ret_5": R.rolling(5, min_periods=4).sum(),
        "ret_22": R.rolling(22, min_periods=15).sum(),
        "rsn_5": np.sqrt(neg2.rolling(5, min_periods=4).mean()),
        "rsn_22": np.sqrt(neg2.rolling(22, min_periods=15).mean()),
        "ldvol": np.log((C * V).rolling(22, min_periods=15).mean().replace(0, np.nan)),
        # RiskMetrics: σ²_t 는 r_t 까지 (t 종가) — t+1 이후 예측
        "ewma": R2.ewm(alpha=0.06, adjust=False, ignore_na=True).mean(),
    }
    D = pd.DataFrame({"date": P["date"].to_numpy(), "ticker": P["ticker"], "t": t_idx.astype("int32"),
                      "j": j_idx.astype("int32")})
    for k, v in W.items():
        D[k] = v.to_numpy(dtype="float64")[t_idx, j_idx].astype("float32")
    D["mkt_ret_5"] = R["SPY"].rolling(5, min_periods=4).sum().to_numpy()[t_idx].astype("float32")
    D["r"], D["mkt_r"], D["beta"] = P["r"].to_numpy(), P["mkt_r"].to_numpy(), P["beta"].to_numpy()
    D["r_neg"] = np.minimum(D["r"], 0)
    D["mkt_r_neg"] = np.minimum(D["mkt_r"], 0)
    D["lv1"], D["lv5"], D["lv22"], D["lv66"] = (_log_var(P[c]) for c in ("abs_r", "rv_5", "rv_22", "rv_66"))
    D["mlv1"] = _log_var(P["mkt_r"].abs())
    D["mlv5"], D["mlv22"] = _log_var(P["mkt_rv_5"]), _log_var(P["mkt_rv_22"])
    D["mkt_rv_22"] = P["mkt_rv_22"].to_numpy()
    D["lewma"] = np.log(np.maximum(D["ewma"].astype("float64"), FLOOR)).astype("float32")
    ea = _earnings(raw, t_idx, j_idx, sessions)
    for k, v in ea.items():
        D[k] = v.astype("float32")
    D["days_to_exp"] = D["days_to_exp"].clip(-30, 120)
    D["sess_to_exp"] = D["sess_to_exp"].clip(-20, 90)
    for h in HORIZONS:
        s = D["sess_to_exp"]
        D[f"exp_near_{h}"] = ((s >= -3) & (s <= h + 2)).astype("float32")
        # 🔴 민감도 피처: 실제 다음 반응일 — 14 달력일 이내일 때만 (사전 공지 가정)
        D[f"sched_{h}"] = np.where(D["days_to_actual"] <= 14, D["sess_to_actual"], np.nan).astype("float32")
        a = D["sess_to_actual"]
        D[f"pre_earn_{h}"] = ((a >= 1) & (a <= h)).to_numpy()
        rv = P[f"rv_fwd_{h}"].to_numpy("float64") ** 2
        D[f"rv_{h}"] = rv
        D[f"y_{h}"] = np.log(np.maximum(rv, FLOOR))
        D[f"label_end_{h}"] = P[f"label_end_{h}"].to_numpy()
    # VaR 용 t+1 수익
    D["r_next"] = R.shift(-1).to_numpy(dtype="float64")[t_idx, j_idx]
    if verbose:
        print(f"  build: {len(D):,}행 · 세션 {D['date'].nunique():,} · 티커 {D['ticker'].nunique()} · "
              f"{D.memory_usage(deep=True).sum() / 1e6:.0f}MB · {time.time() - t0:.0f}초")
    return D


def features(name: str, h: int) -> list[str]:
    earn = [c.format(h=h) for c in EARN]
    full = HAR + OTHER + MKT + LEV + earn
    return {
        "HAR": HAR, "HAR-stock": HAR, "HAR-mkt": HAR + MKT, "EWMA": ["lewma"],
        "HARX-lin": full, "LGBM-HAR": HAR, "LGBM-full": full,
        "LGBM-noearn": [c for c in full if c not in earn],
        "LGBM-nolev": [c for c in full if c not in LEV],
        "LGBM-sched": full + [f"sched_{h}"],
    }[name]


# ── 모델 ────────────────────────────────────────────────────────────────

class OLS:
    """절편 포함 최소제곱. NaN 피처는 학습 중앙값으로 대체(🔴 학습 구간 통계만)."""
    def fit(self, X, y, Xv=None, yv=None):
        self.med = np.nanmedian(X, axis=0)
        A = self._a(X)
        self.b = np.linalg.lstsq(A, y, rcond=None)[0]
        return self

    def _a(self, X):
        X = np.where(np.isfinite(X), X, self.med).astype("float64")
        return np.column_stack([np.ones(len(X)), X])

    def predict(self, X):
        return self._a(X) @ self.b


class StockOLS:
    """종목별 HAR. 마지막 열 = 종목 번호 j. 학습 min_n 행 미만 종목은 풀링 계수."""
    def __init__(self, min_n: int = 250):
        self.min_n = min_n

    def fit(self, X, y, Xv=None, yv=None):
        j, X = X[:, -1].astype(int), X[:, :-1]
        self.pool = OLS().fit(X, y)
        self.coef = {}
        A = self.pool._a(X)
        order = np.argsort(j, kind="stable")
        js, starts = np.unique(j[order], return_index=True)
        for k, (jj, s) in enumerate(zip(js, starts)):
            e = starts[k + 1] if k + 1 < len(starts) else len(order)
            ix = order[s:e]
            if len(ix) >= self.min_n:
                self.coef[jj] = np.linalg.lstsq(A[ix], y[ix], rcond=None)[0]
        return self

    def predict(self, X):
        j, X = X[:, -1].astype(int), X[:, :-1]
        A = self.pool._a(X)
        out = A @ self.pool.b
        for jj in np.unique(j):
            if jj in self.coef:
                m = j == jj
                out[m] = A[m] @ self.coef[jj]
        return out


class Ident:
    """EWMA: 예측 = 피처 그대로 (적합 없음)."""
    def fit(self, X, y, Xv=None, yv=None):
        return self

    def predict(self, X):
        return np.asarray(X[:, 0], float)


class LGBM:
    """LightGBM 회귀 (L2, log RV). 학습 max_rows 행 무작위 표본, 검증으로 조기 종료."""
    def __init__(self, max_rows: int = 300_000, seed: int = SEED):
        self.max_rows, self.seed = max_rows, seed

    def fit(self, X, y, Xv=None, yv=None):
        import lightgbm as lgb
        rng = np.random.default_rng(self.seed)
        if len(X) > self.max_rows:
            ix = np.sort(rng.choice(len(X), self.max_rows, replace=False))
            X, y = X[ix], y[ix]
        if Xv is not None and len(Xv) > 100_000:
            iv = np.sort(rng.choice(len(Xv), 100_000, replace=False))
            Xv, yv = Xv[iv], yv[iv]
        self.m = lgb.LGBMRegressor(n_estimators=600, learning_rate=0.05, num_leaves=31, min_child_samples=500,
                                   subsample=0.8, subsample_freq=1, colsample_bytree=0.8, reg_lambda=1.0,
                                   random_state=self.seed, n_jobs=6, verbose=-1)
        self.m.fit(X, y, eval_set=[(Xv, yv)], callbacks=[lgb.early_stopping(50, verbose=False)])
        return self

    def predict(self, X):
        return self.m.predict(X)


def _run(D: pd.DataFrame, folds, cols: list[str], h: int, make, shift_on_val: bool = False):
    """폴드마다 적합(train) → 검증으로 배율 c (와 EWMA 는 로그 이동 b) → 시험 예측.
    반환: (pred_log, pred_var) — D 와 같은 길이, 시험 행만 값."""
    X = D[cols].to_numpy("float32")
    y, rv = D[f"y_{h}"].to_numpy(), D[f"rv_{h}"].to_numpy()
    pl, pv = np.full(len(D), np.nan), np.full(len(D), np.nan)
    for f in folds:
        tr = f.train[np.isfinite(y[f.train])]
        va = f.val[np.isfinite(y[f.val])]
        m = make().fit(X[tr], y[tr], X[va], y[va])
        gv = m.predict(X[va])
        b = float(np.mean(y[va] - gv)) if shift_on_val else 0.0
        c = float(np.mean(rv[va] / np.exp(gv)))
        g = m.predict(X[f.test])
        pl[f.test] = g + b
        pv[f.test] = np.exp(g) * c
    return pl, pv


# ── LSTM ────────────────────────────────────────────────────────────────

LOOK = 60


def _seq_inputs(raw_R: np.ndarray, mkt: np.ndarray):
    """세션×티커 수익 → 채널 [r·100 클립, (log(r²+FLOOR)+9)/3, r_SPY·100]. NaN 은 0."""
    r = np.nan_to_num(raw_R, nan=0.0)
    a = np.clip(r * 100, -25, 25).astype("float32")
    b = ((np.log(r ** 2 + FLOOR) + 9) / 3).astype("float32")
    m = np.clip(np.nan_to_num(mkt) * 100, -25, 25).astype("float32")
    return a, b, m


def _seqs(t, j, A, B, M):
    ix = t[:, None] + np.arange(-LOOK + 1, 1)[None, :]
    return np.stack([A[ix, j[:, None]], B[ix, j[:, None]], M[ix]], axis=-1)


def run_lstm(D: pd.DataFrame, folds_by_h: dict, verbose: bool = True):
    import torch
    torch.manual_seed(SEED)
    torch.set_num_threads(6)
    raw = panel.load_raw()
    R = raw.C.pct_change(fill_method=None)
    A, B, M = _seq_inputs(R.to_numpy(), R["SPY"].to_numpy())
    t_all, j_all = D["t"].to_numpy(), D["j"].to_numpy()
    assert t_all.min() >= LOOK - 1
    Y = np.column_stack([D[f"y_{h}"].to_numpy() for h in HORIZONS])
    RV = np.column_stack([D[f"rv_{h}"].to_numpy() for h in HORIZONS])
    out = {h: (np.full(len(D), np.nan), np.full(len(D), np.nan)) for h in HORIZONS}
    rng = np.random.default_rng(SEED)

    class Net(torch.nn.Module):
        def __init__(self):
            super().__init__()
            self.lstm = torch.nn.LSTM(3, 32, batch_first=True)
            self.head = torch.nn.Linear(32, len(HORIZONS))

        def forward(self, x):
            o, _ = self.lstm(x)
            return self.head(o[:, -1])

    def pred(net, ix, mu, sd):
        net.eval()
        res = []
        with torch.no_grad():
            for s in range(0, len(ix), 16384):
                k = ix[s:s + 16384]
                res.append(net(torch.from_numpy(_seqs(t_all[k], j_all[k], A, B, M))).numpy())
        return np.concatenate(res) * sd + mu

    # 🔴 세 h 를 한 모델로 → 가장 엄격한 퍼지(h=22)의 폴드로 학습. 시험 블록은 h 와 무관하게 같다.
    for f in folds_by_h[max(HORIZONS)]:
        t0 = time.time()
        ok = lambda ix: ix[np.isfinite(Y[ix]).all(axis=1)]
        tr, va = ok(f.train), ok(f.val)
        tr = np.sort(rng.choice(tr, min(150_000, len(tr)), replace=False))
        vs = np.sort(rng.choice(va, min(30_000, len(va)), replace=False))
        mu, sd = Y[tr].mean(0), Y[tr].std(0)
        Xv = torch.from_numpy(_seqs(t_all[vs], j_all[vs], A, B, M))
        Yv = torch.from_numpy(((Y[vs] - mu) / sd).astype("float32"))
        net = Net()
        opt = torch.optim.Adam(net.parameters(), lr=2e-3)
        best, best_state, bad = np.inf, None, 0
        for ep in range(8):
            net.train()
            perm = rng.permutation(tr)
            for s in range(0, len(perm), 512):
                k = perm[s:s + 512]
                xb = torch.from_numpy(_seqs(t_all[k], j_all[k], A, B, M))
                yb = torch.from_numpy(((Y[k] - mu) / sd).astype("float32"))
                opt.zero_grad()
                loss = torch.mean((net(xb) - yb) ** 2)
                loss.backward()
                opt.step()
            net.eval()
            with torch.no_grad():
                vl = float(torch.mean((net(Xv) - Yv) ** 2))
            if vl < best - 1e-4:
                best, bad = vl, 0
                best_state = {k: v.clone() for k, v in net.state_dict().items()}
            else:
                bad += 1
                if bad >= 2:
                    break
        net.load_state_dict(best_state)
        gv = pred(net, va, mu, sd)
        g = pred(net, f.test, mu, sd)
        for i, h in enumerate(HORIZONS):
            c = float(np.mean(RV[va, i] / np.exp(gv[:, i])))
            out[h][0][f.test] = g[:, i]
            out[h][1][f.test] = np.exp(g[:, i]) * c
        if verbose:
            print(f"    LSTM fold {f.k} {f.test_start.date()} ep {ep + 1} val {best:.4f} · {time.time() - t0:.0f}초", flush=True)
    return out


# ── 평가 ────────────────────────────────────────────────────────────────

def losses(D, h, pl, pv):
    y, rv = D[f"y_{h}"].to_numpy(), D[f"rv_{h}"].to_numpy()
    return evaluate.loss_mse(y, pl), evaluate.loss_qlike(np.maximum(rv, FLOOR), pv)


def eval_mask(D, h, preds: dict) -> np.ndarray:
    """모든 모델 예측·라벨이 있는 행 (공통 표본)."""
    m = np.isfinite(D[f"y_{h}"].to_numpy())
    for pl, pv in preds.values():
        m &= np.isfinite(pl) & np.isfinite(pv)
    return m


def metrics(D, h, pl, pv, mask) -> dict:
    lm, lq = losses(D, h, pl, pv)
    Rr = pd.DataFrame({"date": D["date"].to_numpy()[mask], "pred": pl[mask], "y": D[f"rv_{h}"].to_numpy()[mask]})
    ic = evaluate.ic_summary(evaluate.rank_ic(Rr))
    return dict(mse_log=float(np.mean(lm[mask])), qlike=float(np.mean(lq[mask])), n_rows=int(mask.sum()),
                n_dates=int(Rr["date"].nunique()), **ic)


def daily(D, mask, x) -> pd.Series:
    return pd.Series(x[mask]).groupby(D["date"].to_numpy()[mask]).mean()


def kupiec(n_exc: int, n: int, p: float = 0.01) -> tuple[float, float]:
    from scipy.stats import chi2
    if n == 0:
        return np.nan, np.nan
    x = n_exc
    pi = x / n
    ll0 = (n - x) * np.log(1 - p) + x * np.log(p)
    ll1 = ((n - x) * np.log(1 - pi) if pi < 1 else 0) + (x * np.log(pi) if x > 0 else 0)
    lr = -2 * (ll0 - ll1)
    return float(lr), float(chi2.sf(lr, 1))


# ── 실행 ────────────────────────────────────────────────────────────────

MODELS = ["HAR", "HAR-stock", "HAR-mkt", "EWMA", "HARX-lin", "LGBM-HAR", "LGBM-full", "LGBM-noearn",
          "LGBM-nolev", "LGBM-sched", "LSTM"]
SENSITIVITY = {"LGBM-sched"}          # 🔴 사전 공지 가정 — Holm 가족·주 결과 밖


def _make(name):
    if name == "HAR-stock":
        return StockOLS
    if name == "EWMA":
        return Ident
    if name.startswith("LGBM"):
        return LGBM
    return OLS


def folds_for(D):
    return {h: cv.walk_forward(D["date"], D[f"label_end_{h}"], first_test=FIRST_TEST, refit_months=12,
                               val_months=12) for h in HORIZONS}


def _path(name, h):
    return OUT / f"pred_{name}_h{h}.npz"


def fit(only=None):
    OUT.mkdir(parents=True, exist_ok=True)
    D = build()
    F = folds_for(D)
    print(f"  폴드 {len(F[1])}개: {F[1][0]} … {F[1][-1]}")
    for name in (only or MODELS):
        t0 = time.time()
        if name == "LSTM":
            res = run_lstm(D, F)
        else:
            res = {}
            for h in HORIZONS:
                cols = features(name, h) + (["j"] if name == "HAR-stock" else [])
                res[h] = _run(D, F[h], cols, h, _make(name), shift_on_val=(name == "EWMA"))
        for h in HORIZONS:
            pl, pv = res[h]
            np.savez_compressed(_path(name, h), pl=pl.astype("float32"), pv=pv.astype("float64"))
            mask = np.isfinite(D[f"y_{h}"].to_numpy()) & np.isfinite(pl)
            m = metrics(D, h, pl, pv, mask)
            registry.log(STUDY, f"{name}-h{h}", dict(model=name, h=h, features=features(name, h) if name != "LSTM" else
                                                     f"seq{LOOK}[r,logr2,mkt]", first_test=FIRST_TEST, refit=12,
                                                     val=12, floor=FLOOR), m)
            print(f"  {name:<12} h={h:<2} MSE-log {m['mse_log']:.4f} QLIKE {m['qlike']:.4f} IC {m['ic_mean']:+.3f}"
                  f" ({time.time() - t0:.0f}초)", flush=True)


def load_preds(D):
    P = {}
    for name in MODELS:
        for h in HORIZONS:
            p = _path(name, h)
            if p.exists():
                z = np.load(p)
                P[(name, h)] = (z["pl"].astype("float64"), z["pv"])
    return P


def report():
    lines = []

    def say(s=""):
        print(s, flush=True)
        lines.append(s)

    D = build(verbose=False)
    P = load_preds(D)
    names = [n for n in MODELS if all((n, h) in P for h in HORIZONS)]
    say(f"KAN-24 변동성 예측 — {pd.Timestamp.now():%Y-%m-%d %H:%M} · 시험 {FIRST_TEST} ~ {D['date'].max():%Y-%m-%d}")
    say(f"패널 {len(D):,}행 · 티커 {D['ticker'].nunique()} · 모델 {len(names)}개 · 장부 시도 수 N = {registry.n_trials(STUDY)}")
    pe = D["proj_err"].to_numpy()
    near = np.isfinite(pe) & (D["days_to_actual"].to_numpy() <= 30)
    say(f"실적 투영 정확도 (실제 다음 발표가 30일 안인 행): |오차| 중앙값 {np.nanmedian(np.abs(pe[near])):.0f}일 · "
        f"±3일 {np.mean(np.abs(pe[near]) <= 3):.0%} · ±7일 {np.mean(np.abs(pe[near]) <= 7):.0%}")
    rows = []
    split_rows = []
    for h in HORIZONS:
        preds = {n: P[(n, h)] for n in names}
        mask = eval_mask(D, h, preds)
        base_m, base_q = losses(D, h, *preds["HAR"])
        bm, bq = daily(D, mask, base_m), daily(D, mask, base_q)
        say()
        say(f"── h = {h} ─ 공통 표본 {mask.sum():,}행 · {D['date'][mask].nunique():,}일 " + "─" * 30)
        say(f"  {'모델':<12} {'MSE-log':>8} {'Δ%':>6} {'DM t':>6} {'QLIKE':>7} {'Δ%':>6} {'DM t':>6} {'IC':>6} {'IC t':>6}")
        for n in names:
            pl, pv = preds[n]
            m = metrics(D, h, pl, pv, mask)
            lm, lq = losses(D, h, pl, pv)
            r = dict(model=n, h=h, mse_log=m["mse_log"], qlike=m["qlike"], ic=m["ic_mean"], ic_t=m["ic_t"])
            for key, l, b in (("mse", lm, bm), ("qlike", lq, bq)):
                dl = daily(D, mask, l)
                dm = evaluate.diebold_mariano(dl, b, h=h) if n != "HAR" else dict(stat=np.nan, p=np.nan)
                r[f"{key}_imp"] = float(1 - dl.mean() / b.mean()) * 100
                r[f"{key}_dm"], r[f"{key}_p"] = dm["stat"], dm["p"]
            rows.append(r)
            say(f"  {n:<12} {r['mse_log']:8.4f} {r['mse_imp']:+6.2f} {r['mse_dm']:+6.2f} {r['qlike']:7.4f} "
                f"{r['qlike_imp']:+6.2f} {r['qlike_dm']:+6.2f} {r['ic']:+6.3f} {r['ic_t']:+6.1f}")
        # 같은 정보에서 비선형만의 몫: LGBM-full vs HARX-lin (기준 = 선형). Holm 가족에 넣는다.
        for a_, b_ in (("LGBM-full", "HARX-lin"), ("LSTM", "HARX-lin")):
            if a_ in names and b_ in names:
                r = dict(model=f"{a_}|vs-{b_}", h=h)
                la_m, la_q = losses(D, h, *preds[a_])
                lb_m, lb_q = losses(D, h, *preds[b_])
                for key, la, lb in (("mse", la_m, lb_m), ("qlike", la_q, lb_q)):
                    x, y_ = daily(D, mask, la), daily(D, mask, lb)
                    dm = evaluate.diebold_mariano(x, y_, h=h)
                    r[f"{key}_imp"] = float(1 - x.mean() / y_.mean()) * 100
                    r[f"{key}_dm"], r[f"{key}_p"] = dm["stat"], dm["p"]
                rows.append(r)
                say(f"  {a_} vs {b_}: MSE-log Δ {r['mse_imp']:+.2f}% (DM {r['mse_dm']:+.2f}) · "
                    f"QLIKE Δ {r['qlike_imp']:+.2f}% (DM {r['qlike_dm']:+.2f})")
        # 분해
        dvr = D.groupby("date")["ldvol"].rank(pct=True).to_numpy()
        mv = D["mkt_rv_22"].to_numpy()
        dmv = pd.Series(mv[mask]).groupby(D["date"].to_numpy()[mask]).first()
        hi_days = dmv.index[dmv >= dmv.quantile(0.9)]
        hi = np.isin(D["date"].to_numpy(), hi_days.to_numpy())
        pre = D[f"pre_earn_{h}"].to_numpy()
        groups = {"pre-earn": pre, "no-earn": ~pre, "high-vol": hi, "calm": ~hi,
                  "big-dvol": dvr > 2 / 3, "small-dvol": dvr <= 1 / 3}
        say(f"  분해 (HAR 대비 손실 변화 %, 음수 = 개선 · DM t)   행 비율: pre-earn {pre[mask].mean():.1%} · high-vol {hi[mask].mean():.1%}")
        say(f"  {'모델':<12} " + " ".join(f"{g:>17}" for g in groups))
        for n in [x for x in names if x != "HAR"]:
            lm, lq = losses(D, h, *preds[n])
            cells = []
            for g, gm in groups.items():
                mm = mask & gm
                a, b = daily(D, mm, lq), daily(D, mm, base_q)
                a2, b2 = daily(D, mm, lm), daily(D, mm, base_m)
                dq = evaluate.diebold_mariano(a, b, h=h)
                dmse = evaluate.diebold_mariano(a2, b2, h=h)
                share = float(np.sum(lq[mm] - base_q[mm]) / np.sum(lq[mask] - base_q[mask])) if n != "HAR" else np.nan
                split_rows.append(dict(model=n, h=h, group=g, qlike_chg=(a.mean() / b.mean() - 1) * 100, qlike_dm=dq["stat"],
                                       mse_chg=(a2.mean() / b2.mean() - 1) * 100, mse_dm=dmse["stat"], share_qlike_gain=share,
                                       rows=int(mm.sum())))
                cells.append(f"Q{(a.mean() / b.mean() - 1) * 100:+5.1f}({dq['stat']:+5.1f})")
            say(f"  {n:<12} " + " ".join(f"{c:>17}" for c in cells))
        say("  (Q = QLIKE 변화 %, 괄호 = DM t. MSE-log 분해는 아래 표)")
        say(f"  {'모델':<12} " + " ".join(f"{g:>17}" for g in groups))
        for n in [x for x in names if x != "HAR"]:
            cs = [s for s in split_rows if s["model"] == n and s["h"] == h]
            say(f"  {n:<12} " + " ".join(f"{'M' + format(s['mse_chg'], '+5.1f') + '(' + format(s['mse_dm'], '+5.1f') + ')':>17}" for s in cs))
        # 이득 중 pre-earn 행에서 온 몫
        for n in ("LGBM-full", "LGBM-HAR", "HARX-lin", "LSTM"):
            if n in names:
                lm, lq = losses(D, h, *preds[n])
                tot = np.sum(lq[mask] - base_q[mask])
                pe_ = np.sum((lq - base_q)[mask & pre])
                say(f"  {n}: QLIKE 총 이득 중 pre-earn 행 몫 {pe_ / tot:.0%} (pre-earn 행 비율 {pre[mask].mean():.1%})")
    T = pd.DataFrame(rows)
    # Holm: 주 결과 모델 × h × 손실 (HAR 자신·민감도 제외)
    fam = T[(T["model"] != "HAR") & (~T["model"].isin(SENSITIVITY))]
    pv = np.concatenate([fam["mse_p"].to_numpy(), fam["qlike_p"].to_numpy()])
    adj = registry.holm(pv)
    k = len(fam)
    T.loc[fam.index, "mse_holm"] = adj[:k]
    T.loc[fam.index, "qlike_holm"] = adj[k:]
    say()
    say(f"── Holm (가족 = {len(pv)}개 DM 비교: {fam['model'].nunique()}개 비교(HAR 대비 9 + vs-HARX-lin 2) × {len(HORIZONS)} h × 2 손실, 민감도 {sorted(SENSITIVITY)} 제외) ──")
    say(f"  {'모델':<22} {'h':>3} {'MSE Δ%':>7} {'DM t':>6} {'Holm p':>8} {'QLIKE Δ%':>9} {'DM t':>6} {'Holm p':>8}")
    for _, r in T[T["model"] != "HAR"].iterrows():
        say(f"  {r['model']:<22} {r['h']:>3} {r['mse_imp']:+7.2f} {r['mse_dm']:+6.2f} {r.get('mse_holm', np.nan):8.1e} "
            f"{r['qlike_imp']:+9.2f} {r['qlike_dm']:+6.2f} {r.get('qlike_holm', np.nan):8.1e}")
    say("  Δ% = 기준(HAR, 또는 'a|vs-b' 행은 b) 대비 평균 손실 감소율 (양수 = 개선). DM t < 0 = 그 모델 손실이 작다.")
    say("  HLN 보정, lag = max(h−1, NW). Holm 가족에 'vs-HARX-lin'(같은 정보에서 비선형만의 몫) 비교도 포함.")
    # VaR
    say()
    say("── 1일 99% VaR (h=1 분산 예측) " + "─" * 40)
    h = 1
    preds = {n: P[(n, h)] for n in names}
    mask = eval_mask(D, h, preds) & np.isfinite(D["r_next"].to_numpy())
    rn = D["r_next"].to_numpy()
    F1 = folds_for(D)[1]
    var_rows = []
    say(f"  {'모델':<12} {'q':>5} {'위반율':>7} {'Kupiec LR':>10} {'p':>7} {'종목 기각%':>9} {'평균 VaR%':>9}")
    for n in [x for x in ("HAR", "EWMA", "HAR-mkt", "HARX-lin", "LGBM-full", "LGBM-noearn", "LSTM") if x in names]:
        pv = preds[n][1]
        sig = np.sqrt(pv)
        for qn in ("normal", "fhs"):
            qv = np.full(len(D), np.nan)
            for f in F1:
                if qn == "normal":
                    qv[f.test] = 2.3263
                else:
                    # 🔴 배율은 검증 구간 표준화 수익의 1% 분위 — 시험 구간 안 봄. 검증 구간 예측이 없으니
                    # 직전 폴드의 시험 예측(=그 기간의 표본 밖 예측)으로 만든다. 첫 폴드는 정규값.
                    prev = (D["date"] >= f.test_start - pd.DateOffset(months=12)) & (D["date"] < f.test_start)
                    pm = prev.to_numpy() & np.isfinite(sig) & np.isfinite(rn)
                    qv[f.test] = -np.quantile(rn[pm] / sig[pm], 0.01) if pm.sum() > 10_000 else 2.3263
            mm = mask & np.isfinite(qv)
            exc = rn[mm] < -qv[mm] * sig[mm]
            lr, p = kupiec(int(exc.sum()), int(mm.sum()))
            per = pd.DataFrame({"j": D["j"].to_numpy()[mm], "e": exc}).groupby("j")["e"].agg(["sum", "size"])
            per = per[per["size"] >= 250]
            rej = np.mean([kupiec(int(s), int(z))[1] < 0.05 for s, z in zip(per["sum"], per["size"])])
            var_rows.append(dict(model=n, q=qn, rate=exc.mean(), lr=lr, p=p, rej=rej))
            say(f"  {n:<12} {qn:>6} {exc.mean():7.2%} {lr:10.1f} {p:7.3f} {rej:9.0%} {np.mean(qv[mm] * sig[mm]) * 100:9.2f}")
    say("  목표 위반율 1%. 풀링 Kupiec 는 같은 날 위반이 몰려 과대 유의 — 종목별 기각 비율(250일 이상 종목, 5%)을 같이 본다.")
    say()
    say(f"장부 시도 수 N = {registry.n_trials(STUDY)} (study={STUDY})")
    txt = "\n".join(lines)
    (panel.RUNS / "vol.txt").write_text(txt + "\n")
    T.to_csv(OUT / "table.csv", index=False)
    pd.DataFrame(split_rows).to_csv(OUT / "splits.csv", index=False)
    pd.DataFrame(var_rows).to_csv(OUT / "var.csv", index=False)
    print(f"\n→ {panel.RUNS / 'vol.txt'}")


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=["fit", "report"])
    ap.add_argument("--only", nargs="*")
    a = ap.parse_args(argv)
    if a.cmd == "fit":
        fit(a.only)
    else:
        report()


if __name__ == "__main__":
    main()
