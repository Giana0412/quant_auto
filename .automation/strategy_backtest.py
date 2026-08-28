#!/usr/bin/env python3
"""그룹(지역·섹터·스타일 ETF) 로테이션 규칙의 과거 성적. gs-quant 로 계산한다.

── 왜 그룹 단위로만 백테스트하나 ──────────────────────────────────────────
market_metrics.py 의 [스크리닝]은 섹터·스타일 ETF의 **오늘 시점** 상위 보유종목을
유니버스로 쓴다 (screen_universe()). 과거로 돌아가 "그때의 상위 보유종목"을 구할
방법이 없으므로(생존편향 — 지금 잘나가는 종목일수록 상위 보유에 남아 있다),
개별종목 스크리닝 자체는 백테스트가 불가능하다.

대신 GROUPS(지역·섹터·스타일 13개 ETF)는 같은 티커가 수년간 유지돼 왔으므로,
"매달 위험조정 점수(변동성 대비 초과수익) 상위를 상관필터로 5개 골라 역변동성
가중으로 다음 한 달 보유한다"는 build_book() 의 **방법론 자체**는 이 13개로
재현할 수 있다 — 랭킹·사이징 방식이 market_metrics.main() 과 어긋나면 "같은
방법론을 검증한다"는 이 파일의 존재 이유가 깨지므로, 그쪽이 바뀌면 여기도
같이 바꾼다(§run() 의 info_score 사용 부분 참고).

즉 이 스크립트는 "오늘의 종목 후보가 맞았나"가 아니라 "이 로테이션 규칙이
지난 N개월 벤치마크를 이겼나"를 검증한다. 매일 돌릴 만큼 가볍지 않고 결과도
하루 단위로 바뀌지 않으므로 주간(strategy-backtest-weekly.sh)으로 돌리고,
market_metrics.py 가 결과 캐시(personal/10-market/_backtest/latest.json)를
읽어 매일 브리핑에 한 줄로 인용한다.

각 리밸런스 시점은 **그 시점까지의 데이터만** 써서 순위를 매기고, 다음 구간
동안 실제로 보유했다면 벌었을 수익으로 평가한다 (미래 데이터를 순위 산정에
쓰지 않는다 — look-ahead 방지).

실행:
  .automation/.venv/bin/python .automation/strategy_backtest.py
"""
import json
import sys
import warnings
from datetime import date
from pathlib import Path

warnings.filterwarnings("ignore")

import pandas as pd
import yfinance as yf
from gs_quant.timeseries import Window, max_drawdown

from market_metrics import BENCH, EXTRA, GROUPS, build_book, info_score, rel_vol  # 실제 운용 규칙을 그대로 재사용

CACHE_PATH = Path("personal/10-market/_backtest/latest.json")
REBAL_DAYS = 21    # 리밸런스 주기(영업일) — market_metrics 의 1개월 창과 맞춘다
LOOKBACK = 21       # 순위 산정에 쓰는 트레일링 초과수익 창
MAX_PERIODS = 12    # 최근 몇 회까지 볼지 (~1년)


def fetch_universe():
    tick = dict(EXTRA)
    for g in GROUPS.values():
        tick.update(g)
    out = {}
    for t, name in tick.items():
        try:
            h = yf.Ticker(t).history(period="2y", interval="1d")["Close"].dropna()
            if len(h) < REBAL_DAYS * 3:
                continue
            h.index = h.index.tz_localize(None)
            out[name] = h
        except Exception:
            continue
    if BENCH not in out:
        return None
    return pd.DataFrame(out).reindex(out[BENCH].index).ffill()


