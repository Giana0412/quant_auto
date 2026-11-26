#!/usr/bin/env python3
"""KAN-25 — 다음 분기 실적 서프라이즈(SUE) 방향을 미리 맞힐 수 있나, 그리고 그걸로 발표 전에 사서 돈이 되나.

── 왜 ──────────────────────────────────────────────────────────────────────
PEAD 연구(ml/pead/hypo.py H3)에서 2020 이후 drift 를 설명하는 유일한 가설이 '서프라이즈 지속성 상승'
이었다: 이번→다음 분기 SUE 순위상관 0.205 → 0.30 (차이 t 4.2), 상회→다음도 상회 76% → 81–83%.
지속성이 올랐다면 ① 다음 분기 방향 예측력도 올라야 하고 ② 예측 가능한 부분이 발표 전 가격에 아직
안 들어가 있다면 발표 직전 매수로 돈이 돼야 한다. 둘 다 확인한다.

── 정의 ────────────────────────────────────────────────────────────────────
한 행       = (종목, 직전 발표 k) → 다음 발표 k+1 을 예측. panel.earnings_events() 의 연속 두 행.
라벨        beat = SUE_{k+1} > 0 (실제 EPS > 예상, 0 은 '상회 아님').
            terc = SUE_{k+1} 의 직전 90일 백분위(pead trail90) ≥ 2/3 → 1, ≤ 1/3 → 0, 가운데는 버림.
🔴 예측 시점 f (그 종가까지의 정보만 쓴다):
   A  f = d0_{k+1} − 10 세션. 다음 발표일을 10 세션 전에는 안다고 가정한다. S&P 500 기업은 대개 2–4주
      전에 날짜를 공지하지만 Yahoo 에는 '지금 예정된 다음 날짜' 하나만 있고 과거 예정일 이력이 없어
      이 가정은 검증할 수 없다. 장중 발표(~1%)는 date_pre = d0−2 라 여전히 f 보다 뒤.
   B  f = d0_k + 50 세션 (보수적 — 다음 날짜를 몰라도 된다). 다음 발표 전 마지막 종가(date_pre)가
      f 보다 앞이면(조기 발표) 그 행은 거래하지 않는다(사전에 판정 가능). 보유는 발표 반응일까지.
   공통: f 에 S&P 500 편입 중인 종목만(member_mask[f]).
피처 (전부 f 또는 d0_k 시점에 알려진 값)
   SUE 이력   sue_l0..l3(이번·직전 3건 SUE), sue_pct_l0..l3, beat_l0..l3, zero_l0(SUE==0),
              hist_beat(그 종목 과거 상회율, (k+½)/(n+1)), hist_top/hist_bot(상·하위 3분위 비율),
              persist(최근 8건 자기 순위상관), ear_l0(직전 발표일 반응), n_hist
   시장(f)    panel.FEATURES 의 가격·거래량 피처(f 종가), run_since(d0_k+2 … f 초과수익 합),
              ex_10(최근 10 세션 초과수익), mkt_beat90(f 전 90일 편입 종목 발표의 상회율)
   🔴 업종은 쓰지 않는다(오늘의 GICS — 편출 종목은 업종이 없어 미래 정보).
   🔴 애널리스트 대용 피처 없음: Yahoo 는 분기마다 '최종 컨센서스 한 값'만 저장하고 예상치 수정 이력이
      없다. 다음 분기 컨센서스(est_{k+1})는 발표 직전 값이라 f 에서 알 수 없으므로 넣지 않는다.
모델       base_last  직전 상회 여부별 학습 구간 빈도 (terc 은 직전 백분위 3분위별)
           base_rate  종목 과거 상회율(terc 은 상·하위 비율) 1-D 로지스틱
           logit_sue  SUE 이력 로지스틱 (모든 비교의 기준)
           lgbm_sue   SUE 이력 LightGBM,  logit_full / lgbm_full  SUE 이력 + 시장 피처
CV         cv.walk_forward(기준일 f, 라벨 끝 d0_{k+1}+1 세션) — 2016-01 부터 분기마다 재학습,
           최근 12개월 검증(LightGBM 조기 종료·로지스틱 C 선택). 하이퍼파라미터는 고정 격자 하나.
           🔴 그래서 '2014–19' 표본외 기간은 실제로 2016–19 다 (학습에 2년 필요).
평가       AUC · log loss · Brier, 기간 2016–19 / 2020–. logit_sue 대비 차이는 분기(d0_{k+1}) 단위
           군집 부트스트랩 2,000회(짝지은 — 같은 재표본), 양측 p.
거래       f 종가 매수 → d0_{k+1} 종가(또는 +1 세션) 청산, 베타조정 초과수익(panel.beta_excess, 헤지 SPY).
           달력시간 포트폴리오: 매일 열린 포지션 동일가중, 회전 Σ|Δw| × 편도 c bp. 월합 → NW t.
           예측 3분위 = f 전 90일(달력) 표본외 예측 안 백분위 (100건 미만이면 거래 안 함) — 사전에 정해진 문턱.

── 한계 ──────────────────────────────────────────────────────────────────
· 컨센서스·실제 EPS 는 Yahoo 가 **지금** 저장한 값 — 발표 당시 화면과 다를 수 있다(SUE 자체의 한계).
· 다음 발표일을 미리 안다는 A 의 가정은 검증 불가 — B 로 같이 본다.
· 다음 발표가 200일 안에 없으면(인수·상폐) 행이 빠진다 — 거래 표본에 약간의 생존 조건.
· 헤지 SPY 거래·차입비·시장충격 없음, 상폐 수익 0, 생존 편향(편출 종목 가격 일부만) — 하네스 한계 그대로.
· 시도들이 서로 상관돼 있어 장부 행 수 N 은 독립 시도 수의 상한 — DSR 은 보수적.

실행 (ml/ 에서):  ../headline-sentiment/.venv/bin/python -m research.surprise
출력: RUNS/surprise.txt, 장부 study = "kan-25-surprise"
"""
from __future__ import annotations

