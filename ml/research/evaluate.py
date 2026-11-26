"""표본 밖 예측 평가 — R², 순위 IC, 10분위 포트폴리오(비용 포함), 짝지은 증분, Diebold–Mariano.

── 왜 ──────────────────────────────────────────────────────────────────────
예측 모델을 '정확도'로만 보면 거래 가능한지를 모른다. 같은 예측을 세 겹으로 잰다:
① 통계 — OOS R²(Gu–Kelly–Xiu 2020), 날짜별 순위 IC 의 Newey–West t
② 경제 — 10분위 롱숏·상위 10분위 롱(동일가중, 베타조정 초과수익), 회전율, 편도 0/10/25bp 순수익
③ 비교 — 기준 모델 대비 날짜별 차이의 NW t, 예측 손실의 Diebold–Mariano
모든 시계열 통계는 **날짜별 한 값**으로 접은 뒤 시간축에서 낸다(Fama–MacBeth 식) — 같은 달의
종목 500개는 독립 표본이 아니다.

── 정의 ────────────────────────────────────────────────────────────────────
입력 R     cv.predict_oos 의 출력 — 열 date, ticker, y(라벨), pred.
R²_zero    1 − Σ(y − ŷ)² / Σ y²             (GKX: 기준 예측 0 — 초과수익 평균을 0 으로 본다)
R²_hist    1 − Σ(y − ŷ)² / Σ(y − ȳ_과거)²    ȳ_과거 = 그 날짜에 확정된 라벨들의 누적 평균(hist_mean)
IC_t       날짜 t 안에서 pred 와 y 의 스피어만 순위상관.
10분위     날짜별 pred 순위 상위 10% 롱 · 하위 10% 숏, 각 다리 동일가중(다리마다 자본 1).
           수익 = 라벨(월말 패널이면 y_ex = β 만큼 SPY 를 숏한 베타조정 초과수익).
회전       Σ|w_t − w_{t−1}| (편도 거래 금액, 롱숏은 두 다리 합). 표에는 ÷2 한 '교체율'로 낸다.
           🔴 보유 중 가격 변화로 인한 비중 표류는 무시 — overlay 와 같은 관례(회전 약간 과소).
순수익     총수익 − c/1e4 × Σ|Δw|   (c = 편도 bp). 헤지 SPY 거래·차입 비용은 없다.
NW t       overlay.nw_t (Bartlett, lag = ⌊4(n/100)^(2/9)⌋).
DM         d_t = L_a,t − L_b,t (날짜별 평균 손실) → mean/√(LRV/T), HLN 소표본 보정, t(T−1) 분포.

── 한계 ──────────────────────────────────────────────────────────────────
· 상폐 수익 없음(라벨에서 0) · 헤지 비용 없음 · 비중 표류 무시.
· 롱숏의 숏 다리 차입비 없음 — 대형주라 작지만 0 은 아니다.
"""
from __future__ import annotations

import math
import sys
from pathlib import Path

import numpy as np
import pandas as pd

_PEAD_DIR = Path(__file__).resolve().parent.parent / "pead"
if str(_PEAD_DIR) not in sys.path:
    sys.path.insert(0, str(_PEAD_DIR))
from overlay import nw_t  # noqa: E402  (pead 연구와 같은 NW t)

COSTS = (0, 10, 25)


def _p_norm(t: float) -> float:
    return math.erfc(abs(t) / math.sqrt(2)) if np.isfinite(t) else np.nan


def nw_lag(n: int) -> int:
    return int(np.floor(4 * (n / 100) ** (2 / 9)))


def lrv(x, lag: int | None = None) -> float:
    """Bartlett 장기분산 (nw_t 의 분모 × n 과 같은 식)."""
    x = np.asarray(x, float)
    x = x[np.isfinite(x)]
    n = len(x)
    lag = nw_lag(n) if lag is None else lag
    e = x - x.mean()
    s = e @ e / n
    for k in range(1, lag + 1):
        s += 2 * (1 - k / (lag + 1)) * (e[k:] @ e[:-k]) / n
    return s


# ── 통계 ────────────────────────────────────────────────────────────────────

