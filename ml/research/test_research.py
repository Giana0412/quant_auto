"""연구 하네스 점검 — 미래 정보 차단, 퍼지, 심은 신호 검출, 위약(섞은 라벨), DSR.

실행 (ml/ 에서):  ../headline-sentiment/.venv/bin/python -m pytest research/test_research.py -q
실데이터 점검은 pead 캐시(QA_PEAD_RUNS)의 150종목 부분집합을 쓴다 — 캐시가 없으면 실패한다(건너뛰지 않는다).
"""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from research import baselines, cv, evaluate, panel, registry

T0 = pd.Timestamp("2021-06-15")       # 미래 차단 점검의 기준일 (세션 · 월 중간)


# ── 공용 ────────────────────────────────────────────────────────────────────

@pytest.fixture(scope="module")
def sub():
    """편입 이력이 긴 종목 150개 + SPY. 실데이터."""
    raw = panel.load_raw()
    M = panel.member_mask(raw)
    tick = M.sum().sort_values(ascending=False).index[:150].tolist()
    return tick


@pytest.fixture(scope="module")
def raw_full(sub):
    return panel.load_raw(tickers=sub)


def _same(a: np.ndarray, b: np.ndarray) -> bool:
    return np.allclose(a, b, rtol=1e-6, atol=1e-9, equal_nan=True)


def synth(n_dates=144, n_names=300, signal=0.1, seed=0) -> pd.DataFrame:
    """합성 월간 패널: y ~ N(0, 8%), f_sig = 상관 ≈ signal 인 신호, f0..f4 잡음."""
    rng = np.random.default_rng(seed)
    dates = pd.date_range("2008-01-31", periods=n_dates + 1, freq="ME")
    rows = []
    for k, d in enumerate(dates[:-1]):
        y = rng.normal(0, 0.08, n_names)
        sig = y / 0.08 * signal + rng.normal(0, np.sqrt(1 - signal ** 2), n_names)
        r = {"date": d, "ticker": [f"T{i:03d}" for i in range(n_names)], "y_ex": y, "label_end": dates[k + 1],
             "f_sig": sig}
        for i in range(5):
            r[f"f{i}"] = rng.normal(size=n_names)
        rows.append(pd.DataFrame(r))
    return pd.concat(rows, ignore_index=True)


# ── 1. 미래 정보 차단 ────────────────────────────────────────────────────────

def test_beta_excess_matches_overlay(raw_full):
    import overlay
    _, _, ex = panel.beta_excess(raw_full.C)
    assert _same(ex.to_numpy(), overlay.beta_excess(raw_full.C).to_numpy())


def test_features_unchanged_when_future_altered(sub, raw_full):
    """T0 뒤 가격·거래량·실적을 마구 바꿔도 T0 까지의 피처는 그대로여야 한다."""
    alt = panel.load_raw(tickers=sub)
    rng = np.random.default_rng(1)
    fut = alt.C.index > T0
    noise = np.exp(rng.normal(0, 0.05, (fut.sum(), alt.C.shape[1])))
    alt.C.loc[fut] = alt.C.loc[fut].to_numpy() * noise
    alt.V.loc[fut] = alt.V.loc[fut].to_numpy() * rng.uniform(0.2, 5, noise.shape)
    # 반응일이 T0 뒤인 발표 = 발표 시각이 T0 09:30 ET 이후. 장후(T0 16:00) 발표도 여기 든다 → d0 규칙 점검
    ts = pd.to_datetime(alt.E["ts"], utc=True).dt.tz_convert(panel._ov.ET)
    late = (ts > pd.Timestamp(T0.date()).tz_localize(panel._ov.ET) + pd.Timedelta(hours=9, minutes=30)).to_numpy()
    assert late.sum() > 100
    E = alt.E.copy()
    E.loc[late, "rep"] = E.loc[late, "est"] + rng.normal(0, 5, late.sum())
    alt.E = E
    Ff, Fa = panel.daily_features(raw_full), panel.daily_features(alt)
    upto = raw_full.C.index <= T0
    for k in panel.FEATURES:
        a, b = Ff[k].to_numpy()[upto], Fa[k].to_numpy()[upto]
        assert _same(a, b), f"{k}: T0 이전 값이 미래 변경에 반응했다"
        assert np.isfinite(a[-1]).any(), f"{k}: T0 에 값이 하나도 없다 (점검이 비었다)"
    # 미래는 실제로 바뀌었어야 한다 (점검이 헛돌지 않는지)
    assert not _same(Ff["mom_1m"].to_numpy()[~upto], Fa["mom_1m"].to_numpy()[~upto])
    assert not _same(Ff["sue_raw"].to_numpy()[~upto], Fa["sue_raw"].to_numpy()[~upto])
    # 월말 패널: 피처는 T0 이전 행 모두 같고, 라벨은 label_end ≤ T0 인 행만 같아야 한다
    Pf, Pa = panel.monthly_panel(raw_full), panel.monthly_panel(alt)
    assert (Pf[["date", "ticker"]].astype(str).to_numpy() == Pa[["date", "ticker"]].astype(str).to_numpy()).all()
    pre = (Pf["date"] <= T0).to_numpy()
    for k in panel.FEATURES:
        assert _same(Pf.loc[pre, k].to_numpy(), Pa.loc[pre, k].to_numpy()), k
    known = (Pf["label_end"] <= T0).to_numpy()
    assert _same(Pf.loc[known, "y_ex"].to_numpy(), Pa.loc[known, "y_ex"].to_numpy())
    assert not _same(Pf.loc[~known & pre, "y_ex"].to_numpy(), Pa.loc[~known & pre, "y_ex"].to_numpy())