import sys
import time
import warnings

import numpy as np
import pandas as pd

from . import cv, evaluate, panel, registry

STUDY = "kan-25-surprise"
FIRST_TEST = "2016-01-01"
SPLIT = pd.Timestamp("2020-01-01")
PERIODS = [("2016–19", None, SPLIT), ("2020–", SPLIT, None), ("전체", None, None)]
LEAD_A = 10          # A: d0_next − 10 세션
LAG_B = 50           # B: d0 + 50 세션
NBOOT = 2000
COSTS = (0, 10, 25)

SUE_COLS = (["sue_l0", "sue_l1", "sue_l2", "sue_l3", "sue_pct_l0", "sue_pct_l1", "sue_pct_l2", "sue_pct_l3",
             "beat_l0", "beat_l1", "beat_l2", "beat_l3", "zero_l0", "hist_beat", "hist_top", "hist_bot",
             "persist", "ear_l0", "n_hist"])
MKT_FEATS = ["mom_1m", "strev_1w", "exret_1m", "mom_3m", "mom_6m", "mom_12_1", "maxret_1m", "rvol_1m",
             "ivol_3m", "beta", "vol_chg", "dvol_1m", "high52"]
MKT_COLS = [f"f_{k}" for k in MKT_FEATS] + ["run_since", "ex_10", "mkt_beat90"]
FULL_COLS = SUE_COLS + MKT_COLS


# ── 데이터 ──────────────────────────────────────────────────────────────────

def build(raw: panel.Raw) -> dict[str, pd.DataFrame]:
    """예측 표 두 벌 (A, B). 한 행 = (종목, 직전 발표) → 다음 발표."""
    E = panel.earnings_events().sort_values(["ticker", "d0"], kind="stable").reset_index(drop=True)
    E["ticker"] = E["ticker"].astype(str)
    sess = raw.sessions
    cols = {c: j for j, c in enumerate(raw.C.columns)}
    E = E[E["ticker"].isin(cols)].reset_index(drop=True)
    E["j"] = E["ticker"].map(cols).astype(int)
    E["i0"] = sess.searchsorted(E["d0"].to_numpy().astype("datetime64[ns]"))
    E["ipre"] = sess.searchsorted(E["date_pre"].to_numpy().astype("datetime64[ns]"))
    E["beat"] = (E["sue"] > 0).astype(float)
    E["top"] = (E["sue_pct"] >= 2 / 3).astype(float).where(E["sue_pct"].notna())
    E["bot"] = (E["sue_pct"] <= 1 / 3).astype(float).where(E["sue_pct"].notna())
    g = E.groupby("ticker", sort=False)
    for L in range(4):
        E[f"sue_l{L}"] = g["sue"].shift(L)
        E[f"sue_pct_l{L}"] = g["sue_pct"].shift(L)
        E[f"beat_l{L}"] = g["beat"].shift(L)
    E["zero_l0"] = (E["sue"] == 0).astype(float)
    E["n_hist"] = g.cumcount() + 1.0
    E["hist_beat"] = (g["beat"].cumsum() + 0.5) / (E["n_hist"] + 1)
    for c in ("top", "bot"):
        k = E[c].fillna(0).groupby(E["ticker"], sort=False).cumsum()
        n = E[c].notna().astype(float).groupby(E["ticker"], sort=False).cumsum()
        E[f"hist_{c}"] = (k + 1 / 3) / (n + 1)
    E["ear_l0"] = E["ear"]
    # 다음 발표 = 같은 종목 다음 행 (panel 의 d0_next 와 같은지 확인)
    for c in ("d0", "i0", "ipre", "sue_pct", "member"):
        E[f"{c}_nx"] = g[c].shift(-1)
    ok = E["sue_next"].notna() & (E["d0_nx"] == E["d0_next"])
    E = E[ok].reset_index(drop=True)
    E["i0_nx"] = E["i0_nx"].astype(int)
    E["ipre_nx"] = E["ipre_nx"].astype(int)
    E["y_beat"] = (E["sue_next"] > 0).astype(float)
    E["y_terc"] = np.where(E["sue_pct_nx"] >= 2 / 3, 1.0, np.where(E["sue_pct_nx"] <= 1 / 3, 0.0, np.nan))

    F = panel.daily_features(raw)
    _, _, ex = panel.beta_excess(raw.C)
    X = np.nan_to_num(ex.to_numpy())
    cs = np.vstack([np.zeros(X.shape[1]), np.cumsum(X, axis=0)])     # cs[k] = Σ_{<k}
    M = panel.member_mask(raw).to_numpy()
    # 시장 상회율: 편입 중 발표만, f 전 90일(d0 ≤ f). 🔴 d0 ≤ f 인 발표만 — 그 SUE 는 f 에 알려져 있다.
    A_all = panel.earnings_events()
    A_all = A_all[A_all["member"]][["d0", "sue"]].sort_values("d0")
    ad = A_all["d0"].to_numpy().astype("datetime64[ns]")
    ab = np.concatenate([[0], np.cumsum((A_all["sue"] > 0).to_numpy())])

    def mkt_beat90(fd):
        hi = np.searchsorted(ad, fd, "right")
        lo = np.searchsorted(ad, fd - np.timedelta64(90, "D"), "right")
        n = hi - lo
        return np.where(n >= 100, (ab[hi] - ab[lo]) / np.maximum(n, 1), np.nan)

    out = {}
    T = len(sess)
    for setup in ("A", "B"):
        D = E.copy()
        if setup == "A":
            D["i_f"] = D["i0_nx"] - LEAD_A
            keep = D["i_f"] >= D["i0"] + 2
        else:
            D["i_f"] = D["i0"] + LAG_B
            keep = D["i_f"] <= D["ipre_nx"]           # 🔴 다음 발표 전 종가가 f 보다 앞이면 거래 없음
        D = D[keep & (D["i_f"] < T)].reset_index(drop=True)
        i_f, j = D["i_f"].to_numpy(), D["j"].to_numpy()
        D = D[M[i_f, j]].reset_index(drop=True)
        i_f, j = D["i_f"].to_numpy(), D["j"].to_numpy()
        i0, i0n = D["i0"].to_numpy(), D["i0_nx"].to_numpy()
        D["date"] = sess[i_f]
        for k in MKT_FEATS:
            D[f"f_{k}"] = F[k].to_numpy()[i_f, j]
        D["run_since"] = cs[i_f + 1, j] - cs[i0 + 2, j]
        D["ex_10"] = cs[i_f + 1, j] - cs[np.maximum(i_f - 9, 0), j]
        D["mkt_beat90"] = mkt_beat90(D["date"].to_numpy().astype("datetime64[ns]"))
        # 거래 라벨 (event-time): f+1 … 발표 반응일 d0', 그리고 d0'+1 까지
        D["r_d0"] = cs[i0n + 1, j] - cs[i_f + 1, j]
        e1 = np.minimum(i0n + 1, T - 1)
        D["r_d1"] = np.where(i0n + 1 < T, cs[e1 + 1, j] - cs[i_f + 1, j], np.nan)
        D["car_pre_f"] = cs[i_f + 1, j] - cs[i0 + 2, j]              # 직전 d0+2 … f (= run_since)
        D["car_run"] = cs[i0n, j] - cs[i_f + 1, j]                   # f+1 … d0'−1
        D["car_ear"] = X[i0n, j]                                     # d0'
        e5 = np.minimum(i0n + 5, T - 1)
        D["car_post5"] = np.where(i0n + 5 < T, cs[e5 + 1, j] - cs[i0n + 1, j], np.nan)   # d0'+1 … d0'+5
        D["label_end"] = sess[np.minimum(i0n + 1, T - 1)]
        D["q_nx"] = pd.PeriodIndex(D["d0_nx"], freq="Q").astype(str)
        D = D.sort_values(["date", "ticker"], kind="stable").reset_index(drop=True)
        D["row"] = np.arange(len(D))
        out[setup] = D
    return out