def oos_r2(y, pred, bench=None) -> float:
    """1 − Σ(y−ŷ)²/Σ(y−b)². bench=None 이면 b=0 (GKX). NaN 행은 뺀다."""
    y, p = np.asarray(y, float), np.asarray(pred, float)
    b = np.zeros_like(y) if bench is None else np.asarray(bench, float)
    ok = np.isfinite(y) & np.isfinite(p) & np.isfinite(b)
    return float(1 - ((y[ok] - p[ok]) ** 2).sum() / ((y[ok] - b[ok]) ** 2).sum())


def hist_mean(P: pd.DataFrame, label: str, dates, date_col: str = "date", end_col: str = "label_end") -> pd.Series:
    """날짜 d 마다 'label_end ≤ d 인(= d 에 확정된) 라벨'의 누적 평균. R²_hist 의 기준 예측.
    🔴 라벨이 확정된 행만 — date ≤ d 로 자르면 아직 안 끝난 라벨 창이 들어간다."""
    Q = P[[end_col, label]].dropna().sort_values(end_col)
    e = Q[end_col].to_numpy()
    cs = np.cumsum(Q[label].to_numpy(float))
    d = pd.DatetimeIndex(pd.unique(pd.to_datetime(np.asarray(dates))))
    n = np.searchsorted(e, d.to_numpy(), side="right")
    m = np.where(n > 0, cs[np.maximum(n - 1, 0)] / np.maximum(n, 1), np.nan)
    return pd.Series(m, index=d)


def rank_ic(R: pd.DataFrame, pred: str = "pred", y: str = "y", date_col: str = "date",
            min_n: int = 20) -> pd.Series:
    """날짜별 스피어만 IC (종목 min_n 미만인 날은 뺀다)."""
    D = R[[date_col, pred, y]].dropna()
    g = D.groupby(date_col, sort=True)
    a = g[pred].rank() - g[pred].transform("size").add(1) / 2
    b = g[y].rank() - g[y].transform("size").add(1) / 2
    num = (a * b).groupby(D[date_col]).sum()
    den = np.sqrt((a * a).groupby(D[date_col]).sum() * (b * b).groupby(D[date_col]).sum())
    n = g.size()
    ic = (num / den.replace(0, np.nan))[n >= min_n]
    return ic.rename("ic")


def ic_summary(ic: pd.Series) -> dict:
    t = nw_t(ic)
    return dict(ic_mean=float(ic.mean()), ic_std=float(ic.std()), ic_ir=float(ic.mean() / ic.std()) if ic.std() else np.nan,
                ic_t=float(t), ic_p=_p_norm(t), ic_hit=float((ic > 0).mean()), ic_n=int(ic.notna().sum()))


def series_stats(x: pd.Series, ppy: float) -> dict:
    """연환산 평균·변동성·샤프, NW t, 기간당 샤프(srpp)·왜도·첨도(DSR 용, 첨도는 정규=3)."""
    x = pd.Series(x).dropna()
    sd = x.std()
    t = nw_t(x)
    return dict(ann=float(x.mean() * ppy), vol=float(sd * np.sqrt(ppy)),
                sr=float(x.mean() / sd * np.sqrt(ppy)) if sd else np.nan,
                t=float(t), p=_p_norm(t), srpp=float(x.mean() / sd) if sd else np.nan,
                skew=float(x.skew()), kurt=float(x.kurt() + 3), n=int(len(x)))


# ── 포트폴리오 ──────────────────────────────────────────────────────────────

