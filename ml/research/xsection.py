#!/usr/bin/env python3
"""KAN-23 — S&P 500 횡단면 수익 예측에 ML 이 선형 기준보다 나은가 (Gu–Kelly–Xiu 2020 소규모 재현·확장).

── 왜 ──────────────────────────────────────────────────────────────────────
GKX(2020)는 미국 전 종목 60년·94개 특성으로 "트리·신경망이 OLS·벌점 선형보다 월 수익을 더 잘 맞히고,
이득은 주로 비선형·상호작용에서 오며, 소형주에 몰린다"고 보고했다. 우리 조건은 정반대 쪽 끝이다:
S&P 500 대형주만, 2014–2026 12년, 가격·거래량·실적 기반 21개 피처(가치·재무 피처 없음).
여기서도 비선형 이득이 남는지, 남는다면 **비용·다중검정 뒤에도** 의미가 있는지를 본다.
잘 잰 음성 결과도 결과다 — 운 좋은 양성 하나를 고르지 않으려고 모든 설정을 장부에 적고 깎는다.

── 정의 (실행 전에 고정한 설계) ─────────────────────────────────────────────
표본      research.panel.monthly_panel() — 월말 t 편입 종목, 라벨 y_ex = t→t' 베타조정 초과수익 합.
피처      panel.FEATURES 21개 → panel.prepare (날짜별 순위 [-1,1] + 날짜별 중앙값 대체 + <col>_na).
분할      cv.walk_forward(first_test=2017-01, refit_months=12, val_months=12) — 매년 재학습, 매달 예측,
          학습 후보의 마지막 12개월은 시간순 검증(조기 종료·α 선택), 고른 뒤 학습+검증으로 다시 학습.
          시험 2017-01 ~ 2026-09 (117개월).
          왜 2017 인가: 패널이 2014-01 부터라 첫 폴드의 안쪽 학습은 2014–2015 (24개월 = min_train_dates),
          검증 2016. 2018 시작(README 예시)보다 시험이 12개월 길고, 검증을 24개월로 늘리면 첫 폴드 학습이
          12개월로 줄어 하한에 걸린다. 그래서 검증 12개월 · 시험 2017 이 가능한 가장 이른 시작이다.
          첫 폴드는 2014 상반기 mom_12_1 이 비어(중앙값 대체) 가장 약한 모델이다 — 그대로 둔다.
모델 (장부에 적는 설정 = 아래가 전부, 실행 전에 고정)
  OLS-3     CLASSIC 3개(mom_12_1, dvol_1m, mom_1m) 최소제곱. 🔴 baselines.OLS 는 검증 구간을 버리므로
            refit 을 붙여 학습+검증으로 맞춘다(Ridge 와 같은 데이터).
  OLS-all   전 피처 최소제곱 (같은 refit).
  Ridge     baselines.RidgeCV (α 격자 7개를 검증 MSE 로) — **모든 짝지은 비교의 기준**.
  Lasso     baselines.LassoCV.   ENet  l1_ratio 0.5, α 격자 7개 (같은 방식).
  GBM-d{1,2,3,6}  LightGBM, max_depth=d · num_leaves=min(2^d, 31) · lr 0.02 · min_child 500 · 행/열 표본 0.8 ·
            L2 10 · 최대 3000 그루 · 검증 조기 종료 100 → 최적 그루 수로 학습+검증 재학습.
            본 모델은 GBM-d3. d1(가법, 상호작용 없음)·d2·d6 은 상호작용 점검용.
  NN{1,2,3} GKX 식 피라미드 (32) · (32,16) · (32,16,8), Linear→BatchNorm→ReLU, Adam 1e-3, 배치 1024,
            가중치 L1, 최대 100 에폭 · 인내 5 조기 종료, 시드 5개 앙상블(평균).
            L1 ∈ {1e-5, 1e-3} 은 폴드 안에서 검증 MSE 로 고른다(시험은 안 본다 → 장부 시도가 아니라 절차).
            고른 뒤 시드마다 최적 에폭 수만큼 학습+검증으로 재학습.
  확장(새 설정 → 같은 장부): Ridge·GBM-d3·NN3 를 횡단면 라벨 y_xs = y_ex − 날짜 평균 으로 학습(-xs).
            왜: 월별 공통 성분이 MSE 를 지배해 검증 조기 종료가 1그루·1에폭에서 멈추는 폴드가 있다(점검 실행에서 확인).
            평가는 그대로 y_ex. 이 설정은 점검 실행(2폴드) 뒤 추가했다 — 그래서 장부 N 에 같이 센다.
  강건성 재학습(새 설정 → 같은 장부): Ridge·GBM-d3·NN3 를 SUE 피처(sue_raw, sue_pct, sue_persist + _na) 없이.
평가      evaluate.summarize (R²_zero, R²_hist, 순위 IC NW t, 10분위 롱숏·상위 롱 0/10/25bp, 회전),
          evaluate.compare(모델, Ridge) (IC 차·순수익 차 NW t, DM). 롱숏은 y_ex 기준이라 이미 베타조정이다;
          보조로 원수익 y_raw 롱숏을 SPY 에 회귀해 남은 β 와 α 를 낸다.
해석      순열 중요도(OOS, 날짜 안에서 피처+_na 를 함께 섞어 IC 감소) · LightGBM gain ·
          GBM-d1 vs d3/d6 짝 비교 · 상위 3 피처 부분의존(OOS 행에서 그 피처만 격자값으로 바꾼 평균 예측).
강건성    기간 2017 / 2018–2020 / 2021–2026 · 날짜별 거래대금 큰/작은 절반(분위는 절반 안에서) ·
          SUE 피처 제외 재학습 · 실적 발표 달 제외 (a) 실현: 라벨 창 (t, t'] 에 반응일이 있는 행 제외 — 사후
          진단용, 거래 불가 · (b) 거래 가능: ea_next_exp == 1 (다음 달 발표 예상) 행 제외.
          기간·크기·발표 달 자르기는 같은 예측을 나눠 보는 것이라 별도 장부(kan-23-xsection-slices)에 적는다.
다중검정  N = 장부(kan-23-xsection) 줄 수. DSR(ls_c10) · Holm(모델 vs Ridge 의 IC 차 p, 롱숏 10bp 차 p).

── 🔴 미래 정보 ────────────────────────────────────────────────────────────
🔴 전처리는 날짜 안에서만(panel.prepare). 신경망의 y 척도(표준편차)는 학습 y 에서만 잡는다.
🔴 조기 종료·α·L1 은 검증(시험보다 과거, 퍼지된 구간)으로만 고른다. 시험 예측은 그 뒤 한 번.
🔴 "실현 발표 달 제외"는 라벨 창의 미래 발표를 보고 자른다 — 원인 진단용이지 전략이 아니다.
🔴 순열 중요도·부분의존은 각 폴드 모델을 **그 폴드의 시험 행**에만 적용한다.

── 한계 ──────────────────────────────────────────────────────────────────
· 대형주 ~440종목 × 월 → 시험 ~5만 행, 독립 표본은 사실상 117개월. 월 IC 차 0.01 은 검정력 밖이다.
· 가치·수익성·투자 같은 재무 피처가 없다 — GKX 이득의 상당 부분(상호작용 포함)이 그쪽에서 나왔다.
· 생존 편향·상폐 수익 0·차입비 없음(README 한계 그대로). 비용은 편도 c bp × 회전만.
· 시도들은 상관돼 있어 N 은 독립 시도 수의 상한 — DSR 은 보수적이다.

실행 (ml/ 에서):
  ../headline-sentiment/.venv/bin/python -m research.xsection            # 예측 캐시 있으면 재사용, 보고서
  ... -m research.xsection --fresh                                        # 전부 다시 학습 (장부에 다시 적힌다)
  XS_DEV=1 ... -m research.xsection                                       # 2폴드·2시드 점검 (장부·캐시 분리)
"""
from __future__ import annotations