# ── 모델 ────────────────────────────────────────────────────────────────────

class Cell:
    """한 이산 열의 값별 학습 구간 빈도 (기준 규칙의 확률판). NaN 은 별도 칸. 칸 표본 < 30 이면 전체 빈도."""

    def __init__(self, col: int, bins=None):
        self.col, self.bins = col, bins

    def _key(self, X):
        x = X[:, self.col].astype(float)
        k = np.digitize(x, self.bins) if self.bins is not None else np.round(x)
        return np.where(np.isfinite(x), k, -9)

    def fit(self, X, y, Xv=None, yv=None):
        k = self._key(X)
        self.p0 = float(y.mean())
        s = pd.Series(y).groupby(k).agg(["mean", "size"])
        self.tab = {kk: (r["mean"] if r["size"] >= 30 else self.p0) for kk, r in s.iterrows()}
        return self

    def predict(self, X):
        return np.array([self.tab.get(k, self.p0) for k in self._key(X)])


class Logit:
    """로지스틱. 🔴 전처리 통계(1/99% 클립 경계·중앙값·평균·표준편차)는 학습 구간에서만. 결측은 중앙값 + 표시열.
    C 는 검증 log loss 로 {0.01, 0.1, 1} 중 고르고 학습+검증으로 다시 학습하지 않는다."""

    CS = (0.01, 0.1, 1.0)

    def _prep_fit(self, X):
        self.lo = np.nanpercentile(X, 1, axis=0)
        self.hi = np.nanpercentile(X, 99, axis=0)
        self.med = np.nanmedian(X, axis=0)
        self.na = np.flatnonzero(np.isnan(X).any(axis=0))
        Z = self._prep(X, fit=True)
        return Z

    def _prep(self, X, fit=False):
        Z = np.clip(X, self.lo, self.hi)
        nan = np.isnan(Z)
        Z = np.where(nan, self.med, Z)
        Z = np.hstack([Z, nan[:, self.na].astype(float)])
        Z = np.nan_to_num(Z)
        if fit:
            self.mu, self.sd = Z.mean(0), Z.std(0)
            self.sd[self.sd == 0] = 1
        return (Z - self.mu) / self.sd

    def fit(self, X, y, Xv=None, yv=None):
        from sklearn.linear_model import LogisticRegression
        from sklearn.metrics import log_loss
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            Z = self._prep_fit(X)
            best = None
            for C in (self.CS if Xv is not None else (0.1,)):
                m = LogisticRegression(C=C, max_iter=2000).fit(Z, y)
                ll = log_loss(yv, m.predict_proba(self._prep(Xv))[:, 1], labels=[0, 1]) if Xv is not None else 0
                if best is None or ll < best[0]:
                    best = (ll, m)
        self.m = best[1]
        return self

    def predict(self, X):
        return self.m.predict_proba(self._prep(X))[:, 1]