def portfolios(R: pd.DataFrame, pred: str = "pred", ret: str = "y", n_q: int = 10, costs=COSTS,
               date_col: str = "date", name_col: str = "ticker") -> pd.DataFrame:
    """날짜별 분위 포트폴리오 수익·회전.

    열: n, uni(전 종목 동일가중), top, bot, ls(=top−bot), to_top, to_ls (Σ|Δw|),
        top_net{c}, ls_net{c}, top_uni(=top−uni, 유니버스 대비 상위 분위).
    첫 날의 회전은 0 에서 쌓는 것으로 센다(overlay 관례).
    """
    D = R[[date_col, name_col, pred, ret]].dropna().copy()
    D[name_col] = D[name_col].astype(str)
    g = D.groupby(date_col, sort=True)
    q = g[pred].rank(method="first", pct=True)
    top, bot = q > 1 - 1 / n_q, q <= 1 / n_q
    D["wt"] = top / top.groupby(D[date_col]).transform("sum")
    D["wb"] = bot / bot.groupby(D[date_col]).transform("sum")
    D = D.fillna({"wt": 0.0, "wb": 0.0})
    out = pd.DataFrame({"n": g.size(), "uni": g[ret].mean()})
    out["top"] = (D["wt"] * D[ret]).groupby(D[date_col]).sum()
    out["bot"] = (D["wb"] * D[ret]).groupby(D[date_col]).sum()
    out["ls"] = out["top"] - out["bot"]
    out["top_uni"] = out["top"] - out["uni"]
    Wt = D.pivot_table(index=date_col, columns=name_col, values="wt", fill_value=0.0).reindex(out.index).fillna(0)
    Wb = D.pivot_table(index=date_col, columns=name_col, values="wb", fill_value=0.0).reindex(out.index).fillna(0)
    out["to_top"] = Wt.diff().abs().sum(axis=1)
    out.iloc[0, out.columns.get_loc("to_top")] = Wt.iloc[0].abs().sum()
    tb = Wb.diff().abs().sum(axis=1)
    tb.iloc[0] = Wb.iloc[0].abs().sum()
    out["to_ls"] = out["to_top"] + tb
    for c in costs:
        out[f"top_net{c}"] = out["top"] - c / 1e4 * out["to_top"]
        out[f"ls_net{c}"] = out["ls"] - c / 1e4 * out["to_ls"]
    return out


# ── 요약 · 비교 ───────────────────────────────────────────────────────────────

def summarize(R: pd.DataFrame, ppy: float = 12, costs=COSTS, n_q: int = 10, bench=None,
              pred: str = "pred", y: str = "y") -> dict:
    """registry.log 에 바로 넣을 평평한 dict.

    bench  R²_hist 용 기준 예측 (행별 배열, 또는 날짜→값 Series — hist_mean 의 출력).
    키: r2_zero, r2_hist, ic_*, ls_c{c}_{ann,vol,sr,t,p,srpp,skew,kurt,n}, top_c{c}_*, topuni_c0_*,
        turnover_ls, turnover_top (회당 교체율 0~1: 상위 = Σ|Δw|/2, 롱숏 = Σ|Δw|/4 — 두 다리 총자본 2 기준), n_dates.
    """
    Rl = R.dropna(subset=[y, pred])
    out = dict(n_rows=int(len(Rl)), n_dates=int(Rl["date"].nunique()), r2_zero=oos_r2(Rl[y], Rl[pred]))
    if bench is not None:
        if isinstance(bench, pd.Series) and isinstance(bench.index, pd.DatetimeIndex):
            b = Rl["date"].map(bench)                                     # 날짜 → 기준값
        else:
            b = pd.Series(np.asarray(bench, float), index=R.index).loc[Rl.index]   # R 과 같은 행 순서
        out["r2_hist"] = oos_r2(Rl[y], Rl[pred], b)
    out.update(ic_summary(rank_ic(Rl, pred, y)))
    pf = portfolios(Rl, pred, y, n_q, costs)
    for c in costs:
        for leg in ("ls", "top"):
            for k, v in series_stats(pf[f"{leg}_net{c}"], ppy).items():
                out[f"{leg}_c{c}_{k}"] = v
    for k, v in series_stats(pf["top_uni"], ppy).items():
        out[f"topuni_c0_{k}"] = v
    out["turnover_ls"] = float(pf["to_ls"].iloc[1:].mean() / 4)
    out["turnover_top"] = float(pf["to_top"].iloc[1:].mean() / 2)
    return out


def paired(a: pd.Series, b: pd.Series, ppy: float = 12) -> dict:
    """날짜별 a − b 의 평균(연환산)·NW t. 같은 날짜만."""
    d = (a - b).dropna()
    t = nw_t(d)
    return dict(diff_ann=float(d.mean() * ppy), diff_t=float(t), diff_p=_p_norm(t), n=int(len(d)))