def test_features_unchanged_when_future_truncated(sub, raw_full):
    """데이터를 T0 에서 잘라 다시 만들어도 T0 이전 피처가 같아야 한다 (전체 표본 통계·bfill 차단).
    T0 당일은 비교하지 않는다 — overlay.event_table 이 마지막 세션 반응일 발표를 빼는 규칙 때문."""
    cut = panel.load_raw(tickers=sub, end=T0)
    Ff, Fc = panel.daily_features(raw_full), panel.daily_features(cut)
    n = (cut.C.index < T0).sum()
    for k in panel.FEATURES:
        assert _same(Ff[k].to_numpy()[:n], Fc[k].to_numpy()[:n]), k


def test_sue_feature_timing(raw_full):
    """t 행의 sue_raw = 반응일 d0 ≤ t 인 가장 최근 발표의 SUE. 실적 이벤트 표의 pre_sue_raw 는 직전 발표."""
    D = panel._events(raw_full)
    F = panel.daily_features(raw_full, dtype="float64")
    g = D[D["ticker"] == D["ticker"].iloc[0]].sort_values("i0")
    j = int(g["j"].iloc[0])
    for _, r in g.iloc[1:6].iterrows():
        assert F["sue_raw"].iat[r["i0"], j] == pytest.approx(r["sue"])           # 반응일 당일부터 보인다
        prev = g[g["i0"] < r["i0"]]["sue"].iloc[-1]
        assert F["sue_raw"].iat[r["i0"] - 1, j] == pytest.approx(prev)           # 전날에는 직전 발표
    EV = panel.earnings_events(raw_full)
    e = EV[EV["ticker"].astype(str) == g["ticker"].iloc[0]].sort_values("d0")
    assert np.allclose(e["pre_sue_raw"].to_numpy()[1:], e["sue"].to_numpy()[:-1], equal_nan=True, rtol=1e-5)
    nxt = e["sue_next"].to_numpy()[:-1]
    ok = np.isfinite(nxt)
    assert np.allclose(nxt[ok], e["sue"].to_numpy()[1:][ok])


def test_monthly_label_definition(raw_full):
    P = panel.monthly_panel(raw_full)
    _, _, ex = panel.beta_excess(raw_full.C)
    r = P.dropna(subset=["y_ex"]).iloc[1234]
    s = ex.loc[(ex.index > r["date"]) & (ex.index <= r["label_end"]), r["ticker"]].sum()
    assert r["y_ex"] == pytest.approx(s, rel=1e-5)
    C = raw_full.C[r["ticker"]]
    assert r["y_raw"] == pytest.approx(C[r["label_end"]] / C[r["date"]] - 1, rel=1e-5)
    # 편입 중인 종목만
    M = panel.member_mask(raw_full)
    assert all(M.at[d, t] for d, t in zip(P["date"].iloc[::997], P["ticker"].astype(str).iloc[::997]))
    assert "SPY" not in set(P["ticker"].astype(str))