class LGBM:
    """LightGBM 분류기, 고정 하이퍼파라미터 + 검증 log loss 조기 종료(100). 검증이 없으면 300 그루."""

    def fit(self, X, y, Xv=None, yv=None):
        import lightgbm as lgb
        kw = dict(learning_rate=0.02, num_leaves=15, min_child_samples=100, subsample=0.8, subsample_freq=1,
                  colsample_bytree=0.8, reg_lambda=1.0, verbose=-1, random_state=0)
        if Xv is not None:
            self.m = lgb.LGBMClassifier(n_estimators=2000, **kw)
            self.m.fit(X, y, eval_set=[(Xv, yv)], callbacks=[lgb.early_stopping(100, verbose=False)])
        else:
            self.m = lgb.LGBMClassifier(n_estimators=300, **kw).fit(X, y)
        return self

    def predict(self, X):
        return self.m.predict_proba(X)[:, 1]


def models(target: str):
    """(이름, 열, 생성자)"""
    if target == "beat":
        last = ("base_last", ["beat_l0"], lambda: Cell(0))
        rate = ("base_rate", ["hist_beat"], lambda: Logit())
    else:
        last = ("base_last", ["sue_pct_l0"], lambda: Cell(0, bins=[1 / 3, 2 / 3 + 1e-12]))
        rate = ("base_rate", ["hist_top", "hist_bot"], lambda: Logit())
    return [last, rate,
            ("logit_sue", SUE_COLS, lambda: Logit()),
            ("lgbm_sue", SUE_COLS, lambda: LGBM()),
            ("logit_full", FULL_COLS, lambda: Logit()),
            ("lgbm_full", FULL_COLS, lambda: LGBM())]


# ── 지표·부트스트랩 ──────────────────────────────────────────────────────────

def _uinv(s):
    return np.unique(s, return_inverse=True)[1]


def wauc(u, y, w):
    """가중 AUC. u = 점수의 고유값 순위(동률 같은 값), 동률은 ½."""
    K = u.max() + 1
    pos = np.bincount(u, w * y, K)
    neg = np.bincount(u, w * (1 - y), K)
    below = np.cumsum(neg) - neg
    den = pos.sum() * neg.sum()
    return float((pos * (below + 0.5 * neg)).sum() / den) if den > 0 else np.nan


def metrics(y, p, w=None):
    w = np.ones(len(y)) if w is None else w
    pc = np.clip(p, 1e-6, 1 - 1e-6)
    ll = -(y * np.log(pc) + (1 - y) * np.log(1 - pc))
    return dict(auc=wauc(_uinv(p), y, w), ll=float((w * ll).sum() / w.sum()),
                brier=float((w * (p - y) ** 2).sum() / w.sum()))


def boot_weights(q: np.ndarray, B: int = NBOOT, seed: int = 0):
    """분기 군집 부트스트랩 가중치 (B × n). 분기를 복원추출한 횟수 = 그 분기 행들의 가중치."""
    qi = _uinv(q)
    G = qi.max() + 1
    rng = np.random.default_rng(seed)
    cnt = rng.multinomial(G, np.full(G, 1 / G), size=B)          # B × G
    return cnt[:, qi].astype(float)


def boot_p(d: np.ndarray, est: float) -> float:
    """두 측 부트스트랩 p: 재표본 차이의 0 너머 비율 ×2 (중심 이동 없이 백분위 방식)."""
    d = d[np.isfinite(d)]
    if not len(d):
        return np.nan
    return float(min(1.0, 2 * min((d <= 0).mean(), (d >= 0).mean())))


def period_mask(dates: pd.Series, lo, hi):
    m = np.ones(len(dates), bool)
    if lo is not None:
        m &= (dates >= lo).to_numpy()
    if hi is not None:
        m &= (dates < hi).to_numpy()
    return m


# ── 거래 ────────────────────────────────────────────────────────────────────

def trailing_pct(dates: pd.Series, p: np.ndarray, days: int = 90, min_n: int = 100) -> np.ndarray:
    """각 행 예측의 백분위 — 기준일 (d−days, d] 의 표본외 예측들 안에서 (같은 날 포함: 모두 d 종가에 알려짐)."""
    d = dates.to_numpy().astype("datetime64[ns]")
    o = np.argsort(d, kind="stable")
    ds, ps = d[o], p[o]
    out = np.full(len(p), np.nan)
    for day in np.unique(ds):
        hi = np.searchsorted(ds, day, "right")
        lo = np.searchsorted(ds, day - np.timedelta64(days, "D"), "right")
        if hi - lo < min_n:
            continue
        win = np.sort(ps[lo:hi])
        idx = np.flatnonzero(ds == day)
        r = (np.searchsorted(win, ps[idx], "left") + np.searchsorted(win, ps[idx], "right")) / 2
        out[o[idx]] = r / (hi - lo)
    return out


def calendar_returns(raw: panel.Raw, ex: np.ndarray, trades: pd.DataFrame, exit_col: str) -> pd.DataFrame:
    """trades: j, i_f, <exit_col>(청산 세션 번호), side(+1/−1). 보유일 = i_f+1 … exit.
    일간: 다리마다 열린 포지션 동일가중(롱 +1, 숏 −1 총노출), 회전 Σ|Δw|. 반환 일간 (gross, turnover)."""
    T, N = ex.shape
    W = np.zeros((T + 1, N))
    for side in (1, -1):
        t = trades[trades["side"] == side]
        if not len(t):
            continue
        H = np.zeros((T + 1, N))
        np.add.at(H, (t["i_f"].to_numpy() + 1, t["j"].to_numpy()), 1.0)
        np.add.at(H, (t[exit_col].to_numpy() + 1, t["j"].to_numpy()), -1.0)
        H = np.cumsum(H, axis=0)[:T]
        n = H.sum(1, keepdims=True)
        W[:T] += side * np.divide(H, n, out=np.zeros_like(H), where=n > 0)
    W = W[:T]
    gross = (W * ex).sum(1)
    turn = np.abs(np.diff(np.vstack([np.zeros(N), W]), axis=0)).sum(1)
    return pd.DataFrame({"gross": gross, "turn": turn}, index=raw.sessions)


