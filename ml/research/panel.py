#!/usr/bin/env python3
"""연구용 패널 — 월말 종목 패널 · 일간 변동성 패널 · 실적 이벤트 표를 한 곳에서 만든다.

── 왜 ──────────────────────────────────────────────────────────────────────
pead.py · overlay.py · signals.py 가 각자 가격을 읽고, 편입 이력을 걸고, 베타조정 초과수익을
다시 계산했다. 다음 연구 셋(ML 횡단면 예측 · 변동성 예측 · 실적 서프라이즈 예측)은 같은 재료를
쓰므로, **미래 정보가 안 새는** 한 벌을 여기서 만들고 캐시해 둔다. 계산 규칙은 pead/overlay 의
것을 그대로 가져다 쓴다(import) — 같은 질문에 다른 숫자가 나오지 않게.

── 정의 ────────────────────────────────────────────────────────────────────
세션         SPY 가격이 있는 날(px.pkl 의 거래일).
월말 행      각 달의 마지막 세션. 데이터 마지막 달(끝나지 않은 달)은 월말이 아니므로 뺀다.
편입         그 행 날짜 t 에 S&P 500 편입 중(pead.membership 의 [편입일, 편출일) 창)이고
             t 종가가 있는 종목만. SPY 는 뺀다.
초과수익     일간 r − β·r_SPY. β = 직전 250일(최소 120) 공분산/분산, 🔴 shift(1), 0~3 클립.
             overlay.beta_excess 와 같은 식이다(test 로 확인).
라벨 y_ex    t 종가 → 다음 월말 t' 종가까지 일간 초과수익의 합 (t+1 … t' 세션).
라벨 y_raw   C[t'] / C[t] − 1 (t' 가격이 없으면 그 창 안 마지막 가격).
label_end    t' — CV 에서 퍼지에 쓴다(라벨이 언제 확정되는가).
피처         전부 **t 종가까지**의 정보. 정의는 FEATURES (README 표와 같다).

── 🔴 미래 정보가 새는 곳과 막은 방법 ────────────────────────────────────────
🔴 편입: 행 날짜 t 에 편입 중인 종목만 (나중에 편입될 종목의 편입 전 구간 제외, 편출 종목은
   편출일 전까지 포함 — 가격이 yfinance 에 남은 것만).
🔴 베타: 라벨용 초과수익의 β 는 shift(1) — 그날 수익이 그날 β 에 안 들어간다. 피처 beta 는 t 까지의
   창(t 종가에 알려진 값)이라 shift 없이 쓴다.
🔴 실적: 반응일 d0 규칙(09:30 ET 전 발표면 그날, 이후면 다음 세션, 00:00 행 제외)은 overlay.event_table
   그대로. 피처는 d0 ≤ t 인 발표만 본다 — 장후 발표(d0 = t+1)는 t 행에 안 들어간다.
🔴 SUE 백분위: 그 발표 **전** 90일(달력, 같은 날 제외) 발표들 안에서의 백분위(pead trail90).
   전체 표본 1/99% 클리핑은 하지 않는다 — 그 경계가 미래 정보다. 원값 sue_raw 는 극단값이 있으니
   rank_normalize 로 순위화해서 쓴다.
🔴 정규화: 횡단면 순위·결측 대체는 **날짜별**로만 한다(rank_normalize, fill_missing). 시계열 전체
   평균·표준편차로 표준화하면 미래 분포가 들어간다.
🔴 업종: 업종은 **오늘의** GICS 이고 편출 종목은 업종이 없다("(편출)") — 그대로 쓰면 '나중에 빠질
   종목'이 표시되는 셈이다. 그래서 기본 피처에서 뺐고 add_sectors 는 경고와 함께만 쓴다.
🔴 라벨 결측: 상장폐지 등으로 창 중간에 가격이 끊기면 그 뒤 초과수익은 0 으로 본다(overlay 와 같다).
   가격이 끝까지 있을 것을 조건으로 걸면 '살아남을 종목'만 고르는 미래 조건이 된다.

── 한계 ──────────────────────────────────────────────────────────────────
· 시가총액·재무 이력(point-in-time)이 없다 — 크기는 거래대금(dvol_1m)으로 대신한다.
  수정종가 × 거래량이라 배당 조정만큼 과거 거래대금이 약간 작게 잡힌다.
· 컨센서스는 Yahoo 가 지금 저장한 값이다 — 발표 당시 화면과 다를 수 있다.
· 상장폐지 수익이 없다(0 처리) → 롱숏 모두 약간 낙관적. 편출 후 yfinance 에서 사라진 티커는 가격 자체가 없다.
· 업종은 오늘 기준.

실행 (캐시 빌드·크기 보고):
  ../headline-sentiment/.venv/bin/python -m research.panel           # ml/ 에서
  QA_PEAD_RUNS=/path/to/pead/runs QA_RESEARCH_RUNS=/path/to/out ...  # 경로 바꾸기
"""
from __future__ import annotations