# ── 2. 퍼지 · 분할 ──────────────────────────────────────────────────────────

@pytest.mark.parametrize("embargo,horizon", [(0, 1), (40, 1), (0, 3)])
def test_purge(embargo, horizon):
    dates = pd.date_range("2010-01-31", "2020-12-31", freq="ME")
    d = np.repeat(dates, 5)
    le = np.repeat(dates.shift(horizon, freq="ME"), 5)
    folds = cv.walk_forward(d, le, first_test="2015-01-01", refit_months=12, val_months=12, embargo_days=embargo)
    assert len(folds) == 6
    emb = pd.Timedelta(days=embargo)
    for f in folds:
        t0 = f.test_start
        tr, va, te = (pd.DatetimeIndex(d[i]) for i in (f.train, f.val, f.test))
        ltr, lva = pd.DatetimeIndex(le[f.train]), pd.DatetimeIndex(le[f.val])
        assert te.min() == t0 and (tr < t0).all() and (va < t0).all()
        assert (ltr <= t0 - emb).all() and (lva <= t0 - emb).all(), "라벨 창이 시험 시작을 넘는 학습 행"
        assert tr.max() < va.min(), "검증은 안쪽 학습보다 뒤여야 한다"
        assert (ltr <= va.min() - emb).all(), "안쪽 학습 라벨이 검증 시작을 넘는다"
        assert not set(f.train) & set(f.val) and not set(f.fit) & set(f.test)
        # 퍼지가 '꼭 필요한 만큼만' 뺐는지: 시험·검증 경계 두 곳에서 라벨이 넘는 행만 빠진다
        tv = va.min()
        allowed = (d < t0) & (le <= t0 - emb) & ~((d < tv) & (le > tv - emb))
        assert set(np.flatnonzero(allowed)) == set(f.fit)
        if horizon > 1 or embargo:
            assert len(f.fit) < ((d < t0) & (le <= t0 - emb)).sum()           # 실제로 퍼지가 일어났다
    # 시험 블록이 빈틈없이 이어진다
    te_all = np.concatenate([f.test for f in folds])
    assert len(te_all) == len(set(te_all)) == ((d >= pd.Timestamp("2015-01-01"))).sum()


def test_purge_on_real_panel(raw_full):
    P = panel.monthly_panel(raw_full).dropna(subset=["y_ex"]).reset_index(drop=True)
    folds = cv.walk_forward(P["date"], P["label_end"], first_test="2019-01-01", val_months=24)
    for f in folds:
        assert P.loc[f.fit, "label_end"].max() <= f.test_start
        # 시험 직전 월말 행은 라벨 끝 = 시험 첫 월말 → 남는다. 그 전 달까지 모두 학습에 쓰인다.
        assert P.loc[f.fit, "date"].max() == P.loc[P["date"] < f.test_start, "date"].max()


# ── 3. 심은 신호 · 위약 ──────────────────────────────────────────────────────

def _run(P, cols, model, first="2013-01-01"):
    folds = cv.walk_forward(P["date"], P["label_end"], first_test=first, refit_months=12, val_months=12)
    return cv.predict_oos(P, folds, cols, "y_ex", model)


def test_planted_signal_detected():
    P = synth(signal=0.1)
    cols = ["f_sig"] + [f"f{i}" for i in range(5)]
    Rm = _run(P, cols, baselines.RidgeCV)
    Rb = _run(P, cols, lambda: baselines.OLS(cols=[1]))           # 잡음 피처 하나만 쓰는 기준
    s = evaluate.summarize(Rm)
    c = evaluate.compare(Rm, Rb)
    print(f"\n[심은 신호 corr 0.1] IC {s['ic_mean']:+.3f} (t {s['ic_t']:+.1f}) · R²(0) {s['r2_zero'] * 100:+.2f}%"
          f" · 롱숏 10bp 연 {s['ls_c10_ann'] * 100:+.1f}% t {s['ls_c10_t']:+.1f}"
          f" · 기준 대비 증분 10bp 연 {c['ls_c10_diff_ann'] * 100:+.1f}% t {c['ls_c10_diff_t']:+.1f}"
          f" · DM {c['dm_stat']:+.2f}")
    assert s["ic_mean"] > 0.05 and s["ic_t"] > 5
    assert s["ls_c10_ann"] > 0 and s["ls_c10_t"] > 3
    assert c["ls_c10_diff_ann"] > 0 and c["ls_c10_diff_t"] > 3
    assert c["ic_diff_t"] > 3 and c["dm_stat"] < 0
    assert s["r2_zero"] > 0