def run(df):
    bench_full = df[BENCH]
    # 🔴 EXTRA 에 있는 "VIX" 를 빼야 한다. fetch_universe() 가 dict(EXTRA) 로 시작해서
    # ACWI(BENCH)뿐 아니라 ^VIX 도 df 컬럼에 들어온다. VIX 는 지수와 역상관이라
    # build_book() 의 corr_cap 필터를 항상 통과하고, 실측에서 12회 중 6회 편입돼
    # 최대낙폭을 -3%p대에서 -13%p대로 부풀렸다 — "지역·섹터·스타일 ETF 로테이션"이라는
    # 이름과 다른 걸 검증하고 그 숫자를 [백테스트] 에 그대로 인용하는 셈이었다.
    universe = [c for c in df.columns if c not in (BENCH, "VIX")]
    n = len(bench_full)

    starts = list(range(LOOKBACK + REBAL_DAYS, n - REBAL_DAYS, REBAL_DAYS))
    starts = starts[-MAX_PERIODS:]

    period_rets = []
    for t in starts:
        hist = df.iloc[:t + 1]   # t 시점까지만 안다 — 이후 데이터는 순위에 안 쓴다
        b_hist = hist[BENCH].dropna()

        ranked = []
        for name in universe:
            s = hist[name].dropna()
            idx = s.index.intersection(b_hist.index)
            if len(idx) <= LOOKBACK + 5:
                continue
            s, bb = s[idx], b_hist[idx]
            e1 = (float(s.iloc[-1]) / float(s.iloc[-1 - LOOKBACK]) - 1) * 100
            e1 -= (float(bb.iloc[-1]) / float(bb.iloc[-1 - LOOKBACK]) - 1) * 100
            # market_metrics.main() 이 2026-08-28 부터 raw e1 대신 위험조정
            # 점수(info_score)로 줄 세우도록 바뀌었다 — "같은 방법론을 검증한다"는
            # 이 스크립트의 존재 이유(§ 파일 docstring)를 지키려면 여기도 같이
            # 바꿔야 한다. rel_vol 은 t 시점까지의 전체 이력(s 는 이미 idx 로
            # b_hist 와 맞춰져 있다)에서 최근 60거래일만 본다 — LOOKBACK(21) 보다
            # 긴 창이라 look-ahead 는 아니다(여전히 t 이후 데이터는 안 쓴다).
            rel = s.pct_change().dropna() - bb.pct_change().dropna()
            scr = info_score(e1, rel_vol(rel))
            ranked.append((scr, 0.0, float("nan"), name, ""))
        if not ranked:
            continue
        # scr 이 NaN(60거래일 이력이 아직 안 쌓인 초반 리밸런스 등)이면 맨 뒤로
        ranked.sort(key=lambda r: r[0] if not pd.isna(r[0]) else float("-inf"), reverse=True)

        weights, _ = build_book(hist[universe], b_hist, ranked, cap=0.20, corr_cap=0.75, n=5)
        if not weights:
            continue

        # 🔴 t 자체(진입일 종가)부터 포함해야 한다. fwd 가 t+1 부터 시작하면
        # pct_change() 의 첫 행(= t→t+1 수익률)이 "이전 행"을 못 찾아 NaN 이 되고,
        # 그걸 fillna(0) 으로 메우면 리밸런스 구간마다 첫날 수익률이 통째로 0으로
        # 빠진다 — 21거래일 중 20개만 세는 것과 같다(실측: 적중률·MDD 둘 다 바뀜).
        fwd = df.iloc[t: t + 1 + REBAL_DAYS]                # 실제 보유 구간(미래) — 평가에만 쓴다
        names = [nm for nm in weights if nm in fwd.columns]
        if len(fwd) < REBAL_DAYS // 2 + 1 or not names:
            continue
        rets = fwd[names].pct_change().dropna()
        bret = fwd[BENCH].pct_change().dropna()
        idx = rets.index.intersection(bret.index)
        if len(idx) == 0:
            continue
        rets, bret = rets.loc[idx], bret.loc[idx]
        w = pd.Series({nm: weights[nm] for nm in names})
        port = (rets[names] * w).sum(axis=1)
        excess = float((1 + port).prod() - (1 + bret).prod())  # 구간 누적 초과수익
        period_rets.append(excess * 100)

    return period_rets


def summarize(period_rets):
    if not period_rets:
        return None
    s = pd.Series(period_rets)
    periods, hits = len(s), int((s > 0).sum())
    cum = (1 + s / 100).cumprod()
    try:
        mdd = float(max_drawdown(cum, Window(len(cum), 0)).dropna().min()) * 100
    except Exception:
        mdd = float("nan")
    mean, std = float(s.mean()), float(s.std())
    # 회당 기준 — 12회 남짓으로 연율화하면 표본이 너무 작아 숫자가 왜곡된다
    ir = (mean / std) if std > 0 else float("nan")
    return dict(
        as_of=date.today().isoformat(),
        periods=periods,
        hits=hits,
        hit_rate=hits / periods * 100,
        avg_excess=mean,
        ir=ir,
        mdd=mdd,
        recent=[round(x, 2) for x in s.tail(3).tolist()],
    )


def main():
    df = fetch_universe()
    if df is None:
        print("벤치마크(ACWI) 를 못 받았다 — 백테스트 불가", file=sys.stderr)
        return 1
    result = summarize(run(df))
    if result is None:
        print("리밸런스 구간을 못 만들었다 (데이터 부족)", file=sys.stderr)
        return 1

    CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
    CACHE_PATH.write_text(json.dumps(result, ensure_ascii=False, indent=2))
    print(f"[전략백테스트] 지역·섹터·스타일 로테이션 {result['periods']}회 · "
          f"적중 {result['hits']}/{result['periods']}({result['hit_rate']:.0f}%) · "
          f"회당평균초과 {result['avg_excess']:+.2f}%p · 정보비율(회당) {result['ir']:+.2f} · "
          # 북 자체 절대수익 기준(market_metrics.book_stats 의 최대낙폭(절대))과 계산
          # 대상이 다르다 — 이건 리밸런스마다의 초과수익을 이어붙인 누적 곡선의 낙폭이다.
          f"최대낙폭(누적초과수익) {result['mdd']:+.1f}%p")
    print(f"최근 3회: {' / '.join(f'{x:+.2f}%p' for x in result['recent'])}")
    print(f"캐시 저장: {CACHE_PATH}")
    print("※ 개별종목 스크리닝(오늘 시점 ETF 보유종목)은 생존편향 때문에 과거 재현이 안 된다 — "
          "그룹 로테이션 규칙만 검증한 값이다. 과거 성적이지 미래 보장이 아니다.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