import json
import os
import pickle
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
_PEAD_DIR = HERE.parent / "pead"
if str(_PEAD_DIR) not in sys.path:
    sys.path.insert(0, str(_PEAD_DIR))

import overlay as _ov  # noqa: E402  (ml/pead/overlay.py — event_table · member_matrix · beta_excess)


def _main_root() -> Path:
    """저장소 본체 경로. git worktree(.claude/worktrees/…) 안에서 돌아도 본체의 캐시를 가리키게 한다."""
    p = str(HERE.parents[1])
    mark = "/.claude/worktrees/"
    return Path(p.split(mark)[0]) if mark in p else Path(p)


# 입력 캐시(pead 가 받아 둔 px.pkl · earnings.pkl · membership.pkl)와 이 패키지의 출력 캐시.
# 둘 다 gitignore 되어 있고 환경변수로 바꿀 수 있다.
DATA_DIR = Path(os.environ.get("QA_PEAD_RUNS", _main_root() / "ml" / "pead" / "runs"))
RUNS = Path(os.environ.get("QA_RESEARCH_RUNS", _main_root() / "ml" / "research" / "runs"))

START = "2014-01-01"        # 월말 패널 첫 행 — 가격이 2013-06 부터라 12-1 모멘텀은 2014-06 부터 찬다
BETA_WIN, BETA_MIN = 250, 120
_NAT = np.datetime64("NaT", "ns")


# ── 원자료 ────────────────────────────────────────────────────────────────

@dataclass
class Raw:
    """가격·거래량·실적·편입 이력 한 벌. C, V 는 세션 × 티커(SPY 포함)."""
    C: pd.DataFrame
    V: pd.DataFrame
    E: pd.DataFrame
    win: dict
    sector: dict
    _cache: dict = field(default_factory=dict, repr=False)

    @property
    def sessions(self) -> pd.DatetimeIndex:
        return self.C.index


def load_raw(data_dir: str | Path | None = None, tickers=None, end=None) -> Raw:
    """캐시만 읽는다(다운로드 없음).

    tickers  일부 종목만(테스트용, SPY 는 항상 포함).
    end      이 날짜까지만 남긴다(가격 세션 ≤ end, 실적 발표 시각 ≤ end 23:59 ET) — 미래 차단 테스트용.
    🔴 pead.prices() 를 부르지 않는다 — 편출 종목 때문에 전체를 다시 받을 수 있다(KAN-12).
    """
    d = Path(data_dir) if data_dir else DATA_DIR
    if not (d / "px.pkl").exists():
        raise FileNotFoundError(f"{d}/px.pkl 이 없다 — QA_PEAD_RUNS 로 pead 캐시 경로를 지정하라")
    C, V = pd.read_pickle(d / "px.pkl")
    with open(d / "membership.pkl", "rb") as fh:
        win, sector = pickle.load(fh)
    E = pd.read_pickle(d / "earnings.pkl")
    E = E.drop_duplicates(["ticker", "ts"]).dropna(subset=["est", "rep"])
    sessions = C["SPY"].dropna().index
    C, V = C.loc[sessions], V.loc[sessions]
    if tickers is not None:
        cols = [c for c in dict.fromkeys(list(tickers) + ["SPY"]) if c in C.columns]
        C, V = C[cols], V[cols]
    if end is not None:
        end = pd.Timestamp(end)
        C, V = C.loc[:end], V.loc[:end]
        ts = pd.to_datetime(E["ts"], utc=True).dt.tz_convert(_ov.ET)
        E = E[ts.dt.tz_localize(None) < end + pd.Timedelta(days=1)]
    E = E[E["ticker"].isin(C.columns)].reset_index(drop=True)
    return Raw(C.astype("float64"), V.astype("float64"), E, win, sector)


def member_mask(raw: Raw) -> pd.DataFrame:
    """[t, 티커] = t 에 S&P 500 편입 중이고 t 종가가 있음. SPY 는 False. (overlay.member_matrix)"""
    M = _ov.member_matrix(raw.win, raw.C.columns, raw.C.index)
    M &= np.isfinite(raw.C.to_numpy())
    if "SPY" in raw.C.columns:
        M[:, list(raw.C.columns).index("SPY")] = False
    return pd.DataFrame(M, index=raw.C.index, columns=raw.C.columns)


