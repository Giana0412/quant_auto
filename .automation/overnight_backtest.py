#!/usr/bin/env python3
"""오버나이트(종가 매수 → 다음 시가 매도) 전략 백테스트.

── 왜 ────────────────────────────────────────────────────────────────────
2026-09-17 교수 A(HKUST Finance) 자문에서 **유일하게 구체적으로 제시된 알파**다:

    "진짜 잘되는 건, 숏이 안 돼서 문제긴 한데, 오버나이트에 투자하고 장중에 안 갖고
     있는 거예요. 이건 생각보다 잘 돼요. 되게 컨시스턴트하게 한국·미국·유럽에서 다
     발생하는 현상이에요. (…) 원래 안 되는 이유는 슬리피지가 있어서 어려운 건데,
     **여기서는 전혀 상관없으니까 오히려 해볼 수도 있을 것 같아요.**"

즉 **"대회가 체결 비용을 안 물린다면 성립한다"** 는 조건부 주장이다. 그래서 이
스크립트의 핵심 출력은 수익률이 아니라 **§손익분기 비용** 이다 — 왕복 비용이
얼마를 넘으면 이 전략이 죽는지. 9/23 블룸버그 행사에서 체결 방식을 확인하면
그 숫자와 대조해 쓸지 말지를 바로 정할 수 있다.

── 계산 ──────────────────────────────────────────────────────────────────
  오버나이트 = 시가[t] / 종가[t-1] − 1      (종가에 사서 다음 시가에 판다)
  인트라데이 = 종가[t] / 시가[t] − 1        (시가에 사서 종가에 판다)
  바이앤홀드 = 오버나이트와 인트라데이를 곱한 것 = 그냥 들고 있기

auto_adjust=True 로 받는다 — 분할이 있으면 시가/종가가 서로 다른 기준이 돼
오버나이트 수익이 통째로 왜곡된다(실측 확인: 대상 종목엔 분할이 없어 두 설정이
같았지만, 유니버스를 바꾸면 언제든 걸릴 수 있다).

🔴 **대회 평가는 상대수익**이라 벤치마크 대비도 같이 낸다. 오버나이트가 절대로
플러스여도 벤치를 못 이기면 대회에선 의미가 없다.

실행:
  .automation/.venv/bin/python .automation/overnight_backtest.py            # 기본 기술주
  .automation/.venv/bin/python .automation/overnight_backtest.py SWKS QRVO  # 종목 지정
  .automation/.venv/bin/python .automation/overnight_backtest.py --years 1
"""
import sys
import warnings

warnings.filterwarnings("ignore")

import numpy as np
import pandas as pd
import yfinance as yf

# 1차 미팅에서 정한 기술 섹터 관심군 — 반도체 서플라이어 · 소프트웨어 · 보안 ·
# 데이터센터. 비교용으로 빅테크와 지수 프록시도 넣는다.
DEFAULT = ["SWKS", "QRVO", "MU", "AMD", "LRCX", "AMAT", "KLAC", "TER",
           "PANW", "CRWD", "FTNT", "ZS", "OKTA", "NET",
           "SMCI", "VRT", "NVDA", "AAPL", "MSFT", "META"]
BENCH = "ACWI"           # 대회 벤치마크(WLS) 대용 — market_metrics 와 같은 기준
TRADING_DAYS = 252


def decompose(op, cl):
    """(오버나이트, 인트라데이) 일간 수익률. 인덱스를 맞춰 돌려준다."""
    i = op.index.intersection(cl.index)
    o, c = op[i].dropna(), cl[i].dropna()
    j = o.index.intersection(c.index)
    o, c = o[j], c[j]
    on = (o / c.shift(1) - 1).dropna()
    intra = (c / o - 1).dropna()
    k = on.index.intersection(intra.index)
    return on[k], intra[k]


def cum(r):
    return ((1 + r).prod() - 1) * 100


def breakeven_cost(on):
    """왕복 체결비용이 몇 bp 를 넘으면 오버나이트 전략이 0 이 되는가.
    매일 사고파는 전략이라 거래일마다 비용이 한 번씩 붙는다 —
    **하루 평균 수익이 곧 하루치 비용 한도**다."""
    return float(on.mean()) * 10000      # bp