def compare(Ra: pd.DataFrame, Rb: pd.DataFrame, ppy: float = 12, costs=COSTS, n_q: int = 10,
            loss: str = "mse") -> dict:
    """모델 a 와 기준 b 의 짝지은 비교 (같은 (date, ticker) 행만).

    키: ic_diff_*(날짜별 IC 차), ls_c{c}_diff_*, top_c{c}_diff_*(순수익 차), dm_stat, dm_p (손실 a − b;
        음수면 a 가 낫다).
    """
    k = ["date", "ticker"]
    M = Ra[k + ["y", "pred"]].merge(Rb[k + ["pred"]], on=k, suffixes=("", "_b")).dropna()
    A, B = M[k + ["y", "pred"]], M[k + ["y"]].assign(pred=M["pred_b"])
    out = {f"ic_{kk}": v for kk, v in paired(rank_ic(A), rank_ic(B), ppy=1).items()}
    pa, pb = portfolios(A, n_q=n_q, costs=costs), portfolios(B, n_q=n_q, costs=costs)
    for c in costs:
        for leg in ("ls", "top"):
            for kk, v in paired(pa[f"{leg}_net{c}"], pb[f"{leg}_net{c}"], ppy).items():
                out[f"{leg}_c{c}_{kk}"] = v
    lf = loss_mse if loss == "mse" else loss_qlike
    la = pd.Series(lf(M["y"], M["pred"]), index=M.index).groupby(M["date"]).mean()
    lb = pd.Series(lf(M["y"], M["pred_b"]), index=M.index).groupby(M["date"]).mean()
    dm = diebold_mariano(la, lb)
    out["dm_stat"], out["dm_p"] = dm["stat"], dm["p"]
    return out


# ── 예측 손실 · Diebold–Mariano ─────────────────────────────────────────────

def loss_mse(y, f) -> np.ndarray:
    return (np.asarray(y, float) - np.asarray(f, float)) ** 2


def loss_qlike(rv, f, eps: float = 1e-12) -> np.ndarray:
    """QLIKE (Patton 2011) = rv/f − log(rv/f) − 1. **분산** 단위(σ²)로 넣는다. 0 이 최소."""
    rv = np.maximum(np.asarray(rv, float), eps)
    f = np.maximum(np.asarray(f, float), eps)
    return rv / f - np.log(rv / f) - 1


def diebold_mariano(loss_a, loss_b, h: int = 1, lag: int | None = None) -> dict:
    """DM 검정. 손실 시계열 두 개(같은 날짜). d = a − b; stat < 0 이면 a 의 손실이 작다.
    lag None → max(h−1, NW 자동 lag). HLN(1997) 소표본 보정 후 t(T−1) 양측 p."""
    from scipy import stats as st
    d = (pd.Series(loss_a, dtype=float) - pd.Series(loss_b, dtype=float)).to_numpy()
    d = d[np.isfinite(d)]
    T = len(d)
    if T < 5 or not d.std():
        return dict(stat=np.nan, p=np.nan, mean=float(d.mean()) if T else np.nan, n=T)
    lag = max(h - 1, nw_lag(T)) if lag is None else lag
    dm = d.mean() / np.sqrt(lrv(d, lag) / T)
    dm *= np.sqrt((T + 1 - 2 * h + h * (h - 1) / T) / T)
    p = 2 * st.t.sf(abs(dm), T - 1)
    return dict(stat=float(dm), p=float(p), mean=float(d.mean()), n=T)


def table(s: dict, costs=COSTS) -> str:
    """summarize 결과를 한 덩이 글로."""
    lines = [f"  R²(0) {s['r2_zero'] * 100:+.2f}%" + (f" · R²(과거평균) {s['r2_hist'] * 100:+.2f}%" if "r2_hist" in s else "")
             + f" · IC {s['ic_mean']:+.4f} (NW t {s['ic_t']:+.2f}, 양수 {s['ic_hit']:.0%}, {s['ic_n']}일)",
             f"  회전(회당 교체율) 롱숏 {s['turnover_ls']:.0%} · 상위 {s['turnover_top']:.0%}"]
    for leg, nm in (("ls", "롱숏"), ("top", "상위 롱")):
        lines.append(f"  {nm:<6}" + "  ".join(
            f"{c}bp 연{s[f'{leg}_c{c}_ann'] * 100:+.2f}% 샤프 {s[f'{leg}_c{c}_sr']:+.2f} t {s[f'{leg}_c{c}_t']:+.2f}"
            for c in costs))
    return "\n".join(lines)