import argparse
import contextlib
import io
import os
import pickle
import sys
import time

import numpy as np
import pandas as pd

from . import baselines, cv, evaluate, panel, registry

DEV = os.environ.get("XS_DEV") == "1"
STUDY = "dev-kan-23" if DEV else "kan-23-xsection"
STUDY_SLICE = STUDY + "-slices"
OUT = panel.RUNS / ("xsection_dev" if DEV else "xsection")
LEDGER = OUT / "ledger_dev.jsonl" if DEV else None          # None → 공용 장부
REPORT = panel.RUNS / ("xsection_dev.txt" if DEV else "xsection.txt")

FIRST_TEST, REFIT, VAL = "2017-01-01", 12, 12
SEEDS = (0, 1) if DEV else (0, 1, 2, 3, 4)
SUE_COLS = ("sue_raw", "sue_pct", "sue_persist")
ALL_FEATS = list(panel.FEATURES)
# 🔴 맥에서 LightGBM 과 torch 가 libomp 를 따로 싣는다. 한 프로세스에서 둘 다 여러 스레드를 쓰면 OMP 초기화가
# 깨져 멈추거나 세그폴트가 난다(직접 재현: GBM 학습 뒤 torch 학습이 멈춤). 둘을 섞어 쓰므로 양쪽 다 1 스레드.
TORCH_THREADS, GBM_THREADS = 1, 1


# ── 모델 ────────────────────────────────────────────────────────────────────

class OLSRefit(baselines.OLS):
    """baselines.OLS + refit — 검증 구간까지 학습에 쓴다(Ridge 와 같은 데이터로 공정하게)."""

    def refit(self, X, y):
        return self.fit(X, y)


class ElasticNetCV(baselines._PenalizedCV):
    # l1_ratio 0.5 → Lasso 와 같은 '죽는' 경계가 α 두 배쯤이라 격자를 2배 위로
    alphas = (2e-6, 2e-5, 6e-5, 2e-4, 6e-4, 2e-3, 6e-3)

    def _make(self, a):
        from sklearn.linear_model import ElasticNet
        return ElasticNet(alpha=a, l1_ratio=0.5, max_iter=5000)


class GBM:
    """LightGBM — 얕은 트리·강한 규제·시간순 검증 조기 종료 → 최적 그루 수로 학습+검증 재학습."""

    def __init__(self, depth=3, seed=0, n_jobs=GBM_THREADS):
        self.depth, self.seed = depth, seed
        self.kw = dict(objective="regression", learning_rate=0.02, n_estimators=3000, max_depth=depth,
                       num_leaves=min(2 ** depth, 31), min_child_samples=500, subsample=0.8, subsample_freq=1,
                       colsample_bytree=0.8, reg_lambda=10.0, random_state=seed, n_jobs=n_jobs, verbose=-1,
                       deterministic=True, force_row_wise=True)

    def fit(self, X, y, Xv=None, yv=None):
        import lightgbm as lgb
        assert Xv is not None and len(Xv), "GBM 은 시간순 검증이 필요하다 (val_months > 0)"
        m = lgb.LGBMRegressor(**self.kw)
        m.fit(X, y, eval_set=[(Xv, yv)], callbacks=[lgb.early_stopping(100, verbose=False)])
        self.best_iter_ = max(int(m.best_iteration_ or 1), 1)
        self.m = m
        return self

    def refit(self, X, y):
        import lightgbm as lgb
        self.m = lgb.LGBMRegressor(**{**self.kw, "n_estimators": self.best_iter_}).fit(X, y)
        return self

    def predict(self, X):
        return self.m.predict(np.asarray(X, np.float32))

    def gain(self):
        return self.m.booster_.feature_importance(importance_type="gain")


