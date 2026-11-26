"""시간 순서 교차검증 — 확장창 walk-forward + 퍼지·엠바고 + 시간순 검증 구간.

── 왜 ──────────────────────────────────────────────────────────────────────
무작위 k-fold 는 패널에서 두 번 샌다. ① 미래 달이 학습에 들어간다. ② 라벨 창이 겹치는 이웃 행
(예: 월말 t 행의 라벨 = t→t+1 개월 수익)이 학습·시험에 나뉘어 들어가 같은 수익을 두 번 본다.
그래서 학습은 항상 시험보다 **과거**이고, 라벨 창이 시험 시작을 넘는 학습 행은 버린다(퍼지).

── 정의 ────────────────────────────────────────────────────────────────────
시험 블록   first_test 부터 refit_months 개월씩. 블록마다 모델을 한 번 학습하고 블록 안의 모든
            날짜를 예측한다 (예: refit_months=12 → 매년 재학습 · 매달 예측).
학습 후보   date < t_test 이고 label_end ≤ t_test − embargo 인 행.  t_test = 블록 첫 행의 날짜.
            🔴 퍼지: 라벨이 t_test 뒤에 확정되는 행(라벨 창이 시험 창과 겹치는 행)은 뺀다.
            label_end 가 정확히 t_test 인 행은 남는다 — t_test 종가에 이미 알려진 라벨이다.
검증        학습 후보 중 마지막 val_months 개월 (date ≥ t_test − val_months). 조기 종료·하이퍼파라미터용.
            안쪽 학습 = 후보 중 date < t_val 이고 label_end ≤ t_val − embargo  (같은 퍼지를 한 번 더).
엠바고      embargo_days 달력일만큼 학습 라벨 끝을 시험(검증) 시작보다 더 앞으로 당긴다.
            확장창(학습이 늘 시험보다 과거)에서는 퍼지만으로 겹침은 없다 — 엠바고는 라벨 밖의
            자기상관(예: 변동성 군집)까지 떼어 놓고 싶을 때 쓴다.

── 한계 ──────────────────────────────────────────────────────────────────
· 블록 안에서는 모델이 고정이다 — 블록 뒤쪽 날짜는 그 사이 새로 확정된 라벨을 못 쓴다(보수적).
· label_end 가 없으면(NaN) 라벨이 확정 안 된 행으로 보고 학습에서 뺀다.

사용:
    folds = walk_forward(P["date"], P["label_end"], first_test="2018-01-01", refit_months=12, val_months=24)
    pred = predict_oos(P, folds, cols, "y_ex", lambda: baselines.RidgeCV())
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

import numpy as np
import pandas as pd


@dataclass
class Fold:
    """한 시험 블록. 인덱스는 입력 배열의 **위치**(np.ndarray[int])."""
    k: int
    train: np.ndarray        # 안쪽 학습 (val_months=0 이면 학습 후보 전체)
    val: np.ndarray          # 시간순 검증 (없으면 빈 배열)
    test: np.ndarray
    test_start: pd.Timestamp  # 블록 첫 행 날짜
    test_end: pd.Timestamp    # 블록 마지막 행 날짜

    @property
    def fit(self) -> np.ndarray:
        """학습 + 검증 (검증으로 하이퍼파라미터를 고른 뒤 다시 학습할 때)."""
        return np.concatenate([self.train, self.val])

    def __repr__(self):
        return (f"Fold({self.k}: 시험 {self.test_start.date()}~{self.test_end.date()} {len(self.test):,}행 · "
                f"학습 {len(self.train):,} · 검증 {len(self.val):,})")


def walk_forward(dates, label_end=None, *, first_test, refit_months: int = 12, val_months: int = 0,
                 embargo_days: int = 0, min_train_dates: int = 24, last_test=None) -> list[Fold]:
    """확장창 walk-forward 분할.

    dates         행별 날짜 (기준일 — 피처가 알려진 시점)
    label_end     행별 라벨 확정일. None 이면 date 와 같다고 본다(라벨이 그날 확정 — 퍼지 없음).
    first_test    첫 시험 블록 시작 (이 날짜 이상인 첫 날짜부터)
    refit_months  재학습 주기 = 시험 블록 길이 (달력 개월)
    val_months    학습 후보의 마지막 몇 개월을 검증으로 (0 이면 검증 없음)
    embargo_days  퍼지 뒤에 더 띄울 달력일
    min_train_dates 학습 날짜 수가 이보다 적은 블록은 건너뛴다
    last_test     시험 블록 끝 (포함). None 이면 데이터 끝까지
    """
    d = pd.DatetimeIndex(pd.to_datetime(np.asarray(dates)))
    le = d if label_end is None else pd.DatetimeIndex(pd.to_datetime(np.asarray(label_end)))
    dv, lv = d.to_numpy(), le.to_numpy()
    has_label = ~pd.isna(lv)
    emb = np.timedelta64(int(embargo_days), "D")
    uniq = np.unique(dv)
    start = pd.Timestamp(first_test)
    stop = pd.Timestamp(last_test) if last_test is not None else pd.Timestamp(uniq[-1])
    folds = []
    k = 0
    while start <= stop:
        nxt = start + pd.DateOffset(months=refit_months)
        in_blk = (dv >= np.datetime64(start)) & (dv < np.datetime64(nxt)) & (dv <= np.datetime64(stop))
        if in_blk.any():
            t_test = dv[in_blk].min()
            cand = (dv < t_test) & has_label & (lv <= t_test - emb)
            if cand.any():
                if val_months > 0:
                    t_val0 = np.datetime64(pd.Timestamp(t_test) - pd.DateOffset(months=val_months))
                    val = cand & (dv >= t_val0)
                    t_val = dv[val].min() if val.any() else t_test
                    tr = cand & (dv < t_val) & (lv <= t_val - emb)
                else:
                    val = np.zeros_like(cand)
                    tr = cand
                if len(np.unique(dv[tr])) < min_train_dates:       # 안쪽 학습 기준으로 센다
                    start = nxt
                    continue
                folds.append(Fold(k, np.flatnonzero(tr), np.flatnonzero(val), np.flatnonzero(in_blk),
                                  pd.Timestamp(t_test), pd.Timestamp(dv[in_blk].max())))
                k += 1
        start = nxt
    return folds


def predict_oos(P: pd.DataFrame, folds: list[Fold], cols: list[str], label: str,
                make_model: Callable[[], object], date_col: str = "date", keep=("ticker",),
                refit_on_val: bool = False, verbose: bool = False) -> pd.DataFrame:
    """폴드마다 make_model() 새 모델 → fit(X_tr, y_tr, X_val, y_val) → predict(X_test).

    반환: date, (keep 열), y(라벨), pred, fold — 시험 행만, 날짜순.
    학습·검증에서 라벨이 NaN 인 행은 뺀다. 시험 행은 라벨이 NaN 이어도 예측한다(실전 예측 달).
    refit_on_val=True 면 검증으로 고른 모델을 학습+검증으로 다시 학습한다(모델이 refit 을 지원할 때).
    """
    X = P[cols].to_numpy(dtype="float32")
    y = P[label].to_numpy(dtype="float64")
    out = []
    for f in folds:
        tr = f.train[np.isfinite(y[f.train])]
        va = f.val[np.isfinite(y[f.val])]
        m = make_model()
        m.fit(X[tr], y[tr], X[va] if len(va) else None, y[va] if len(va) else None)
        if refit_on_val and len(va) and hasattr(m, "refit"):
            m.refit(np.concatenate([X[tr], X[va]]), np.concatenate([y[tr], y[va]]))
        p = np.asarray(m.predict(X[f.test]), dtype="float64").ravel()
        o = P.iloc[f.test][[date_col, *keep]].copy()
        o["y"], o["pred"], o["fold"] = y[f.test], p, f.k
        out.append(o)
        if verbose:
            print(f"  {f}")
    R = pd.concat(out, ignore_index=True)
    return R.rename(columns={date_col: "date"})