def test_shuffled_labels_give_zero_ic():
    """신호와 라벨의 짝을 날짜 안에서 섞으면 IC·롱숏이 0 근처여야 한다 (위약 10회)."""
    ts, ls = [], []
    cols = ["f_sig"] + [f"f{i}" for i in range(5)]
    for seed in range(10):
        P = synth(signal=0.1, seed=seed, n_dates=96, n_names=200)
        rng = np.random.default_rng(100 + seed)
        P["y_ex"] = P.groupby("date")["y_ex"].transform(lambda x: rng.permutation(x.to_numpy()))
        s = evaluate.summarize(_run(P, cols, baselines.RidgeCV, first="2012-01-01"))
        ts.append(s["ic_t"])
        ls.append(s["ls_c0_t"])
    ts, ls = np.array(ts), np.array(ls)
    print(f"\n[위약 10회] IC NW t 평균 {ts.mean():+.2f}, |t|>2 {int((abs(ts) > 2).sum())}회 · 롱숏 t 평균 {ls.mean():+.2f}")
    assert abs(ts.mean()) < 1.0 and (abs(ts) > 2.5).sum() <= 2
    assert abs(ls.mean()) < 1.0


def test_shuffled_labels_real_panel(raw_full):
    """실데이터: 12-1 모멘텀 순위 대 날짜 안에서 섞은 라벨 → IC t ≈ 0."""
    P = panel.monthly_panel(raw_full).dropna(subset=["y_ex", "mom_12_1"])
    rng = np.random.default_rng(7)
    R = P[["date", "ticker"]].assign(pred=P["mom_12_1"].to_numpy(),
                                     y=P.groupby("date")["y_ex"].transform(lambda x: rng.permutation(x.to_numpy())))
    s = evaluate.ic_summary(evaluate.rank_ic(R))
    assert abs(s["ic_t"]) < 3 and abs(s["ic_mean"]) < 0.02


# ── 4. 평가 도구 ─────────────────────────────────────────────────────────────

def test_nw_and_dm():
    rng = np.random.default_rng(3)
    x = rng.normal(0.1, 1, 500)
    import overlay
    assert evaluate.nw_t(x) == overlay.nw_t(x)
    a = rng.normal(1, 1, 300) ** 2
    assert np.isnan(evaluate.diebold_mariano(a, a)["stat"])
    b = a + rng.normal(0.5, 0.3, 300)
    dm = evaluate.diebold_mariano(a, b)
    assert dm["stat"] < -5 and dm["p"] < 1e-6
    # QLIKE 는 참 분산을 예측할 때 기대 손실이 가장 작다
    v = rng.uniform(0.5, 2, 5000)
    rv = v * rng.chisquare(5, 5000) / 5
    assert evaluate.loss_qlike(rv, v).mean() < evaluate.loss_qlike(rv, v * 1.3).mean()
    assert evaluate.loss_qlike(rv, v).mean() < evaluate.loss_qlike(rv, v * 0.7).mean()


def test_portfolio_turnover_and_costs():
    P = synth(n_dates=12, n_names=100)
    R = P.rename(columns={"y_ex": "y"}).assign(pred=lambda d: d["ticker"].str[1:].astype(int))   # 늘 같은 순위
    pf = evaluate.portfolios(R)
    assert pf["to_top"].iloc[0] == pytest.approx(1.0) and pf["to_ls"].iloc[0] == pytest.approx(2.0)
    assert np.allclose(pf["to_ls"].iloc[1:], 0)
    assert np.allclose(pf["ls_net25"].iloc[1:], pf["ls"].iloc[1:])
    assert pf["ls_net10"].iloc[0] == pytest.approx(pf["ls"].iloc[0] - 10 / 1e4 * 2)
    top = R[R["pred"] >= 90].groupby("date")["y"].mean()
    assert np.allclose(pf["top"], top)