class MLP:
    """GKX NN1–NN3 식 작은 피라미드 신경망, 시드 앙상블. 🔴 y 척도는 학습 y 에서만."""

    def __init__(self, hidden=(32, 16, 8), l1s=(1e-5, 1e-3), seeds=SEEDS, lr=1e-3, batch=1024,
                 max_epochs=100, patience=5):
        self.hidden, self.l1s, self.seeds = tuple(hidden), tuple(l1s), tuple(seeds)
        self.lr, self.batch, self.max_epochs, self.patience = lr, batch, max_epochs, patience

    def _net(self, d):
        import torch.nn as nn
        layers, k = [], d
        for h in self.hidden:
            layers += [nn.Linear(k, h), nn.BatchNorm1d(h), nn.ReLU()]
            k = h
        layers.append(nn.Linear(k, 1))
        return nn.Sequential(*layers)

    def _train(self, X, y, l1, seed, Xv=None, yv=None, epochs=None):
        import torch
        torch.manual_seed(seed)
        g = torch.Generator().manual_seed(seed)
        net = self._net(X.shape[1])
        opt = torch.optim.Adam(net.parameters(), lr=self.lr)
        ws = [p for n, p in net.named_parameters() if p.dim() == 2]          # Linear 가중치만 L1
        n = len(X)
        best, best_ep, best_state, bad = np.inf, 0, None, 0
        for ep in range(epochs or self.max_epochs):
            net.train()
            perm = torch.randperm(n, generator=g)
            for i in range(0, n, self.batch):
                idx = perm[i:i + self.batch]
                if len(idx) < 2:                                              # BatchNorm
                    continue
                opt.zero_grad()
                loss = ((net(X[idx]).squeeze(1) - y[idx]) ** 2).mean() + l1 * sum(w.abs().sum() for w in ws)
                loss.backward()
                opt.step()
            if Xv is None:
                continue
            net.eval()
            with torch.no_grad():
                v = float(((net(Xv).squeeze(1) - yv) ** 2).mean())
            if v < best - 1e-7:
                best, best_ep, bad = v, ep + 1, 0
                best_state = {k: t.clone() for k, t in net.state_dict().items()}
            else:
                bad += 1
                if bad >= self.patience:
                    break
        if best_state is not None:
            net.load_state_dict(best_state)
        net.eval()
        return net, best_ep, best

    def _t(self, X):
        import torch
        torch.set_num_threads(TORCH_THREADS)          # 🔴 캐시에서 읽은 모델은 fit 을 안 거친다 — 여기서도 고정
        return torch.as_tensor(np.asarray(X, np.float32))

    def fit(self, X, y, Xv=None, yv=None):
        import torch
        torch.set_num_threads(TORCH_THREADS)
        assert Xv is not None and len(Xv), "MLP 은 시간순 검증이 필요하다"
        self.sd_ = float(np.std(y)) or 1.0
        Xt, yt = self._t(X), self._t(np.asarray(y) / self.sd_)
        Xvt, yvt = self._t(Xv), self._t(np.asarray(yv) / self.sd_)
        res = {}
        for l1 in self.l1s:
            runs = [self._train(Xt, yt, l1, s, Xvt, yvt) for s in self.seeds]
            with torch.no_grad():
                pv = np.mean([r[0](Xvt).squeeze(1).numpy() for r in runs], axis=0)
            res[l1] = (float(np.mean((pv - yvt.numpy()) ** 2)), runs)
        self.val_mse_ = {k: v[0] for k, v in res.items()}
        self.l1_ = min(self.val_mse_, key=self.val_mse_.get)
        runs = res[self.l1_][1]
        self.nets = [r[0] for r in runs]
        self.epochs_ = [max(r[1], 1) for r in runs]
        return self

    def refit(self, X, y):
        Xt, yt = self._t(X), self._t(np.asarray(y) / self.sd_)                # 척도는 안쪽 학습 것 유지
        self.nets = [self._train(Xt, yt, self.l1_, s, epochs=e)[0] for s, e in zip(self.seeds, self.epochs_)]
        return self

    def predict(self, X):
        import torch
        with torch.no_grad():
            Xt = self._t(X)
            return np.mean([n(Xt).squeeze(1).numpy() for n in self.nets], axis=0) * self.sd_


class ColSubset:
    """같은 X 에서 열 일부만 내부 모델에 넘긴다 (피처 제외 재학습용)."""

    def __init__(self, inner, ix):
        self.inner, self.ix = inner, list(ix)

    def fit(self, X, y, Xv=None, yv=None):
        self.inner.fit(X[:, self.ix], y, None if Xv is None else Xv[:, self.ix], yv)
        return self

    def refit(self, X, y):
        if hasattr(self.inner, "refit"):
            self.inner.refit(X[:, self.ix], y)
        return self

    def predict(self, X):
        return self.inner.predict(np.asarray(X)[:, self.ix])