def beta_excess(C: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """(R 일간수익, beta_now, ex 초과수익).

    beta_now  t 까지 250일 창의 β (t 종가에 알려진 값 — 피처용, 클립 없음)
    ex        R − clip(beta_now.shift(1), 0, 3) × R_SPY   — overlay.beta_excess 와 같다.
    """
    R = C.pct_change(fill_method=None)
    m = R["SPY"]
    cov = R.rolling(BETA_WIN, min_periods=BETA_MIN).cov(m)
    beta_now = cov.div(m.rolling(BETA_WIN, min_periods=BETA_MIN).var(), axis=0)
    ex = R - beta_now.shift(1).clip(0, 3).mul(m, axis=0)
    return R, beta_now, ex


def month_ends(sessions: pd.DatetimeIndex) -> pd.DatetimeIndex:
    """각 달의 마지막 세션. 🔴 데이터 마지막 달은 끝났는지 알 수 없으니 뺀다."""
    s = pd.Series(sessions, index=sessions)
    last = s.groupby(sessions.to_period("M")).max()
    return pd.DatetimeIndex(last.iloc[:-1].to_numpy())


# ── 실적 이벤트 ────────────────────────────────────────────────────────────

def _events(raw: Raw) -> pd.DataFrame:
    """발표 한 건당 한 행 (편입 여부 무관). overlay.event_table 의 d0 규칙·SUE 정의를 그대로 쓴다.

    열: ticker, j(C 열 번호), i0(반응일 세션 번호), d0, sue, pct(직전 90일 백분위, 편입 중 발표만),
        member(d0 에 편입 중), persist(SUE 지속성), sue_next, d0_next, i0_next.
    🔴 pct 는 pead 정의대로 '편입 중 발표들' 안의 백분위 — 편입 밖 발표는 NaN.
    """
    if "events" in raw._cache:
        return raw._cache["events"]
    allwin = {t: [(pd.NaT, pd.NaT)] for t in raw.C.columns}
    D = _ov.event_table(raw.E, raw.C, allwin)                    # 편입 무관 전체 발표
    Dm = _ov.event_table(raw.E, raw.C, raw.win)                  # pead 정의(편입 중 발표) 백분위
    Dm = Dm[["ticker", "i0", "pct"]].drop_duplicates(["ticker", "i0"], keep="last").assign(member=True)
    D = D.drop(columns=["pct"]).merge(Dm, on=["ticker", "i0"], how="left")
    D["member"] = D["member"].fillna(False).astype(bool)
    # 같은 종목·같은 반응일에 두 행(정정 공시 등)이면 뒤의 것 하나만
    D = D.sort_values(["ticker", "i0"], kind="stable").drop_duplicates(["ticker", "i0"], keep="last")
    D = D.reset_index(drop=True)
    persist = np.full(len(D), np.nan)
    nxt_sue = np.full(len(D), np.nan)
    nxt_i0 = np.full(len(D), -1)
    for _, g in D.groupby("ticker", sort=False):
        ix = g.index.to_numpy()
        s = g["sue"].to_numpy()
        for k in range(len(s)):
            # 🔴 지금 발표까지의 마지막 8건(쌍 7개)만 — 다음 발표는 안 본다
            x = s[max(0, k - 7):k + 1]
            if len(x) >= 6:
                a, b = _rank(x[:-1]), _rank(x[1:])
                if a.std() > 0 and b.std() > 0:
                    persist[ix[k]] = np.corrcoef(a, b)[0, 1]
        nxt_sue[ix[:-1]] = s[1:]
        nxt_i0[ix[:-1]] = g["i0"].to_numpy()[1:]
    D["persist"] = persist
    D["sue_next"] = nxt_sue
    D["i0_next"] = nxt_i0
    sess = raw.sessions.to_numpy().astype("datetime64[ns]")
    D["d0_next"] = pd.DatetimeIndex(np.where(nxt_i0 >= 0, sess[np.maximum(nxt_i0, 0)], _NAT))
    # 다음 발표가 200일 넘게 뒤면(편입 공백·자료 누락) '다음 분기' 라벨로 보지 않는다
    gap = (D["d0_next"] - D["d0"]).dt.days
    D.loc[~(gap <= 200), ["sue_next"]] = np.nan
    raw._cache["events"] = D
    return D


def _rank(x: np.ndarray) -> np.ndarray:
    return pd.Series(x).rank().to_numpy()


def _event_matrices(raw: Raw) -> dict[str, np.ndarray]:
    """[t, j] = t 종가 시점의 '가장 최근 발표(i0 ≤ t)' 정보. 🔴 i0 ≤ t — 장후 발표는 다음 세션부터."""
    T, J = raw.C.shape
    D = _events(raw)
    days = raw.sessions.to_numpy().astype("datetime64[D]")
    out = {k: np.full((T, J), np.nan) for k in ("sue_raw", "sue_pct", "sue_persist", "days_since_ann",
                                                  "ea_month", "ea_next_exp")}
    # 🔴 발표 플래그는 0 으로 시작한다 — 발표 이력이 없는 종목을 NaN 으로 두면 '나중에 발표가 생기는
    # 종목'(0)과 '끝까지 없는 종목'(NaN)이 갈려 미래 정보가 된다 (잘라 낸 데이터 점검에서 발견).
    out["ea_month"][:] = 0.0
    out["ea_next_exp"][:] = 0.0
    tt = np.arange(T)
    for j, g in D.groupby("j", sort=False):
        i0 = g["i0"].to_numpy()
        k = np.searchsorted(i0, tt, side="right") - 1           # 최근 발표 번호 (i0 ≤ t)
        has = k >= 0
        kk = np.where(has, k, 0)
        for col, src in (("sue_raw", "sue"), ("sue_pct", "pct"), ("sue_persist", "persist")):
            v = g[src].to_numpy(float)[kk]
            out[col][:, j] = np.where(has, v, np.nan)
        d0 = g["d0"].to_numpy().astype("datetime64[D]")
        ds = (days - d0[kk]).astype(float)
        out["days_since_ann"][:, j] = np.where(has, ds, np.nan)
        # 발표 달: 반응일이 (t−30일, t] 안
        n_le = np.searchsorted(d0, days, side="right")
        n_30 = np.searchsorted(d0, days - np.timedelta64(30, "D"), side="right")
        out["ea_month"][:, j] = (n_le - n_30 > 0).astype(float)
        # 다음 달 발표 예상: 분기 주기로 한 분기 전, 즉 (t−91일, t−61일] 에 발표가 있었다
        a = np.searchsorted(d0, days - np.timedelta64(91, "D"), side="right")
        b = np.searchsorted(d0, days - np.timedelta64(61, "D"), side="right")
        out["ea_next_exp"][:, j] = (b - a > 0).astype(float)
    return out


# ── 피처 ────────────────────────────────────────────────────────────────────

FEATURES: dict[str, str] = {
    "mom_1m":        "C[t]/C[t−21] − 1 (1개월 수익 — 단기 반전 신호, 기대 부호 −)",
    "strev_1w":      "C[t]/C[t−5] − 1 (1주 수익 — 주간 반전)",
    "exret_1m":      "최근 21세션 베타조정 초과수익 합 (잔차 반전)",
    "mom_3m":        "C[t−21]/C[t−63] − 1 (최근 1개월 건너뜀)",
    "mom_6m":        "C[t−21]/C[t−126] − 1 (최근 1개월 건너뜀)",
    "mom_12_1":      "C[t−21]/C[t−252] − 1 (12-1 모멘텀, Jegadeesh–Titman)",
    "maxret_1m":     "최근 21세션 일간수익 최대값 (MAX, Bali–Cakici–Whitelaw)",
    "rvol_1m":       "최근 21세션 일간수익 표준편차 × √252 (최소 15)",
    "rvol_3m":       "최근 63세션 일간수익 표준편차 × √252 (최소 40)",
    "ivol_3m":       "최근 63세션 베타조정 초과수익 표준편차 × √252 (최소 40)",
    "beta":          "t 까지 250세션(최소 120) cov(r, r_SPY)/var(r_SPY)",
    "beta_down":     "t 까지 250세션 중 r_SPY<0 인 날만으로 계산한 β (최소 50쌍)",
    "vol_chg":       "log(최근 21세션 평균 거래량 / 최근 252세션 평균 거래량)",
    "dvol_1m":       "log(최근 21세션 평균 거래대금 C×V) — 시가총액 이력이 없어 크기 대용",
    "high52":        "C[t] / 최근 252세션 최고 종가 (최소 120)",
    "sue_raw":       "가장 최근 발표(d0 ≤ t)의 (실제 EPS − 예상) ÷ 발표 전날 종가 (클리핑 없음)",
    "sue_pct":       "그 발표의 SUE 가 직전 90일(같은 날 제외) 편입 종목 발표들 중 몇 % 보다 큰가 (100건 미만 NaN)",
    "sue_persist":   "최근 8건 SUE 의 1차 자기 순위상관 (연속 쌍 7개, 최소 6건)",
    "days_since_ann": "t − 최근 발표 반응일 d0 (달력일)",
    "ea_month":      "반응일 d0 ∈ (t−30일, t] 인 발표가 있으면 1",
    "ea_next_exp":   "d0 ∈ (t−91일, t−61일] 발표가 있으면 1 — 분기 주기상 다음 한 달 안 발표 예상",
}


def daily_features(raw: Raw, dtype="float32") -> dict[str, pd.DataFrame]:
    """FEATURES 전부를 세션 × 티커 행렬로. 모든 값은 그 세션 종가까지의 정보만 쓴다.

    메모리: 피처 21개 × 3,393세션 × 605종목 × 4B ≈ 170MB (float32).
    """
    key = ("feat", dtype)
    if key in raw._cache:
        return raw._cache[key]
    C, V = raw.C, raw.V
    R, beta_now, ex = beta_excess(C)
    m = R["SPY"]
    F: dict[str, pd.DataFrame] = {}
    F["mom_1m"] = C / C.shift(21) - 1
    F["strev_1w"] = C / C.shift(5) - 1
    F["exret_1m"] = ex.rolling(21, min_periods=15).sum()
    F["mom_3m"] = C.shift(21) / C.shift(63) - 1
    F["mom_6m"] = C.shift(21) / C.shift(126) - 1
    F["mom_12_1"] = C.shift(21) / C.shift(252) - 1
    F["maxret_1m"] = R.rolling(21, min_periods=15).max()
    F["rvol_1m"] = R.rolling(21, min_periods=15).std() * np.sqrt(252)
    F["rvol_3m"] = R.rolling(63, min_periods=40).std() * np.sqrt(252)
    F["ivol_3m"] = ex.rolling(63, min_periods=40).std() * np.sqrt(252)
    F["beta"] = beta_now
    down = m < 0
    rd, md = R.where(down, axis=0), m.where(down)
    md_pair = rd.mul(0).add(md, axis=0)                          # r 가 있는 하락일만 (쌍 맞춤)
    F["beta_down"] = rd.rolling(BETA_WIN, min_periods=50).cov(md) / md_pair.rolling(BETA_WIN, min_periods=50).var()
    Vp = V.where(V > 0)
    with np.errstate(divide="ignore", invalid="ignore"):
        F["vol_chg"] = np.log(Vp.rolling(21, min_periods=15).mean() / Vp.rolling(252, min_periods=120).mean())
        F["dvol_1m"] = np.log((C * Vp).rolling(21, min_periods=15).mean())
    F["high52"] = C / C.rolling(252, min_periods=120).max()
    for k, v in _event_matrices(raw).items():
        F[k] = pd.DataFrame(v, index=C.index, columns=C.columns)
    F = {k: F[k].replace([np.inf, -np.inf], np.nan).astype(dtype) for k in FEATURES}
    raw._cache[key] = F
    return F


# ── 월말 패널 ──────────────────────────────────────────────────────────────

def monthly_panel(raw: Raw | None = None, start: str = START, cache: bool = True,
                  refresh: bool = False, save: bool | None = None) -> pd.DataFrame:
    """월말 × 편입 종목 패널 (한 행 = (date, ticker)).

    열: date, ticker, FEATURES…, y_ex(다음 달 베타조정 초과수익 합), y_raw(다음 달 수익),
        spy_fwd(같은 창 SPY 수익), fwd_days(창 안 수익이 있는 세션 수), label_end(다음 월말).
    마지막 월말 행은 라벨이 NaN 이다(다음 월말이 아직 없다) — 실전 예측용으로 남긴다.
    캐시: RUNS/monthly_{start}.parquet (px.pkl 이 더 새로우면 다시 만든다).
    """
    name = f"monthly_{start}"
    if raw is None and cache and not refresh:
        hit = _read_cache(name)
        if hit is not None:
            return hit
    save = (raw is None and cache) if save is None else save    # 🔴 테스트용 부분 raw 가 캐시를 덮지 않게
    raw = raw or load_raw()
    F = daily_features(raw)
    C = raw.C
    R, _, ex = beta_excess(C)
    M = member_mask(raw).to_numpy()
    me = month_ends(raw.sessions)
    pos = raw.sessions.get_indexer(me)
    keep = me >= pd.Timestamp(start)
    # 라벨: 행 t (pos[k]) → 다음 월말 (pos[k+1]); 마지막 월말은 다음 월말이 없다
    nxt = np.append(pos[1:], -1)
    pos, nxt, me = pos[keep], nxt[keep], me[keep]
    X = np.nan_to_num(ex.to_numpy())
    cs = np.cumsum(X, axis=0)
    fin = np.cumsum(np.isfinite(R.to_numpy()), axis=0)
    Cf = C.ffill().to_numpy()                                    # 🔴 창 안 마지막 가격 (t 가격은 따로 요구)
    Cv = C.to_numpy()
    spy = Cv[:, list(C.columns).index("SPY")]
    tick = np.asarray(C.columns)
    Fv = {k: F[k].to_numpy() for k in FEATURES}
    parts = []
    for t, t2, d in zip(pos, nxt, me):
        js = np.flatnonzero(M[t])
        blk = {"date": np.full(len(js), d), "ticker": tick[js]}
        for k in FEATURES:
            blk[k] = Fv[k][t, js]
        if t2 >= 0:
            blk["y_ex"] = (cs[t2, js] - cs[t, js]).astype("float32")
            blk["y_raw"] = (Cf[t2, js] / Cv[t, js] - 1).astype("float32")
            blk["spy_fwd"] = np.full(len(js), spy[t2] / spy[t] - 1, "float32")
            blk["fwd_days"] = (fin[t2, js] - fin[t, js]).astype("int16")
            blk["label_end"] = np.full(len(js), raw.sessions[t2])
        else:
            blk["y_ex"] = blk["y_raw"] = blk["spy_fwd"] = np.full(len(js), np.nan, "float32")
            blk["fwd_days"] = np.zeros(len(js), "int16")
            blk["label_end"] = np.full(len(js), pd.NaT)
        parts.append(pd.DataFrame(blk))
    P = pd.concat(parts, ignore_index=True)
    P["date"] = pd.to_datetime(P["date"])
    P["label_end"] = pd.to_datetime(P["label_end"])
    P["ticker"] = P["ticker"].astype("category")
    if save:
        _write_cache(name, P)
    return P


# ── 일간 패널 (변동성) ───────────────────────────────────────────────────────

def daily_panel(raw: Raw | None = None, start: str = START, horizons=(1, 5, 22), cache: bool = True,
                refresh: bool = False, save: bool | None = None) -> pd.DataFrame:
    """일간 × 편입 종목 패널, float32 (변동성 예측용, HAR 식 피처).

    피처 (t 종가까지): r, ex(베타조정 초과), abs_r=|r|, rv_5 · rv_22 · rv_66 = √(최근 n세션 r² 평균)
                      (최소 n·2/3), mkt_r · mkt_rv_5 · mkt_rv_22 (SPY 같은 식), beta(250일).
    라벨: rv_fwd_{h} = √(t+1 … t+h 세션 r² 평균) (h 세션이 다 있어야), label_end_{h} = 세션 t+h.
    🔴 라벨 창의 r 은 '가격이 있는 날'만 — 상장폐지 직전 창은 NaN 이 된다(변동성 라벨은 0 대체가 더 왜곡).
    크기: ~3,200세션 × ~490종목 ≈ 160만 행 × 17열 ≈ 110MB.
    """
    name = f"daily_{start}_{'-'.join(map(str, horizons))}"
    if raw is None and cache and not refresh:
        hit = _read_cache(name)
        if hit is not None:
            return hit
    save = (raw is None and cache) if save is None else save    # 🔴 테스트용 부분 raw 가 캐시를 덮지 않게
    raw = raw or load_raw()
    C = raw.C
    R, beta_now, ex = beta_excess(C)
    R2 = R ** 2
    W = {
        "r": R, "ex": ex, "abs_r": R.abs(),
        "rv_5": np.sqrt(R2.rolling(5, min_periods=4).mean()),
        "rv_22": np.sqrt(R2.rolling(22, min_periods=15).mean()),
        "rv_66": np.sqrt(R2.rolling(66, min_periods=44).mean()),
        "beta": beta_now,
    }
    for h in horizons:
        # t+1 … t+h 의 평균: 뒤집어 rolling 하지 않고 앞으로 h 만큼 당긴 rolling 평균
        W[f"rv_fwd_{h}"] = np.sqrt(R2.rolling(h, min_periods=h).mean().shift(-h))
    mk = R["SPY"]
    mkt = {"mkt_r": mk, "mkt_rv_5": np.sqrt((mk ** 2).rolling(5, min_periods=4).mean()),
           "mkt_rv_22": np.sqrt((mk ** 2).rolling(22, min_periods=15).mean())}
    M = member_mask(raw).to_numpy().copy()
    M[C.index < pd.Timestamp(start)] = False
    t_idx, j_idx = np.nonzero(M)
    out = {"date": C.index[t_idx], "ticker": pd.Categorical(np.asarray(C.columns)[j_idx])}
    for k, v in W.items():
        out[k] = v.to_numpy(dtype="float32")[t_idx, j_idx]
    for k, v in mkt.items():
        out[k] = v.to_numpy(dtype="float32")[t_idx]
    T = len(C)
    for h in horizons:
        e = t_idx + h
        out[f"label_end_{h}"] = pd.DatetimeIndex(np.where(e < T, C.index.to_numpy().astype("datetime64[ns]")[np.minimum(e, T - 1)],
                                                          _NAT))
    P = pd.DataFrame(out)
    if save:
        _write_cache(name, P)
    return P


# ── 실적 이벤트 표 ──────────────────────────────────────────────────────────

def earnings_events(raw: Raw | None = None, start: str = START, cache: bool = True,
                    refresh: bool = False, save: bool | None = None) -> pd.DataFrame:
    """발표 한 건 = 한 행. d0 규칙·SUE 는 pead/overlay 그대로.

    열:
      ticker, d0(반응일), date_pre(d0 직전 세션 — 발표 전 피처의 기준일), member(d0 에 편입 중)
      sue, sue_pct(직전 90일 백분위), surprise 관련 = 이 발표의 값 (d0 에 알려진다)
      pre_<피처>: FEATURES 를 date_pre 종가에 샘플 — pre_sue_* 는 **직전** 발표의 값
      ear     d0 하루 베타조정 초과수익
      drift20 d0+2 … d0+20 초과수익 합 (pead: d0+1 종가 진입), drift60 같은 식 60
      sue_next 같은 종목의 다음 발표 SUE (200일 안), d0_next
    CV 에 쓸 때:
      · 이번 SUE 예측  → 기준일 date_pre, 라벨 끝 d0
      · 다음 SUE 예측  → 기준일 d0, 라벨 끝 d0_next (pre_* + sue 를 피처로)
      · drift 예측     → 기준일 d0 (+1 세션 진입), 라벨 끝 d0+20/60 세션 (label_end_drift20 …)
    🔴 drift·ear 라벨은 미래 가격이 창 끝까지 있어야 계산한다 — 없으면 NaN(그 행은 학습에서 빠진다).
    """
    name = f"events_{start}"
    if raw is None and cache and not refresh:
        hit = _read_cache(name)
        if hit is not None:
            return hit
    save = (raw is None and cache) if save is None else save    # 🔴 테스트용 부분 raw 가 캐시를 덮지 않게
    raw = raw or load_raw()
    D = _events(raw).copy()
    F = daily_features(raw)
    _, _, ex = beta_excess(raw.C)
    X = ex.to_numpy()
    T = len(raw.sessions)
    D = D[(D["d0"] >= pd.Timestamp(start)) & (D["i0"] >= 1)].reset_index(drop=True)
    i0, j = D["i0"].to_numpy(), D["j"].to_numpy()
    D["date_pre"] = raw.sessions[i0 - 1]
    for k in FEATURES:
        D[f"pre_{k}"] = F[k].to_numpy()[i0 - 1, j]
    D["ear"] = X[i0, j]
    cs = np.vstack([np.zeros(X.shape[1]), np.cumsum(np.nan_to_num(X), axis=0)])   # cs[k] = Σ_{<k}
    for h in (20, 60):
        ok = i0 + h < T
        e = np.minimum(i0 + h, T - 1)
        D[f"drift{h}"] = np.where(ok, cs[e + 1, j] - cs[i0 + 2, j], np.nan)
        D[f"label_end_drift{h}"] = pd.DatetimeIndex(np.where(ok, raw.sessions.to_numpy().astype("datetime64[ns]")[e], _NAT))
    D = D.drop(columns=["j", "i0_next"]).rename(columns={"pct": "sue_pct"})
    D["ticker"] = D["ticker"].astype("category")
    if save:
        _write_cache(name, D)
    return D


def add_sectors(P: pd.DataFrame, raw: Raw | None = None, prefix: str = "sec_") -> pd.DataFrame:
    """업종 원-핫을 붙인다. 🔴 오늘의 GICS 이고, 편출 종목은 업종이 없어 모두 0 이 된다 —
    '모두 0' 자체가 '나중에 편출될 종목'이라는 미래 정보다. 업종 중립화(업종 안 순위) 같은 용도로만
    쓰고, 모델 피처로 넣을 거면 편출 종목을 뺀 표본에서 결과가 유지되는지 같이 보여라."""
    sector = raw.sector if raw is not None else load_raw().sector
    s = P["ticker"].astype(str).map(sector).where(lambda x: x != "(편출)")
    return P.join(pd.get_dummies(s, prefix=prefix.rstrip("_"), dtype="int8"))


# ── 횡단면 전처리 ────────────────────────────────────────────────────────────

def rank_normalize(P: pd.DataFrame, cols, by: str = "date") -> pd.DataFrame:
    """날짜별 순위를 [-1, 1] 로 (동률은 평균 순위). NaN 은 NaN 으로 둔다.
    🔴 날짜 안에서만 — 시계열 전체 표준화는 미래 분포를 쓴다."""
    out = P.copy()
    g = P.groupby(by, observed=True, sort=False)
    for c in cols:
        r = g[c].rank(method="average")
        n = g[c].transform("count")
        out[c] = np.where(n > 1, 2 * (r - 1) / (n - 1).where(n > 1) - 1, np.where(n == 1, 0.0, np.nan))
        out[c] = out[c].astype("float32")
    return out


def fill_missing(P: pd.DataFrame, cols, by: str = "date", indicators: bool = True) -> tuple[pd.DataFrame, list[str]]:
    """날짜별 중앙값으로 결측을 채우고, 결측이 있던 열마다 <col>_na (0/1) 표시를 붙인다.
    그날 전부 결측이면 0. 반환: (채운 표, 모델에 넣을 열 이름 목록)."""
    out = P.copy()
    used = list(cols)
    for c in cols:
        na = out[c].isna()
        if not na.any():
            continue
        med = out.groupby(by, observed=True, sort=False)[c].transform("median")
        out[c] = out[c].fillna(med).fillna(0.0)
        if indicators:
            out[f"{c}_na"] = na.astype("int8")
            used.append(f"{c}_na")
    return out, used


def prepare(P: pd.DataFrame, cols=None, by: str = "date") -> tuple[pd.DataFrame, list[str]]:
    """표준 전처리: rank_normalize → fill_missing. 반환 (표, 피처 열 목록)."""
    cols = list(cols or FEATURES)
    return fill_missing(rank_normalize(P, cols, by), cols, by)


# ── 캐시 ────────────────────────────────────────────────────────────────────

def _src_mtime() -> float:
    return max((DATA_DIR / f).stat().st_mtime for f in ("px.pkl", "earnings.pkl", "membership.pkl"))


def _read_cache(name: str) -> pd.DataFrame | None:
    f, meta = RUNS / f"{name}.parquet", RUNS / f"{name}.json"
    if not f.exists() or not meta.exists():
        return None
    try:
        if json.loads(meta.read_text()).get("src_mtime", 0) < _src_mtime():
            return None
    except FileNotFoundError:
        pass
    return pd.read_parquet(f)


def _write_cache(name: str, P: pd.DataFrame):
    RUNS.mkdir(parents=True, exist_ok=True)
    P.to_parquet(RUNS / f"{name}.parquet", index=False)
    (RUNS / f"{name}.json").write_text(json.dumps(dict(
        src_mtime=_src_mtime(), built=pd.Timestamp.now().isoformat(timespec="seconds"),
        rows=len(P), dates=int(P["date" if "date" in P else "d0"].nunique()),
        tickers=int(P["ticker"].nunique())), ensure_ascii=False))


def describe(P: pd.DataFrame, date_col: str = "date") -> str:
    mb = P.memory_usage(deep=True).sum() / 2 ** 20
    return (f"{len(P):,}행 · 날짜 {P[date_col].nunique():,} ({P[date_col].min().date()}~{P[date_col].max().date()})"
            f" · 티커 {P['ticker'].nunique():,} · {P.shape[1]}열 · {mb:.0f}MB")


def main():
    t0 = time.time()
    raw = load_raw()
    print(f"[원자료] {DATA_DIR} · 가격 {raw.C.shape} · 실적 {len(raw.E):,}행 ({time.time() - t0:.1f}s)")
    t = time.time()
    daily_features(raw)
    print(f"[피처 행렬] {len(FEATURES)}개 ({time.time() - t:.1f}s)")
    for nm, fn, dc in (("월말 패널", monthly_panel, "date"), ("실적 이벤트", earnings_events, "d0"),
                       ("일간 패널", daily_panel, "date")):
        t = time.time()
        P = fn(raw, save=True)
        print(f"[{nm}] {describe(P, dc)} ({time.time() - t:.1f}s)")
        if nm == "월말 패널":
            lab = P["y_ex"].notna()
            print(f"  라벨 있는 행 {lab.sum():,} · 월평균 {P.groupby('date').size().mean():.0f}종목 · 피처 결측률 "
                  + ", ".join(f"{k} {P[k].isna().mean():.0%}" for k in ("mom_12_1", "sue_pct", "sue_persist")))
        del P
    print(f"[저장] {RUNS} · 총 {time.time() - t0:.1f}s")


if __name__ == "__main__":
    main()
