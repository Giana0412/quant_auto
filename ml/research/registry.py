"""실험 장부와 다중검정 — 몇 번 시도했는지 세고, 그 횟수만큼 결과를 깎는다.

── 왜 ──────────────────────────────────────────────────────────────────────
설정을 20개 돌려 가장 좋은 하나를 보고하면 t ≈ 2 는 우연으로도 나온다(overlay.py 가 이미 "24개를
동시에 본다 — |t|≈2 하나는 우연"이라고 적었다). 시도 횟수를 기억에 맡기지 않고 **평가할 때마다
장부에 자동으로 적는다**. 그러면 ① Holm/BH 로 p 를 보정하고 ② Deflated Sharpe Ratio
(Bailey & López de Prado 2014)로 "N 번 시도의 최대값으로 기대되는 샤프"를 넘었는지 볼 수 있다.

── 정의 ────────────────────────────────────────────────────────────────────
장부        RUNS/ledger.jsonl (gitignore) — 한 줄 = 한 평가: ts, study, name, params, metrics, git.
            같은 study 의 줄 수 = 그 연구의 시도 횟수 N. 지우지 않는다(실패한 시도도 센다).
Holm        단계적 FWER 보정.  BH = Benjamini–Hochberg FDR 보정.
SR0         N 개 시도 샤프(기간 단위)의 분산 V 일 때 최대값의 기대치
            = √V · ((1−γ)Φ⁻¹(1 − 1/N) + γ Φ⁻¹(1 − 1/(N·e))),  γ = 오일러–마스케로니 상수.
DSR         Φ( (SR − SR0) √(T−1) / √(1 − γ₃·SR + (γ₄−1)/4·SR²) )
            SR·SR0 는 **기간 단위**(연환산 아님), T = 기간 수, γ₃ 왜도, γ₄ 첨도(정규 = 3).
            DSR ≥ 0.95 이면 "시도 N 번을 감안해도 진짜 SR > 0" 으로 읽는다.

── 한계 ──────────────────────────────────────────────────────────────────
· 시도들은 서로 상관돼 있다(비슷한 피처·기간) → N 은 '독립 시도 수'의 상한이다. DSR 은 보수적이다.
· 장부에 안 적고 돌린 탐색은 세지 못한다 — evaluate 결과를 낼 때는 반드시 log() 를 거쳐라.
"""
from __future__ import annotations

import json
import math
import subprocess
from pathlib import Path

import numpy as np
import pandas as pd

from . import panel

EULER = 0.5772156649015329


def ledger_path() -> Path:
    return panel.RUNS / "ledger.jsonl"


def _git() -> str | None:
    try:
        return subprocess.run(["git", "rev-parse", "--short", "HEAD"], capture_output=True, text=True,
                              cwd=Path(__file__).parent, timeout=5).stdout.strip() or None
    except Exception:
        return None


def _jsonable(x):
    if isinstance(x, dict):
        return {str(k): _jsonable(v) for k, v in x.items()}
    if isinstance(x, (list, tuple)):
        return [_jsonable(v) for v in x]
    if isinstance(x, (np.integer,)):
        return int(x)
    if isinstance(x, (np.floating, float)):
        return None if not np.isfinite(x) else float(x)
    if isinstance(x, (pd.Timestamp, np.datetime64)):
        return str(pd.Timestamp(x).date())
    return x


def log(study: str, name: str, params: dict, metrics: dict, notes: str | None = None,
        path: str | Path | None = None) -> dict:
    """평가 한 번을 장부에 덧붙인다. 반환: 적은 레코드."""
    rec = dict(ts=pd.Timestamp.now().isoformat(timespec="seconds"), study=study, name=name,
               params=_jsonable(params), metrics=_jsonable(metrics), git=_git(), notes=notes)
    p = Path(path) if path else ledger_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    with open(p, "a") as fh:
        fh.write(json.dumps(rec, ensure_ascii=False) + "\n")
    return rec


def load(study: str | None = None, path: str | Path | None = None) -> pd.DataFrame:
    """장부 → 표 (metrics 는 펼쳐서 열로, params 는 dict 그대로)."""
    p = Path(path) if path else ledger_path()
    if not p.exists():
        return pd.DataFrame(columns=["ts", "study", "name", "params"])
    recs = [json.loads(l) for l in p.read_text().splitlines() if l.strip()]
    if study is not None:
        recs = [r for r in recs if r["study"] == study]
    rows = [dict(ts=r["ts"], study=r["study"], name=r["name"], params=r["params"], git=r.get("git"),
                 **r["metrics"]) for r in recs]
    return pd.DataFrame(rows)