def model_specs(cols: list[str]) -> list[tuple[str, dict, callable]]:
    """(이름, 장부 params, 모델 공장). 순서 = 실행 순서. Ridge 가 먼저(비교 기준)."""
    ci = [cols.index(c) for c in baselines.CLASSIC]
    specs = [
        ("Ridge", dict(model="RidgeCV", alphas=list(baselines.RidgeCV.alphas)), lambda: baselines.RidgeCV()),
        ("OLS-3", dict(model="OLS", cols=baselines.CLASSIC), lambda: OLSRefit(cols=ci)),
        ("OLS-all", dict(model="OLS"), lambda: OLSRefit()),
        ("Lasso", dict(model="LassoCV", alphas=list(baselines.LassoCV.alphas)), lambda: baselines.LassoCV()),
        ("ENet", dict(model="ElasticNetCV", l1_ratio=0.5, alphas=list(ElasticNetCV.alphas)), lambda: ElasticNetCV()),
    ]
    for d in (1, 2, 3, 6):
        specs.append((f"GBM-d{d}", dict(model="LightGBM", **{k: v for k, v in GBM(d).kw.items()
                                                             if k not in ("n_jobs", "verbose")}),
                      lambda d=d: GBM(d)))
    for nm, h in (("NN1", (32,)), ("NN2", (32, 16)), ("NN3", (32, 16, 8))):
        m = MLP(h)
        specs.append((nm, dict(model="MLP", hidden=list(h), l1s=list(m.l1s), seeds=list(m.seeds), lr=m.lr,
                               batch=m.batch, max_epochs=m.max_epochs, patience=m.patience),
                      lambda h=h: MLP(h)))
    return specs


# ── 실행 · 캐시 · 장부 ───────────────────────────────────────────────────────

class Ctx:
    """패널·분할·기준 예측을 한 번 만들어 들고 다닌다."""

    def __init__(self):
        self.P = P = panel.monthly_panel().dropna(subset=["y_ex"]).reset_index(drop=True)
        self.Q, self.cols = panel.prepare(P)
        assert (self.Q["ticker"].to_numpy() == P["ticker"].to_numpy()).all()
        self.folds = cv.walk_forward(self.Q["date"], self.Q["label_end"], first_test=FIRST_TEST,
                                     refit_months=REFIT, val_months=VAL)
        if DEV:
            self.folds = self.folds[:2]
        self.bench = evaluate.hist_mean(self.Q, "y_ex", self.Q["date"])
        # 횡단면 라벨: 날짜별 평균을 뺀 y_ex. 같은 날 모든 종목에 공통인 부분(피처로는 못 맞히는 잡음)을 지운다.
        # 🔴 같은 날짜 안의 평균이라 그 날짜 라벨만 쓴다 — 학습 행의 라벨은 퍼지로 이미 확정된 것들이다.
        self.Q["y_xs"] = self.Q["y_ex"] - self.Q.groupby("date")["y_ex"].transform("mean")
        self.info = self._info()
        self.R: dict[str, pd.DataFrame] = {}
        self.models: dict[str, list] = {}
        self.fit_secs: dict[str, float] = {}

    def _info(self) -> pd.DataFrame:
        """행별 보조 정보: 원수익·SPY(β 점검), 거래대금 순위(크기 절반), 발표 플래그."""
        Q = self.Q
        I = Q[["date", "ticker", "label_end", "y_raw", "spy_fwd", "dvol_1m"]].copy()
        # 🔴 Q 의 ea_next_exp 는 순위화돼 있다 — 원값(0/1, NaN = 발표 이력 없음 → 0)은 정규화 전 패널에서
        I["ea_next_exp"] = self.P["ea_next_exp"].fillna(0).to_numpy()
        I["big"] = (I["dvol_1m"] >= I.groupby("date")["dvol_1m"].transform("median")).astype(int)
        # 🔴 실현 발표: 라벨 창 (t, t'] 에 반응일이 있는가 — 사후 진단용
        E = panel.earnings_events()[["ticker", "d0"]].dropna()
        E["ticker"] = E["ticker"].astype(str)
        by = {t: np.sort(g["d0"].to_numpy("datetime64[ns]")) for t, g in E.groupby("ticker")}
        flag = np.zeros(len(I), dtype=int)
        tk = I["ticker"].astype(str).to_numpy()
        d = I["date"].to_numpy("datetime64[ns]")
        le = I["label_end"].to_numpy("datetime64[ns]")
        for t in np.unique(tk):
            a = by.get(t)
            if a is None:
                continue
            ix = np.flatnonzero(tk == t)
            flag[ix] = (np.searchsorted(a, le[ix], side="right") - np.searchsorted(a, d[ix], side="right")) > 0
        I["ann_in_win"] = flag
        I["ticker"] = I["ticker"].astype(str)
        return I.drop(columns=["label_end"])

    def run(self, name: str, params: dict, make, fresh=False, base="Ridge", label="y_ex",
            study=STUDY) -> pd.DataFrame:
        """예측(캐시) → 요약 → 장부. 🔴 장부에는 **새로 학습했을 때만** 적는다 — 캐시 재사용은 새 시도가 아니다."""
        cols = self.cols
        f_pred, f_mod = OUT / f"{name}.parquet", OUT / f"{name}.models.pkl"
        if f_pred.exists() and f_mod.exists() and not fresh:
            R = pd.read_parquet(f_pred)
            self.models[name] = pickle.loads(f_mod.read_bytes())
            self.R[name] = R
            return R
        OUT.mkdir(parents=True, exist_ok=True)
        mods = []

        def mk():
            m = make()
            mods.append(m)
            return m

        t0 = time.time()
        R = cv.predict_oos(self.Q, self.folds, cols, label, mk, refit_on_val=True)
        secs = time.time() - t0
        if label != "y_ex":                                   # 학습 라벨과 상관없이 평가는 늘 y_ex 로
            R["y"] = self.Q["y_ex"].to_numpy(float)[np.concatenate([f.test for f in self.folds])]
        R["ticker"] = R["ticker"].astype(str)
        R.to_parquet(f_pred, index=False)
        f_mod.write_bytes(pickle.dumps(mods))
        self.R[name], self.models[name], self.fit_secs[name] = R, mods, secs
        s = evaluate.summarize(R, bench=self.bench)
        if name != base and base in self.R:
            s.update({f"vs_ridge_{k}": v for k, v in evaluate.compare(R, self.R[base]).items()})
        extra = {"vs": base}
        mods_in = [getattr(m, "inner", m) for m in mods]
        if hasattr(mods_in[0], "alpha_"):
            extra["alpha_by_fold"] = [m.alpha_ for m in mods_in]
        if hasattr(mods_in[0], "best_iter_"):
            extra["trees_by_fold"] = [m.best_iter_ for m in mods_in]
        if hasattr(mods_in[0], "l1_"):
            extra["l1_by_fold"] = [m.l1_ for m in mods_in]
            extra["epochs_by_fold"] = [m.epochs_ for m in mods_in]
        registry.log(study, name, {**params, "n_cols": len(cols), "first_test": FIRST_TEST, "refit": REFIT,
                                   "val": VAL, "label": label, **extra},
                     {**s, "fit_secs": secs}, path=LEDGER)
        print(f"  [학습] {name}: {secs:.0f}s · 장부 {study}", flush=True)
        return R