def monthly(daily: pd.DataFrame, c: float, start, end) -> pd.Series:
    r = daily["gross"] - c / 1e4 * daily["turn"]
    r = r[(r.index >= start) & (r.index <= end)]
    return r.groupby(r.index.to_period("M")).sum()


def within_quarter(D: pd.DataFrame, out) -> list:
    """[1b] 분기 안 AUC 의 평균 — 기간 안에서도 상회 기저율이 분기마다 달라 풀링 AUC 가 시간 변동을 섞는 것을 뺀다.
    분기(d0') 마다 AUC → 기간 평균, 2020– − 2014–19 차이의 t(분기 독립). 반환 [(이름, p)]."""
    res = []
    out("\n[1b] 분기 안 AUC 평균 (기저율 시간 변동 제거, 분기 30건 이상) — 표 A")
    out(f"  {'':34}{'2014–19':>10}{'2020–':>10}{'차이':>9}{'t':>7}")
    for name, sc, ycol in [("직전 상회 → 상회 (beat)", "beat_l0", "y_beat"),
                           ("과거 상회율 (beat)", "hist_beat", "y_beat"),
                           ("직전 SUE 백분위 (beat)", "sue_pct_l0", "y_beat"),
                           ("직전 SUE 백분위 (terc)", "sue_pct_l0", "y_terc")]:
        Q = D[[sc, ycol, "q_nx", "d0_nx"]].dropna()
        auc, post = [], []
        for _, g in Q.groupby("q_nx"):
            if len(g) >= 30 and 0 < g[ycol].mean() < 1:
                auc.append(wauc(_uinv(g[sc].to_numpy()), g[ycol].to_numpy(), np.ones(len(g))))
                post.append(g["d0_nx"].iloc[0] >= SPLIT)
        auc, post = np.array(auc), np.array(post)
        x0, x1 = auc[~post], auc[post]
        se = np.sqrt(x0.var(ddof=1) / len(x0) + x1.var(ddof=1) / len(x1))
        t = (x1.mean() - x0.mean()) / se
        p = evaluate._p_norm(t)
        out(f"  {name:34}{x0.mean():10.3f}{x1.mean():10.3f}{x1.mean() - x0.mean():+9.3f}{t:7.2f}")
        registry.log(STUDY, f"rule-wq/{name}", dict(table="A", min_q=30),
                     dict(auc_pre=x0.mean(), auc_post=x1.mean(), diff=x1.mean() - x0.mean(), diff_t=t, diff_p=p,
                          n_q_pre=len(x0), n_q_post=len(x1)))
        res.append((f"rule-wq 기간차 {name}", p))
    return res


# ── 본체 ────────────────────────────────────────────────────────────────────

class Tee:
    def __init__(self, path):
        self.f = open(path, "w")

    def __call__(self, *a):
        s = " ".join(str(x) for x in a)
        print(s)
        self.f.write(s + "\n")
        self.f.flush()