def n_trials(study: str | None = None, path=None) -> int:
    return len(load(study, path))


# ── 다중검정 ────────────────────────────────────────────────────────────────

def holm(p) -> np.ndarray:
    """Holm–Bonferroni 보정 p (NaN 은 NaN, m 은 NaN 아닌 개수)."""
    p = np.asarray(p, float)
    out = np.full_like(p, np.nan)
    ok = np.flatnonzero(np.isfinite(p))
    m = len(ok)
    if not m:
        return out
    order = ok[np.argsort(p[ok], kind="stable")]
    adj = np.maximum.accumulate((m - np.arange(m)) * p[order])
    out[order] = np.minimum(adj, 1.0)
    return out


def bh(p) -> np.ndarray:
    """Benjamini–Hochberg 보정 p (q 값)."""
    p = np.asarray(p, float)
    out = np.full_like(p, np.nan)
    ok = np.flatnonzero(np.isfinite(p))
    m = len(ok)
    if not m:
        return out
    order = ok[np.argsort(p[ok], kind="stable")]
    adj = p[order] * m / np.arange(1, m + 1)
    adj = np.minimum.accumulate(adj[::-1])[::-1]
    out[order] = np.minimum(adj, 1.0)
    return out


def adjust(L: pd.DataFrame, p_col: str = "ls_c10_p") -> pd.DataFrame:
    """장부 표에 <p_col>_holm, <p_col>_bh 를 붙인다 (표 전체 = 한 가족)."""
    L = L.copy()
    L[f"{p_col}_holm"] = holm(L[p_col])
    L[f"{p_col}_bh"] = bh(L[p_col])
    return L


# ── Deflated Sharpe Ratio ───────────────────────────────────────────────────

def _ppf(q: float) -> float:
    from scipy.stats import norm
    return float(norm.ppf(q))


def _cdf(x: float) -> float:
    return 0.5 * math.erfc(-x / math.sqrt(2))


def expected_max_sr(n_trials: int, sr_var: float) -> float:
    """N 개 독립 시도(참 SR = 0, 추정 분산 sr_var)의 최대 SR 기대치 — SR0. N = 1 이면 0."""
    if n_trials <= 1:
        return 0.0
    return math.sqrt(sr_var) * ((1 - EULER) * _ppf(1 - 1 / n_trials) + EULER * _ppf(1 - 1 / (n_trials * math.e)))


def psr(sr: float, sr_bench: float, n_obs: int, skew: float = 0.0, kurt: float = 3.0) -> float:
    """Probabilistic Sharpe Ratio: P(참 SR > sr_bench). SR 은 기간 단위."""
    den = 1 - skew * sr + (kurt - 1) / 4 * sr ** 2
    if n_obs < 2 or den <= 0:
        return np.nan
    return _cdf((sr - sr_bench) * math.sqrt(n_obs - 1) / math.sqrt(den))


def deflated_sharpe(sr: float, n_obs: int, n_trials: int, sr_var: float | None = None,
                    skew: float = 0.0, kurt: float = 3.0) -> dict:
    """DSR. sr_var 가 없으면 귀무(SR=0)에서의 추정 분산 1/(T−1) 을 쓴다."""
    v = 1 / max(n_obs - 1, 1) if sr_var is None or not np.isfinite(sr_var) else sr_var
    sr0 = expected_max_sr(n_trials, v)
    return dict(dsr=psr(sr, sr0, n_obs, skew, kurt), sr0=sr0, sr_var=v, n_trials=n_trials)


def deflate(L: pd.DataFrame, prefix: str = "ls_c10", n_trials: int | None = None) -> pd.DataFrame:
    """장부 표의 각 행에 DSR 을 붙인다. N = 표의 행 수(또는 n_trials), V = 행들 srpp 의 분산.
    prefix 는 evaluate.summarize 의 키 접두사 (예: ls_c10 → ls_c10_srpp, _n, _skew, _kurt)."""
    L = L.copy()
    N = n_trials or len(L)
    srs = L[f"{prefix}_srpp"].astype(float)
    V = float(srs.var()) if srs.notna().sum() >= 2 else None
    res = [deflated_sharpe(r[f"{prefix}_srpp"], int(r[f"{prefix}_n"]), N, V,
                           r.get(f"{prefix}_skew", 0.0), r.get(f"{prefix}_kurt", 3.0)) for _, r in L.iterrows()]
    L[f"{prefix}_sr0"] = [x["sr0"] for x in res]
    L[f"{prefix}_dsr"] = [x["dsr"] for x in res]
    return L