# ── 보조 평가 ────────────────────────────────────────────────────────────────

def raw_beta(R: pd.DataFrame, info: pd.DataFrame) -> dict:
    """원수익(y_raw) 10분위 롱숏을 SPY 수익에 회귀: 남은 β 와 α(연, NW t). y_ex 롱숏이 베타조정인지 점검."""
    M = R[["date", "ticker", "pred"]].merge(info[["date", "ticker", "y_raw", "spy_fwd"]], on=["date", "ticker"])
    pf = evaluate.portfolios(M.rename(columns={"y_raw": "y"}), costs=(0,))
    spy = M.groupby("date")["spy_fwd"].first().reindex(pf.index)
    x, yv = spy.to_numpy(float), pf["ls"].to_numpy(float)
    ok = np.isfinite(x) & np.isfinite(yv)
    b = np.polyfit(x[ok], yv[ok], 1)
    resid = pd.Series(yv[ok] - b[0] * x[ok], index=pf.index[ok])
    return dict(beta=float(b[0]), alpha_ann=float(resid.mean() * 12), alpha_t=float(evaluate.nw_t(resid)))


def permutation_importance(ctx: Ctx, name: str, groups: dict[str, list[int]], reps: int = 2,
                           seed: int = 0) -> pd.DataFrame:
    """OOS 순열 중요도: 폴드별 모델을 그 폴드 시험 행에 — 피처(+_na)를 날짜 안에서 함께 섞은 뒤 IC·R² 감소."""
    rng = np.random.default_rng(seed)
    X = ctx.Q[ctx.cols].to_numpy(np.float32)
    y = ctx.Q["y_ex"].to_numpy(float)
    dates = ctx.Q["date"].to_numpy()
    folds, mods = ctx.folds, ctx.models[name]
    tests = [f.test for f in folds]
    base_pred = np.concatenate([np.asarray(m.predict(X[t]), float).ravel() for m, t in zip(mods, tests)])
    idx = np.concatenate(tests)
    D = pd.DataFrame({"date": dates[idx], "ticker": 0, "y": y[idx]})

    def score(p):
        D["pred"] = p
        return evaluate.rank_ic(D).mean(), evaluate.oos_r2(D["y"], p)

    ic0, r20 = score(base_pred)
    rows = []
    for g, ci in groups.items():
        dic, dr2 = [], []
        for _ in range(reps):
            ps = []
            for m, t in zip(mods, tests):
                Xt = X[t].copy()
                dt = dates[t]
                for dd in np.unique(dt):                       # 🔴 날짜 안에서만 섞는다
                    w = np.flatnonzero(dt == dd)
                    Xt[np.ix_(w, ci)] = Xt[np.ix_(rng.permutation(w), ci)]
                ps.append(np.asarray(m.predict(Xt), float).ravel())
            ic, r2 = score(np.concatenate(ps))
            dic.append(ic0 - ic)
            dr2.append(r20 - r2)
        rows.append(dict(feature=g, ic_drop=float(np.mean(dic)), r2_drop_bp=float(np.mean(dr2) * 1e4)))
    return pd.DataFrame(rows).sort_values("ic_drop", ascending=False).reset_index(drop=True)


def partial_dependence(ctx: Ctx, name: str, feat: str, grid=np.linspace(-1, 1, 9)) -> np.ndarray:
    """부분의존: OOS 행에서 feat 만 격자값으로(그 _na 는 0) 바꾼 평균 예측 (월 수익, 폴드 모델별 자기 시험 행)."""
    X = ctx.Q[ctx.cols].to_numpy(np.float32)
    j = ctx.cols.index(feat)
    jn = ctx.cols.index(feat + "_na") if feat + "_na" in ctx.cols else None
    out = []
    for v in grid:
        ps = []
        for m, f in zip(ctx.models[name], ctx.folds):
            Xt = X[f.test].copy()
            Xt[:, j] = v
            if jn is not None:
                Xt[:, jn] = 0
            ps.append(np.asarray(m.predict(Xt), float).ravel())
        out.append(np.concatenate(ps).mean())
    return np.array(out)


