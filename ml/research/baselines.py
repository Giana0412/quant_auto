"""기준 모델 — OLS(고전 피처 몇 개) · Ridge · Lasso, 그리고 연구 코드가 구현할 모델 인터페이스.

── 왜 ──────────────────────────────────────────────────────────────────────
복잡한 모델(LightGBM·MLP·LSTM)의 성과는 **같은 분할·같은 평가**에서 선형 기준을 얼마나 넘는지로만
읽을 수 있다(Gu–Kelly–Xiu 2020 도 OLS-3 → 선형 벌점 → 트리·신경망 순으로 비교한다).
그래서 기준을 여기 고정해 두고, 연구 코드는 같은 인터페이스만 맞추면 cv.predict_oos 에 꽂힌다.

── 인터페이스 (Model) ───────────────────────────────────────────────────────
    fit(X_train, y_train, X_val=None, y_val=None) -> self
        X 는 float32 2차원 배열(열 순서 = cv.predict_oos 의 cols), y 는 float64 1차원.
        X_val/y_val 은 cv 의 시간순 검증 구간 — 조기 종료·하이퍼파라미터 선택에만 쓴다.
        🔴 시험 구간은 절대 들어오지 않는다. 표준화 같은 통계도 X_train 에서만 잡아라.
    predict(X) -> 1차원 배열
    (선택) refit(X, y) — 검증으로 고른 설정으로 학습+검증 전체를 다시 학습.

LightGBM 예 (연구 코드에서):
    class LGBM:
        def __init__(self, **kw): self.kw = kw
        def fit(self, X, y, Xv=None, yv=None):
            import lightgbm as lgb
            self.m = lgb.LGBMRegressor(n_estimators=2000, learning_rate=0.02, verbose=-1, **self.kw)
            cb = [lgb.early_stopping(100, verbose=False)] if Xv is not None else None
            self.m.fit(X, y, eval_set=[(Xv, yv)] if Xv is not None else None, callbacks=cb)
            return self
        def predict(self, X): return self.m.predict(X)

── 정의 ────────────────────────────────────────────────────────────────────
CLASSIC      OLS 에 넣는 고전 피처 3개: mom_12_1(모멘텀) · dvol_1m(크기 대용) · mom_1m(단기 반전).
             GKX 의 OLS-3(크기·장부가/시가·모멘텀) 에서 장부가/시가는 이력이 없어 단기 반전으로 바꿨다.
RidgeCV      alphas 격자에서 검증 MSE 가 가장 작은 α (검증 없으면 학습 안 시간순 마지막 20% 를 검증으로 —
             이 경우 한 달의 종목이 학습·검증에 쪼개질 수 있다. cv.walk_forward 에 val_months 를 주는 쪽을 권한다).
LassoCV      같은 방식.
"""
from __future__ import annotations

from typing import Protocol

import numpy as np

CLASSIC = ["mom_12_1", "dvol_1m", "mom_1m"]


class Model(Protocol):
    def fit(self, X_train, y_train, X_val=None, y_val=None) -> "Model": ...

    def predict(self, X) -> np.ndarray: ...


class Zero:
    """늘 0 을 예측 — R²_zero 의 기준 그 자체, 비교 검정의 귀무 모델."""

    def fit(self, X, y, Xv=None, yv=None):
        return self

    def predict(self, X):
        return np.zeros(len(X))


class OLS:
    """최소제곱(절편 포함). cols 를 주면 그 열 위치만 쓴다 — cv.predict_oos 의 cols 순서 기준."""

    def __init__(self, cols: list[int] | None = None):
        self.cols = cols

    def _x(self, X):
        X = np.asarray(X, float)
        return X if self.cols is None else X[:, self.cols]

    def fit(self, X, y, Xv=None, yv=None):
        from sklearn.linear_model import LinearRegression
        self.m = LinearRegression().fit(self._x(X), y)
        return self

    def predict(self, X):
        return self.m.predict(self._x(X))


class _PenalizedCV:
    """α 격자를 검증 MSE 로 고른다. 🔴 검증이 없으면 학습 **뒤쪽 20%**(행 순서 = 날짜순이어야 한다)."""
    alphas: tuple = ()

    def __init__(self, alphas=None, refit_full: bool = True):
        self.alphas = tuple(alphas or self.alphas)
        self.refit_full = refit_full

    def _make(self, a):
        raise NotImplementedError

    def fit(self, X, y, Xv=None, yv=None):
        X, y = np.asarray(X, float), np.asarray(y, float)
        if Xv is None or len(Xv) == 0:
            cut = int(len(X) * 0.8)
            X, Xv, y, yv = X[:cut], X[cut:], y[:cut], y[cut:]
        Xv, yv = np.asarray(Xv, float), np.asarray(yv, float)
        self.scores_ = {}
        for a in self.alphas:
            m = self._make(a).fit(X, y)
            self.scores_[a] = float(np.mean((yv - m.predict(Xv)) ** 2))
        self.alpha_ = min(self.scores_, key=self.scores_.get)
        if self.refit_full:
            self.m = self._make(self.alpha_).fit(np.vstack([X, Xv]), np.concatenate([y, yv]))
        else:
            self.m = self._make(self.alpha_).fit(X, y)
        return self

    def predict(self, X):
        return self.m.predict(np.asarray(X, float))


class RidgeCV(_PenalizedCV):
    alphas = (1e-1, 1, 10, 100, 1e3, 1e4, 1e5)

    def _make(self, a):
        from sklearn.linear_model import Ridge
        return Ridge(alpha=a)


class LassoCV(_PenalizedCV):
    # 라벨이 월 수익(표준편차 ~0.08)이라 α 는 작다
    alphas = (1e-6, 1e-5, 3e-5, 1e-4, 3e-4, 1e-3)

    def _make(self, a):
        from sklearn.linear_model import Lasso
        return Lasso(alpha=a, max_iter=5000)