def test_rank_normalize_and_fill():
    P = pd.DataFrame({"date": np.repeat(pd.to_datetime(["2020-01-31", "2020-02-29"]), 5),
                      "a": [5, 1, np.nan, 3, 3, 10, 20, 30, 40, 50.]})
    Q, cols = panel.prepare(P, ["a"])
    assert cols == ["a", "a_na"]
    q = Q["a"].to_numpy()
    assert q[1] == -1 and q[0] == 1 and q[3] == q[4] == pytest.approx(0.0) and q[2] == pytest.approx(0.0)
    assert np.allclose(q[5:], [-1, -0.5, 0, 0.5, 1])
    assert Q["a_na"].tolist() == [0, 0, 1, 0, 0, 0, 0, 0, 0, 0]


def test_oos_r2_and_hist_mean():
    y = np.array([0.1, -0.1, 0.2])
    assert evaluate.oos_r2(y, np.zeros(3)) == 0
    assert evaluate.oos_r2(y, y) == 1
    P = pd.DataFrame({"date": pd.to_datetime(["2020-01-31", "2020-02-29", "2020-03-31"]),
                      "label_end": pd.to_datetime(["2020-02-29", "2020-03-31", "2020-04-30"]), "y": [1.0, 2.0, 3.0]})
    h = evaluate.hist_mean(P, "y", P["date"])
    assert np.isnan(h.iloc[0]) and h.iloc[1] == 1.0 and h.iloc[2] == 1.5   # 2/29 에는 첫 라벨만 확정


# ── 5. 다중검정 · DSR · 장부 ──────────────────────────────────────────────────

def test_holm_bh():
    p = [0.01, 0.04, 0.03, 0.005]
    assert np.allclose(registry.holm(p), [0.03, 0.06, 0.06, 0.02])
    assert np.allclose(registry.bh(p), [0.02, 0.04, 0.04, 0.02])


def test_dsr_sanity():
    assert registry.expected_max_sr(1, 0.01) == 0
    # 몬테카를로: SR=0 인 전략 N 개의 최대 SR 평균 ≈ SR0
    rng = np.random.default_rng(5)
    N, T = 50, 250
    mx = [(lambda X: (X.mean(0) / X.std(0, ddof=1)).max())(rng.normal(size=(T, N))) for _ in range(400)]
    sr0 = registry.expected_max_sr(N, 1 / T)
    print(f"\n[DSR] N={N} 최대 SR 몬테카를로 {np.mean(mx):.4f} vs 공식 {sr0:.4f}")
    assert abs(np.mean(mx) - sr0) / sr0 < 0.1
    # SR = SR0 이면 DSR ≈ 0.5 ; 시도가 늘면 DSR 은 줄어든다
    assert registry.deflated_sharpe(sr0, T, N, 1 / T)["dsr"] == pytest.approx(0.5, abs=1e-9)
    d = [registry.deflated_sharpe(0.15, 120, n, 0.01)["dsr"] for n in (1, 10, 100, 1000)]
    assert d[0] > 0.9 and all(a > b for a, b in zip(d, d[1:]))
    # 우연의 최대값은 디플레이트되면 유의하지 않아야 한다
    assert registry.deflated_sharpe(np.mean(mx), T, N, 1 / T)["dsr"] < 0.8


def test_ledger_roundtrip(tmp_path):
    f = tmp_path / "ledger.jsonl"
    rng = np.random.default_rng(0)
    for i in range(5):
        x = pd.Series(rng.normal(0.002 * i, 0.03, 120))
        m = {f"ls_c10_{k}": v for k, v in evaluate.series_stats(x, 12).items()}
        registry.log("t", f"cfg{i}", {"i": i, "d": pd.Timestamp("2020-01-01")}, m, path=f)
    L = registry.load("t", path=f)
    assert len(L) == registry.n_trials("t", path=f) == 5 and L["params"].iloc[0]["i"] == 0
    L = registry.deflate(registry.adjust(L), "ls_c10")
    assert {"ls_c10_p_holm", "ls_c10_p_bh", "ls_c10_dsr", "ls_c10_sr0"} <= set(L.columns)
    assert (L["ls_c10_p_holm"] >= L["ls_c10_p"] - 1e-12).all() and L["ls_c10_sr0"].iloc[0] > 0