def main():
    args = [a for a in sys.argv[1:] if not a.startswith("-")]
    years = 2
    if "--years" in sys.argv:
        try:
            years = int(sys.argv[sys.argv.index("--years") + 1])
        except Exception:
            pass
    syms = [a.upper() for a in args] or DEFAULT

    raw = yf.download(syms + [BENCH], period=f"{years}y", interval="1d",
                      progress=False, auto_adjust=True)
    op, cl = raw["Open"], raw["Close"]
    if BENCH not in cl.columns:
        print("벤치마크를 못 받았다", file=sys.stderr)
        return 1
    b_on, b_intra = decompose(op[BENCH], cl[BENCH])
    b_total = cum(b_on) + cum(b_intra)   # 표시용 근사

    print(f"\n[오버나이트 백테스트] 최근 {years}년 · {len(syms)}종목 · 벤치 {BENCH}")
    print("  오버나이트 = 종가 매수 → 다음 시가 매도 / 인트라데이 = 시가 매수 → 종가 매도")
    print(f"\n  {'':7}{'오버나이트':>11}{'인트라데이':>11}{'바이앤홀드':>11}"
          f"{'승률':>7}{'일평균':>8}{'손익분기':>9}")
    print(f"  {'':7}{'(누적)':>11}{'(누적)':>11}{'(누적)':>11}{'(오버)':>7}{'(bp)':>8}{'(왕복bp)':>9}")

    rows = []
    for s in syms:
        if s not in cl.columns:
            continue
        on, intra = decompose(op[s], cl[s])
        if len(on) < 100:
            continue
        c_on, c_id = cum(on), cum(intra)
        c_bh = ((1 + on).prod() * (1 + intra).prod() - 1) * 100
        win = (on > 0).mean() * 100
        daily_bp = float(on.mean()) * 10000
        be = breakeven_cost(on)
        rows.append(dict(sym=s, on=c_on, intra=c_id, bh=c_bh, win=win,
                         daily_bp=daily_bp, be=be, n=len(on), series=on))
        mark = " ←" if c_on > c_id else ""
        print(f"  {s:7}{c_on:>+10.1f}%{c_id:>+10.1f}%{c_bh:>+10.1f}%"
              f"{win:>6.0f}%{daily_bp:>7.1f}{be:>8.1f}{mark}")

    if not rows:
        print("  계산된 종목이 없다")
        return 1

    d = pd.DataFrame([{k: v for k, v in r.items() if k != "series"} for r in rows])
    n_win = int((d.on > d.intra).sum())
    print(f"\n  {'평균':7}{d.on.mean():>+10.1f}%{d.intra.mean():>+10.1f}%"
          f"{d.bh.mean():>+10.1f}%{d.win.mean():>6.0f}%{d.daily_bp.mean():>7.1f}"
          f"{d.be.mean():>8.1f}")
    print(f"  → {len(d)}종목 중 **{n_win}개**가 오버나이트 우세")
    print(f"  → 벤치({BENCH}) 오버나이트 {cum(b_on):+.1f}% · 인트라데이 {cum(b_intra):+.1f}%")

    # ── 동일가중 바스켓 ────────────────────────────────────────────────
    basket = pd.concat([r["series"] for r in rows], axis=1).mean(axis=1).dropna()
    bi = basket.index.intersection(b_on.index)
    excess = basket[bi] - b_on[bi]
    ann = float(basket.mean()) * TRADING_DAYS * 100
    vol = float(basket.std()) * (TRADING_DAYS ** 0.5) * 100
    t_stat = float(basket.mean()) / (float(basket.std()) / np.sqrt(len(basket)))

    print(f"\n[동일가중 바스켓] {len(rows)}종목을 매일 같은 비중으로")
    print(f"  누적 {cum(basket):+.1f}% · 연율 {ann:+.1f}% · 연율변동성 {vol:.1f}%")
    print(f"  거래일 {len(basket)}일 · 승률 {(basket > 0).mean() * 100:.0f}% · t값 {t_stat:.2f}")
    print(f"  벤치 오버나이트 대비 초과 {cum(excess):+.1f}%p")

    # ── 🔴 핵심: 비용 민감도 ───────────────────────────────────────────
    print(f"\n[🔴 체결비용 민감도] 매일 사고팔므로 {len(basket)}번 왕복한다")
    print("  왕복비용(bp)   바스켓 누적수익")
    for bp in (0, 1, 2, 3, 5, 10):
        net = basket - bp / 10000
        print(f"  {bp:>8}bp    {cum(net):>+10.1f}%"
              + ("   ← 손익분기" if bp and cum(net) < 0 <= cum(basket) else ""))
    be_basket = float(basket.mean()) * 10000
    print(f"\n  → 바스켓 손익분기 왕복비용 = **{be_basket:.1f}bp**")
    print(f"     왕복 {be_basket:.1f}bp 를 넘으면 이 전략은 마이너스가 된다.")
    print("     현실의 중소형주 스프레드는 왕복 10~30bp 가 흔해 실제로는 대부분 먹힌다 —")
    print("     교수님이 \"슬리피지 때문에 원래 안 된다\"고 한 게 이 뜻이다.")
    print("  🔴 9/23 행사에서 **체결가 기준과 비용 차감 여부**를 반드시 확인할 것.")
    print("     차감 안 하면 성립하고, 차감하면 위 표에서 해당 bp 줄을 보면 된다.")

    print("\n  ※ 과거 실적이지 미래 보장이 아니다. 표본은 종목당 "
          f"{int(d.n.mean())}거래일이고, 이 현상이 앞으로도 유지된다는 근거는 없다.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