# ── 보고 ────────────────────────────────────────────────────────────────────

def fmt_row(name, s, c=None, dsr=None):
    vs = ""
    if c is not None:
        vs = (f" {c['ic_diff_ann']:+.4f}({c['ic_diff_t']:+.1f}) {c['ls_c10_diff_ann'] * 100:+6.1f}%({c['ls_c10_diff_t']:+.1f})"
              f" {c['dm_stat']:+5.1f}")
    else:
        vs = f" {'—':>14} {'—':>14} {'—':>5}"
    return (f"  {name:<12}{s['r2_zero'] * 100:+6.2f}% {s['r2_hist'] * 100:+6.2f}%  {s['ic_mean']:+.4f}({s['ic_t']:+.1f})"
            f"  {s['ls_c10_ann'] * 100:+6.1f}% {s['ls_c10_sr']:+5.2f}  {s['top_c10_ann'] * 100:+6.1f}% {s['top_c10_sr']:+5.2f}"
            f" {s['turnover_ls']:4.0%}" + vs + (f"  {dsr:.2f}" if dsr is not None else ""))


HDR = ("  모델          R²(0)  R²(hist)  IC (NW t)        롱숏10bp 연/샤프  상위10bp 연/샤프 교체"
       "  vs Ridge: IC차(t)  LS10차(t)      DM    DSR")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--fresh", action="store_true", help="캐시 무시하고 전부 다시 학습 (장부에 다시 적힌다)")
    a = ap.parse_args()
    buf = io.StringIO()

    class Tee(io.TextIOBase):
        def write(self, s):
            sys.__stdout__.write(s)
            buf.write(s)
            return len(s)

        def flush(self):
            sys.__stdout__.flush()

    t_all = time.time()
    with contextlib.redirect_stdout(Tee()):
        report(a.fresh)
        print(f"\n[총 {time.time() - t_all:.0f}s]")
    REPORT.parent.mkdir(parents=True, exist_ok=True)
    REPORT.write_text(buf.getvalue())
    print(f"[저장] {REPORT}")