def main():
    t0 = time.time()
    out = Tee(panel.RUNS / "surprise.txt")
    raw = panel.load_raw()
    tabs = build(raw)
    _, _, exdf = panel.beta_excess(raw.C)
    ex = np.nan_to_num(exdf.to_numpy())
    pvals = []                    # (이름, p) — Holm 가족
    out(f"KAN-25 다음 분기 서프라이즈 방향 예측 — {pd.Timestamp.now():%Y-%m-%d %H:%M}")
    for s, D in tabs.items():
        out(f"  표 {s}: {len(D):,}행 · 종목 {D['ticker'].nunique()} · 기준일 {D['date'].min().date()}~{D['date'].max().date()} "
            f"· beat 비율 {D['y_beat'].mean():.3f} · terc 라벨 {D['y_terc'].notna().sum():,}행")
    nA, nB = len(tabs["A"]), len(tabs["B"])
    out(f"  B 는 다음 발표가 d0+{LAG_B} 세션 전에 온 행을 뺀다 → A 대비 {nB / nA:.0%}")

    # ── Q4 사전: 학습 없는 규칙의 기간별 예측력 (2014–19 전체 사용) ──
    D = tabs["A"]
    out("\n[1] 학습 없는 규칙 — 기간별 (표 A, d0' 기준, 2014–19 전체 포함)")
    out(f"  {'':34}{'2014–19':>10}{'2020–':>10}{'차이':>9}{'p(분기 부트)':>14}")
    dn = D["d0_nx"]
    for name, sc, ycol in [("직전 상회 → 상회 AUC (beat)", D["beat_l0"], "y_beat"),
                           ("과거 상회율 AUC (beat)", D["hist_beat"], "y_beat"),
                           ("직전 SUE 백분위 AUC (terc)", D["sue_pct_l0"], "y_terc"),
                           ("직전 SUE 백분위 AUC (beat)", D["sue_pct_l0"], "y_beat")]:
        ok = sc.notna() & D[ycol].notna()
        y, x, dd, q = D.loc[ok, ycol].to_numpy(), sc[ok].to_numpy(), dn[ok], D.loc[ok, "q_nx"].to_numpy()
        a = period_mask(dd, None, SPLIT)
        b = ~a
        ua, ub = _uinv(x[a]), _uinv(x[b])
        ea, eb = wauc(ua, y[a], np.ones(a.sum())), wauc(ub, y[b], np.ones(b.sum()))
        Wa, Wb = boot_weights(q[a], seed=1), boot_weights(q[b], seed=2)
        dd_ = np.array([wauc(ub, y[b], Wb[k]) - wauc(ua, y[a], Wa[k]) for k in range(NBOOT)])
        p = boot_p(dd_, eb - ea)
        out(f"  {name:34}{ea:10.3f}{eb:10.3f}{eb - ea:+9.3f}{p:14.3f}")
        registry.log(STUDY, f"rule/{name}", dict(table="A", period_split="2020-01-01"),
                     dict(auc_pre=ea, auc_post=eb, diff=eb - ea, diff_p=p, n=int(ok.sum())))
        pvals.append((f"rule 기간차 {name}", p))
    for lab, lo, hi in [("2014–19", None, SPLIT), ("2020–", SPLIT, None)]:
        m = period_mask(dn, lo, hi)
        out(f"  {lab} beat 비율 {D.loc[m, 'y_beat'].mean():.3f} · 직전 상회→상회 "
            f"{D.loc[m & (D['beat_l0'] == 1), 'y_beat'].mean():.3f} · 직전 하회→상회 "
            f"{D.loc[m & (D['beat_l0'] == 0), 'y_beat'].mean():.3f}")

    pvals += within_quarter(D, out)

    # ── 모델 ──
    preds = {}
    for setup in ("A", "B"):
        D = tabs[setup]
        folds = cv.walk_forward(D["date"], D["label_end"], first_test=FIRST_TEST, refit_months=3, val_months=12)
        for target in ("beat", "terc"):
            ycol = f"y_{target}"
            for name, cols, mk in models(target):
                if setup == "B" and name not in ("base_last", "logit_sue", "lgbm_full"):
                    continue
                R = cv.predict_oos(D, folds, cols, ycol, mk, keep=("ticker", "row"))
                preds[(setup, target, name)] = R
        out(f"  [{setup}] 폴드 {len(folds)}개 · 첫 시험 {folds[0].test_start.date()} · 마지막 {folds[-1].test_end.date()} "
            f"({time.time() - t0:.0f}s)")

    # ── [2] 예측 지표 표 + logit_sue 대비 차이 ──
    out("\n[2] 표본외 예측 — AUC / log loss / Brier, logit_sue 대비 차이(분기 군집 부트스트랩 p, ΔAUC 기준)")
    cmp_rows = []
    for setup in ("A", "B"):
        D = tabs[setup]
        for target in ("beat", "terc"):
            names = [n for (s, t, n) in preds if s == setup and t == target]
            base = preds[(setup, target, "logit_sue")]
            ok = base["y"].notna().to_numpy()
            rows = base.loc[ok, "row"].to_numpy()
            y = base.loc[ok, "y"].to_numpy()
            dd = D["d0_nx"].iloc[rows].reset_index(drop=True)
            q = D["q_nx"].iloc[rows].to_numpy()
            P = {n: preds[(setup, target, n)].set_index("row").loc[rows, "pred"].to_numpy() for n in names}
            out(f"\n  표 {setup} · 라벨 {target} · n={ok.sum():,} (양성 {y.mean():.3f})")
            out(f"  {'모델':12}" + "".join(f"{lab + ' AUC':>14}{'LL':>8}{'Brier':>8}" for lab, _, _ in PERIODS)
                + f"{'  ΔAUC(전체) p':>16}{'ΔAUC 16–19 / 20–':>22}")
            for n in names:
                line = f"  {n:12}"
                met = {}
                for lab, lo, hi in PERIODS:
                    m = period_mask(dd, lo, hi)
                    r = metrics(y[m], P[n][m])
                    met.update({f"{k}_{lab}": v for k, v in r.items()})
                    line += f"{r['auc']:14.3f}{r['ll']:8.4f}{r['brier']:8.4f}"
                extra = {}
                if n != "logit_sue":
                    diffs = []
                    for lab, lo, hi in PERIODS:
                        m = period_mask(dd, lo, hi)
                        W = boot_weights(q[m], seed=3)
                        ua, ub = _uinv(P[n][m]), _uinv(P["logit_sue"][m])
                        da = metrics(y[m], P[n][m])
                        db = metrics(y[m], P["logit_sue"][m])
                        bd = np.array([wauc(ua, y[m], W[k]) - wauc(ub, y[m], W[k]) for k in range(NBOOT)])
                        pc = np.clip(P[n][m], 1e-6, 1 - 1e-6)
                        pb = np.clip(P["logit_sue"][m], 1e-6, 1 - 1e-6)
                        lla = -(y[m] * np.log(pc) + (1 - y[m]) * np.log(1 - pc))
                        llb = -(y[m] * np.log(pb) + (1 - y[m]) * np.log(1 - pb))
                        bl = (W @ (lla - llb)) / W.sum(1)
                        bb = (W @ ((P[n][m] - y[m]) ** 2 - (P["logit_sue"][m] - y[m]) ** 2)) / W.sum(1)
                        e = dict(dauc=da["auc"] - db["auc"], dauc_p=boot_p(bd, 0), dll=da["ll"] - db["ll"],
                                 dll_p=boot_p(bl, 0), dbrier=da["brier"] - db["brier"], dbrier_p=boot_p(bb, 0))
                        extra.update({f"{k}_{lab}": v for k, v in e.items()})
                        diffs.append(e)
                        cmp_rows.append(dict(setup=setup, target=target, model=n, period=lab, **e))
                    line += f"   {diffs[2]['dauc']:+.3f} p={diffs[2]['dauc_p']:.3f}   {diffs[0]['dauc']:+.3f} / {diffs[1]['dauc']:+.3f}"
                    pvals.append((f"{setup}/{target}/{n} vs logit_sue ΔAUC 전체", diffs[2]["dauc_p"]))
                out(line)
                registry.log(STUDY, f"pred/{setup}/{target}/{n}",
                             dict(setup=setup, target=target, model=n, first_test=FIRST_TEST, refit_months=3,
                                  val_months=12, lead=LEAD_A if setup == "A" else None,
                                  lag=LAG_B if setup == "B" else None),
                             dict(n=int(ok.sum()), **met, **extra))
    C = pd.DataFrame(cmp_rows)
    out("\n  ΔlogLoss·ΔBrier (음수 = logit_sue 보다 좋음), 전체 기간:")
    for _, r in C[C["period"] == "전체"].iterrows():
        out(f"    {r.setup}/{r.target}/{r.model:11} ΔLL {r.dll:+.4f} (p={r.dll_p:.3f}) · ΔBrier {r.dbrier:+.4f} (p={r.dbrier_p:.3f})")

    # ── [3] 기간 간 차이: 2020 이후 예측력이 올랐나 (모델) ──
    out("\n[3] 2020– AUC − 2016–19 AUC (표 A, 분기 군집 부트스트랩, 기간 독립)")
    for target in ("beat", "terc"):
        for n in ("base_last", "logit_sue", "lgbm_full"):
            R = preds[("A", target, n)]
            R = R[R["y"].notna()]
            dd = tabs["A"]["d0_nx"].iloc[R["row"].to_numpy()].reset_index(drop=True)
            q = tabs["A"]["q_nx"].iloc[R["row"].to_numpy()].to_numpy()
            y, p = R["y"].to_numpy(), R["pred"].to_numpy()
            a = period_mask(dd, None, SPLIT)
            b = ~a
            ua, ub = _uinv(p[a]), _uinv(p[b])
            ea, eb = wauc(ua, y[a], np.ones(a.sum())), wauc(ub, y[b], np.ones(b.sum()))
            Wa, Wb = boot_weights(q[a], seed=4), boot_weights(q[b], seed=5)
            bd = np.array([wauc(ub, y[b], Wb[k]) - wauc(ua, y[a], Wa[k]) for k in range(NBOOT)])
            p_ = boot_p(bd, eb - ea)
            out(f"  {target:5} {n:10} 2016–19 {ea:.3f} → 2020– {eb:.3f}  차이 {eb - ea:+.3f} "
                f"[{np.nanpercentile(bd, 2.5):+.3f}, {np.nanpercentile(bd, 97.5):+.3f}] p={p_:.3f}")
            registry.log(STUDY, f"period/A/{target}/{n}", dict(setup="A", target=target, model=n),
                         dict(auc_pre=ea, auc_post=eb, diff=eb - ea, diff_p=p_))
            pvals.append((f"기간차 A/{target}/{n}", p_))

    # ── [4] 이벤트 시간 누적 초과수익 — 예측 가능한 부분이 이미 가격에 있나 ──
    out("\n[4] 예측 3분위별 이벤트 시간 누적 초과수익 (표 A, beat 확률, f 전 90일 표본외 백분위) — 평균 %, 괄호 분기 t")
    wins = [("car_pre_f", "직전 d0+2…f"), ("car_run", "f+1…d0'−1"), ("car_ear", "d0' 반응"),
            ("car_post5", "d0'+1…+5"), ("y_beat", "실제 상회율")]
    for n in ("base_last", "logit_sue", "lgbm_full"):
        R = preds[("A", "beat", n)]
        D = tabs["A"].iloc[R["row"].to_numpy()].reset_index(drop=True)
        D["pp"] = trailing_pct(R["date"].reset_index(drop=True), R["pred"].to_numpy()) if n != "base_last" else np.nan
        if n == "base_last":   # 규칙: 직전 상회 = 상위, 하회 = 하위 (가운데 없음)
            D["bk"] = np.where(D["beat_l0"] == 1, 2, np.where(D["beat_l0"] == 0, 0, np.nan))
        else:
            D["bk"] = np.where(D["pp"] >= 2 / 3, 2, np.where(D["pp"] <= 1 / 3, 0, np.where(D["pp"].notna(), 1, np.nan)))
        out(f"\n  {n} (위 = 예측 상위, 아래 = 하위)")
        for lab, lo, hi in PERIODS[:2]:
            m = period_mask(D["d0_nx"], lo, hi)
            line = f"  {lab:8}"
            for c, nm in wins:
                top = D[m & (D["bk"] == 2)].groupby("q_nx")[c].mean()
                bot = D[m & (D["bk"] == 0)].groupby("q_nx")[c].mean()
                dq = (top - bot).dropna()
                t = dq.mean() / dq.std() * np.sqrt(len(dq)) if len(dq) > 2 else np.nan
                sc = 1 if c == "y_beat" else 100
                fmt = "{:.2f}" if c == "y_beat" else "{:+.2f}"
                line += f" | {nm}: {fmt.format(D.loc[m & (D['bk'] == 2), c].mean() * sc)} / " \
                        f"{fmt.format(D.loc[m & (D['bk'] == 0), c].mean() * sc)} (t={t:+.1f})"
            out(line)

    # ── [5] 거래 ──
    out("\n[5] 거래 — f 종가 매수 → d0' 종가(또는 +1) 청산, 베타조정 초과수익, 달력시간 동일가중, 월간 NW t")
    out("     비용: 편도 c bp × Σ|Δw| (헤지 SPY 비용 없음). 상위/하위 = f 전 90일 표본외 예측 백분위 ≥⅔ / ≤⅓")
    strat_rows = []
    for setup in ("A", "B"):
        D = tabs[setup]
        base = preds[(setup, "beat", "logit_sue")]
        rows_oos = base["row"].to_numpy()
        S = D.iloc[rows_oos].reset_index(drop=True)
        S["i_x0"] = S["i0_nx"]
        S["i_x1"] = np.minimum(S["i0_nx"] + 1, len(raw.sessions) - 1)
        start = S["date"].min()
        end = raw.sessions[-1]
        books = {"ALL": S.assign(side=1), "LAST+": S[S["beat_l0"] == 1].assign(side=1),
                 "LAST± LS": pd.concat([S[S["beat_l0"] == 1].assign(side=1), S[S["beat_l0"] == 0].assign(side=-1)])}
        for target in ("beat", "terc"):
            for n in ("logit_sue", "lgbm_full"):
                R = preds[(setup, target, n)].set_index("row").loc[rows_oos].reset_index()
                pp = trailing_pct(R["date"], R["pred"].to_numpy())
                top, bot = S[pp >= 2 / 3], S[pp <= 1 / 3]
                books[f"{n}/{target} 상위"] = top.assign(side=1)
                books[f"{n}/{target} LS"] = pd.concat([top.assign(side=1), bot.assign(side=-1)])
        out(f"\n  표 {setup} (표본외 {start.date()} ~ {end.date()}, 거래 후보 {len(S):,}건)")
        out(f"  {'전략':22}{'청산':>5}{'건수':>7}" + "".join(f"{f'{c}bp 연%':>10}{'t':>6}" for c in COSTS)
            + f"{'SR(10bp)':>9}{'16–19 연%':>10}{'20– 연%':>9}{'−ALL 연% (t)':>15}")
        for ex_col, ex_lab in (("i_x0", "d0"), ("i_x1", "d0+1")):
            dall = calendar_returns(raw, ex, books["ALL"], ex_col)
            for bn, B in books.items():
                d = calendar_returns(raw, ex, B, ex_col)
                line = f"  {bn:22}{ex_lab:>5}{int((B['side'] == 1).sum()):7,}"
                st = {}
                for c in COSTS:
                    m = monthly(d, c, start, end)
                    s = evaluate.series_stats(m, 12)
                    st[c] = s
                    line += f"{s['ann'] * 100:10.2f}{s['t']:6.2f}"
                m10 = monthly(d, 10, start, end)
                pre = m10[m10.index.to_timestamp() < SPLIT].mean() * 12 * 100
                post = m10[m10.index.to_timestamp() >= SPLIT].mean() * 12 * 100
                rel = evaluate.series_stats(m10 - monthly(dall, 10, start, end), 12)
                line += f"{st[10]['sr']:9.2f}{pre:10.2f}{post:9.2f}"
                line += f"{rel['ann'] * 100:+9.2f} ({rel['t']:+.1f})" if bn != "ALL" else f"{'':>15}"
                out(line)
                name = f"trade/{setup}/{bn}/{ex_lab}"
                met = {f"c{c}_{k}": v for c in COSTS for k, v in st[c].items()}
                met.update({f"strat_{k}": v for k, v in st[10].items()})
                met.update(dict(rel_ann=rel["ann"], rel_t=rel["t"], rel_p=rel["p"], ann_pre=pre / 100, ann_post=post / 100,
                                avg_turn_daily=float(d["turn"].mean())))
                registry.log(STUDY, name, dict(setup=setup, book=bn, exit=ex_lab, costs=COSTS), met)
                strat_rows.append(dict(name=name, **met))
                pvals.append((f"{name} 10bp", st[10]["p"]))
                if bn != "ALL":
                    pvals.append((f"{name} −ALL 10bp", rel["p"]))

    # ── [6] 다중검정 ──
    L = registry.load(STUDY)
    N = len(L)
    out(f"\n[6] 다중검정 — 장부 study={STUDY} 행 수 N = {N} (고유 설정 {L['name'].nunique()}개; 재실행도 센다)")
    names, ps = zip(*pvals)
    h = registry.holm(np.array(ps))
    PV = pd.DataFrame({"test": names, "p": ps, "holm": h}).sort_values("p")
    out(f"  이번 실행 검정 {len(PV)}개, Holm 보정 후 p<0.05: {(PV['holm'] < 0.05).sum()}개")
    for _, r in PV.head(15).iterrows():
        out(f"    {r.test:58} p={r.p:.4f}  Holm={r.holm:.4f}")
    T = pd.DataFrame(strat_rows)
    T = T[~T["name"].str.contains("/ALL/")]
    T = registry.deflate(T.reset_index(drop=True), "strat", n_trials=N)
    best = T.sort_values("strat_srpp", ascending=False).head(5)
    out("  DSR (10bp 월간 SR, N = 장부 행 수, V = 전략 SR 분산):")
    for _, r in best.iterrows():
        out(f"    {r['name']:40} 월 SR {r.strat_srpp:+.3f} (연 {r.strat_sr:+.2f}) · SR0 {r.strat_sr0:.3f} · DSR {r.strat_dsr:.3f}")
    out(f"\n완료 {time.time() - t0:.0f}s")


if __name__ == "__main__":
    sys.exit(main())