def report(fresh: bool):
    ctx = Ctx()
    Q, cols = ctx.Q, ctx.cols
    print(f"KAN-23 횡단면 ML — {'DEV ' if DEV else ''}장부 {STUDY}")
    print(f"[표본] {len(Q):,}행 · 월말 {Q['date'].nunique()} ({Q['date'].min().date()}~{Q['date'].max().date()}) · "
          f"피처 {len(ALL_FEATS)} → 열 {len(cols)} (결측 표시 포함)")
    for f in ctx.folds:
        print(f"  {f}")

    specs = model_specs(cols)
    print("\n[1·2] 모델 학습 (캐시 있으면 재사용)")
    for name, params, make in specs:
        ctx.run(name, params, make, fresh=fresh)

    # 강건성 재학습: SUE 피처 없이
    nos_cols = [c for c in cols if not any(c == s or c == s + "_na" for s in SUE_COLS)]
    by = {n: (p, m) for n, p, m in specs}
    nos_i = [cols.index(c) for c in nos_cols]
    for b in ("Ridge", "GBM-d3", "NN3"):
        p, mk = by[b]
        ctx.run(f"{b}-noSUE", {**p, "drop": list(SUE_COLS)}, lambda mk=mk: ColSubset(mk(), nos_i),
                fresh=fresh, base="Ridge-noSUE")

    # 확장: 횡단면 라벨(날짜 평균을 뺀 y_ex)로 학습 — 평가는 그대로 y_ex
    for b in ("Ridge", "GBM-d3", "NN3"):
        p, mk = by[b]
        ctx.run(f"{b}-xs", {**p, "target": "y_xs"}, mk, fresh=fresh, label="y_xs")
    XS = ["Ridge-xs", "GBM-d3-xs", "NN3-xs"]

    names = [n for n, _, _ in specs]
    S = {n: evaluate.summarize(ctx.R[n], bench=ctx.bench) for n in ctx.R}
    C = {n: evaluate.compare(ctx.R[n], ctx.R["Ridge"]) for n in names + XS if n != "Ridge"}
    for b in ("GBM-d3", "NN3"):
        C[f"{b}-noSUE"] = evaluate.compare(ctx.R[f"{b}-noSUE"], ctx.R["Ridge-noSUE"])

    # ── 다중검정: 장부 ──
    L = registry.load(STUDY, path=LEDGER)
    N = len(L)
    Lr = L.drop_duplicates("name", keep="last").set_index("name")
    Ld = registry.deflate(L, "ls_c10", n_trials=N).drop_duplicates("name", keep="last").set_index("name")
    dsr = {n: float(Ld.loc[n, "ls_c10_dsr"]) for n in Ld.index}

    print(f"\n[3] 표본 밖 성과 — 시험 {S['Ridge']['n_dates']}개월 · {S['Ridge']['n_rows']:,}행 "
          f"(롱숏 = y_ex 베타조정 초과수익, 편도 10bp, 교체 = 롱숏 회당 교체율)")
    print(HDR)
    for n in names + XS + ["Ridge-noSUE", "GBM-d3-noSUE", "NN3-noSUE"]:
        print(fmt_row(n, S[n], C.get(n), dsr.get(n)))
    print("  (-xs = 날짜 평균을 뺀 라벨로 학습, vs 는 Ridge 대비. noSUE 의 vs 는 Ridge-noSUE 대비. DM < 0 이면 모델 MSE 가 작다)")
    for n in ("GBM-d3-xs", "NN3-xs"):
        c = evaluate.compare(ctx.R[n], ctx.R["Ridge-xs"])
        print(f"  {n} − Ridge-xs: IC {c['ic_diff_ann']:+.4f} (t {c['ic_diff_t']:+.2f}) · LS10 {c['ls_c10_diff_ann'] * 100:+.1f}% "
              f"(t {c['ls_c10_diff_t']:+.2f}) · DM {c['dm_stat']:+.2f}")

    print("\n  비용별 롱숏·상위 롱 (연 %, NW t)")
    for n in names:
        s = S[n]
        print(f"  {n:<12}" + "  ".join(f"LS{c}bp {s[f'ls_c{c}_ann'] * 100:+5.1f}({s[f'ls_c{c}_t']:+.1f})" for c in (0, 10, 25))
              + "  |  " + "  ".join(f"상위{c}bp {s[f'top_c{c}_ann'] * 100:+5.1f}({s[f'top_c{c}_t']:+.1f})" for c in (0, 10, 25))
              + f"  상위−전체 {s['topuni_c0_ann'] * 100:+5.1f}({s['topuni_c0_t']:+.1f})")

    print("\n  원수익(y_raw) 롱숏의 SPY β·α — y_ex 롱숏이 실제로 시장중립인지")
    for n in ("Ridge", "OLS-3", "GBM-d3", "NN3"):
        rb = raw_beta(ctx.R[n], ctx.info)
        print(f"  {n:<12} β {rb['beta']:+.2f} · α 연 {rb['alpha_ann'] * 100:+.1f}% (t {rb['alpha_t']:+.2f})")

    # 폴드별 선택값
    print("\n  폴드 안 선택값 (검증으로만)")
    for n in ("Ridge", "Lasso", "ENet"):
        print(f"  {n:<8} α: {[m.alpha_ for m in ctx.models[n]]}")
    for n in ("GBM-d1", "GBM-d2", "GBM-d3", "GBM-d6", "GBM-d3-xs"):
        print(f"  {n:<8} 그루: {[m.best_iter_ for m in ctx.models[n]]}")
    for n in ("NN1", "NN2", "NN3", "NN3-xs"):
        print(f"  {n:<8} L1: {[m.l1_ for m in ctx.models[n]]} · 에폭(시드 중앙): "
              f"{[int(np.median(m.epochs_)) for m in ctx.models[n]]}")
    nz = [int((np.abs(m.m.coef_) > 0).sum()) for m in ctx.models["Lasso"]]
    print(f"  Lasso 0 아닌 계수 수: {nz} / {len(cols)}")

    # ── 4. 어디서 오는가 ──
    print("\n[4] 비선형 이득은 어디서 — 순열 중요도(OOS, 날짜 안 섞기 ×2, IC 감소 · R² 감소 bp)")
    groups = {f: [cols.index(c) for c in (f, f + "_na") if c in cols] for f in ALL_FEATS}
    PI = {}
    for n in ("Ridge", "GBM-d3", "NN3"):
        PI[n] = permutation_importance(ctx, n, groups)
    T = pd.concat({n: PI[n].set_index("feature")[["ic_drop", "r2_drop_bp"]] for n in PI}, axis=1)
    T = T.sort_values(("GBM-d3", "ic_drop"), ascending=False)
    print("  " + f"{'피처':<16}" + "".join(f"{n + ' ΔIC':>14}{'ΔR²bp':>8}" for n in PI))
    for f, r in T.iterrows():
        print(f"  {f:<16}" + "".join(f"{r[(n, 'ic_drop')]:+14.4f}{r[(n, 'r2_drop_bp')]:+8.1f}" for n in PI))
    gain = np.sum([m.gain() for m in ctx.models["GBM-d3"]], axis=0)
    gser = pd.Series(gain, index=cols)
    gser = pd.Series({f: gser[[cols[i] for i in ix]].sum() for f, ix in groups.items()})
    gser = (gser / gser.sum()).sort_values(ascending=False)
    print("  GBM-d3 gain 비중 상위 8: " + ", ".join(f"{k} {v:.0%}" for k, v in gser.head(8).items()))

    print("\n  상호작용 점검 — 가법 GBM-d1 대비 (짝지은: IC차 t · LS10bp 차 연%(t) · DM)")
    for n in ("GBM-d2", "GBM-d3", "GBM-d6"):
        c = evaluate.compare(ctx.R[n], ctx.R["GBM-d1"])
        print(f"  {n} − d1: IC {c['ic_diff_ann']:+.4f} (t {c['ic_diff_t']:+.2f}) · LS10 {c['ls_c10_diff_ann'] * 100:+.1f}% "
              f"(t {c['ls_c10_diff_t']:+.2f}) · DM {c['dm_stat']:+.2f} (p {c['dm_p']:.2f})")
    c = evaluate.compare(ctx.R["GBM-d1"], ctx.R["Ridge"])
    print(f"  GBM-d1 − Ridge (가법 비선형 vs 선형): IC {c['ic_diff_ann']:+.4f} (t {c['ic_diff_t']:+.2f}) · "
          f"LS10 {c['ls_c10_diff_ann'] * 100:+.1f}% (t {c['ls_c10_diff_t']:+.2f}) · DM {c['dm_stat']:+.2f}")

    top3 = list(T.index[:3])
    grid = np.linspace(-1, 1, 9)
    print(f"\n  부분의존 — GBM-d3 순열 상위 3 피처, 격자 = 날짜 안 순위 [-1..1], 값 = 평균 예측 월 bp")
    print("  " + f"{'':<22}" + "".join(f"{g:+7.2f}" for g in grid))
    for f in top3:
        for n in ("Ridge", "GBM-d3", "NN3"):
            pdv = partial_dependence(ctx, n, f, grid) * 1e4
            print(f"  {f + ' · ' + n:<22}" + "".join(f"{v:+7.1f}" for v in pdv))

    # ── 5. 강건성 ──
    print("\n[5] 강건성 — 같은 예측을 나눠 본다 (장부 " + STUDY_SLICE + "); 짝 비교는 같은 조각의 Ridge 대비")
    info = ctx.info
    slices = {
        "2017": lambda D: D["date"].dt.year == 2017,
        "2018–2020": lambda D: D["date"].dt.year.between(2018, 2020),
        "2021–2026": lambda D: D["date"].dt.year >= 2021,
        "거래대금 큰 절반": lambda D: D["big"] == 1,
        "거래대금 작은 절반": lambda D: D["big"] == 0,
        "실현 발표 달 제외(진단)": lambda D: D["ann_in_win"] == 0,
        "실현 발표 달만(진단)": lambda D: D["ann_in_win"] == 1,
        "ea_next_exp=0 (거래가능)": lambda D: D["ea_next_exp"] < 0.5,
    }
    rob_models = ("Ridge", "OLS-3", "GBM-d3", "NN3")
    slice_rows = []
    new_slice_log = not (registry.load(STUDY_SLICE, path=LEDGER).shape[0]) or bool(ctx.fit_secs)
    for sl, fn in slices.items():
        print(f"  ── {sl}")
        Rs = {}
        for n in rob_models:
            D = ctx.R[n].merge(info, on=["date", "ticker"], how="left")
            Rs[n] = D[fn(D)][["date", "ticker", "y", "pred", "fold"]]
        if Rs["Ridge"]["date"].nunique() < 6:
            print("  (월 6개 미만 — 건너뜀)")
            continue
        for n in rob_models:
            s = evaluate.summarize(Rs[n], bench=ctx.bench)
            c = evaluate.compare(Rs[n], Rs["Ridge"]) if n != "Ridge" else None
            print("  " + fmt_row(n, s, c)[2:])
            slice_rows.append(dict(slice=sl, model=n, **{k: s[k] for k in ("ic_mean", "ic_t", "ls_c10_ann", "ls_c10_t",
                                                                              "r2_zero")}))
            if new_slice_log:
                registry.log(STUDY_SLICE, f"{n}|{sl}", dict(model=n, slice=sl),
                             {**s, **({f"vs_ridge_{k}": v for k, v in c.items()} if c else {})}, path=LEDGER)

    print("\n  SUE 피처 제외 재학습 (전 피처 대비 짝 비교: 같은 모델 전 피처 − noSUE)")
    for n in ("Ridge", "GBM-d3", "NN3"):
        c = evaluate.compare(ctx.R[n], ctx.R[f"{n}-noSUE"])
        s0, s1 = S[n], S[f"{n}-noSUE"]
        print(f"  {n:<8} IC {s0['ic_mean']:+.4f} → noSUE {s1['ic_mean']:+.4f} · 차 t {c['ic_diff_t']:+.2f} · "
              f"LS10 {s0['ls_c10_ann'] * 100:+.1f}% → {s1['ls_c10_ann'] * 100:+.1f}% (차 t {c['ls_c10_diff_t']:+.2f})")

    # ── 6. 다중검정 ──
    print(f"\n[6] 다중검정 — 장부 {STUDY}: {N}줄 (설정 {L['name'].nunique()}개), 조각 장부 {STUDY_SLICE}: "
          f"{registry.n_trials(STUDY_SLICE, path=LEDGER)}줄")
    best = max(names, key=lambda n: S[n]["ls_c10_srpp"])
    r = Ld.loc[best]
    print(f"  최고 롱숏(10bp, 월 SR 기준): {best} — 월 SR {r['ls_c10_srpp']:+.3f} (연 {S[best]['ls_c10_sr']:+.2f}) · "
          f"SR0 {r['ls_c10_sr0']:.3f} (N={N}, V=설정 간 월 SR 분산) · DSR {r['ls_c10_dsr']:.3f}")
    d1 = registry.deflated_sharpe(r["ls_c10_srpp"], int(r["ls_c10_n"]), 1, None, r["ls_c10_skew"], r["ls_c10_kurt"])
    print(f"  (참고: N=1 로 깎지 않은 PSR(SR>0) = {d1['dsr']:.3f})")
    comp = [n for n in names if n != "Ridge"] + XS + ["GBM-d3-noSUE", "NN3-noSUE"]
    pic = np.array([C[n]["ic_diff_p"] for n in comp])
    pls = np.array([C[n]["ls_c10_diff_p"] for n in comp])
    pdm = np.array([C[n]["dm_p"] for n in comp])
    h_ic, h_ls, h_dm = registry.holm(pic), registry.holm(pls), registry.holm(pdm)
    print(f"  모델 vs Ridge Holm 보정 (가족 = {len(comp)}개 비교, 검정별로)")
    print(f"  {'모델':<14}{'IC차 p':>9}{'Holm':>7}{'LS10차 p':>10}{'Holm':>7}{'DM p':>8}{'Holm':>7}")
    for i, n in enumerate(comp):
        print(f"  {n:<14}{pic[i]:9.3f}{h_ic[i]:7.3f}{pls[i]:10.3f}{h_ls[i]:7.3f}{pdm[i]:8.3f}{h_dm[i]:7.3f}")
    pd.DataFrame(slice_rows).to_csv(OUT / "slices.csv", index=False)


if __name__ == "__main__":
    main()
