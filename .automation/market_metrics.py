#!/usr/bin/env python3
"""매매대회 전략 세팅용 시장 지표. gs-quant 로 계산한다.

── 왜 이 설계인가 ────────────────────────────────────────────────────────
Bloomberg Global Trading Challenge 규칙을 확인하고 맞췄다:
  - 유니버스는 **전 세계 주식** (FX·선물이 아니다)
  - 가상 $1M, 한 포지션이 명목의 20% 초과 불가
  - 🔴 평가가 **벤치마크 대비 시간가중 상대수익률** (Bloomberg WLS Index)

즉 **절대수익이 아니라 초과수익(알파)으로 이긴다.** 그래서 지수·환율·금 시세를
찍는 건 의미가 거의 없고, **"무엇을 사면 벤치마크를 이기나"** 를 봐야 한다.
→ 지역·섹터·스타일 로테이션. 전부 ACWI 대비 상대값으로 낸다.

WLS(대형+중형+소형 글로벌)에 가장 가까운 거래 가능 프록시가 ACWI 라 기준으로 썼다.
WLS 는 소형주를 포함하므로 소형주(IWM) 를 따로 본다.

실행:
  .automation/.venv/bin/python .automation/market_metrics.py
  .automation/.venv/bin/python .automation/market_metrics.py META 005930.KS   # 종목 추가

인자로 티커를 주면 [종목] 절에 벤치마크 대비 성과를 같이 낸다. 종목 고르는
대회라 뉴스에 나온 이름이 곧 아이디어 후보이므로, 그것들이 실제로 벤치마크를
이기고 있는지 바로 보이게 하려는 것이다.
"""
import sys
import warnings

warnings.filterwarnings("ignore")

import pandas as pd
import yfinance as yf
from gs_quant.timeseries import Window, beta, correlation, returns, volatility, zscores

BENCH = "벤치마크"

GROUPS = {
    "지역": {"SPY": "미국", "EFA": "선진ex미", "EEM": "신흥", "EWY": "한국", "EWJ": "일본"},
    "섹터": {"XLK": "기술", "XLF": "금융", "XLE": "에너지", "XLV": "헬스케어", "XLI": "산업재"},
    "스타일": {"IWF": "성장", "IWD": "가치", "IWM": "미국소형"},
}
EXTRA = {"ACWI": BENCH, "^VIX": "VIX"}

Z_STRETCH = 1.5
LOOKBACKS = (21, 63)   # 1개월, 3개월 (영업일)


def fetch(extra_tickers=()):
    tick = dict(EXTRA)
    for g in GROUPS.values():
        tick.update(g)
    # 인자로 받은 종목은 티커를 그대로 이름으로 쓴다 (한글 라벨이 없으므로)
    for t in extra_tickers:
        tick.setdefault(t, t)
    out, failed = {}, []
    for t, name in tick.items():
        try:
            h = yf.Ticker(t).history(period="1y", interval="1d")["Close"].dropna()
            if len(h) < 80:
                failed.append(f"{name}({len(h)}일)")
                continue
            h.index = h.index.tz_localize(None)
            out[name] = h
        except Exception as e:
            failed.append(f"{name}({str(e)[:20]})")
    if BENCH not in out:
        return pd.DataFrame(out), failed

    # 🔴 **벤치마크 거래일로 달력을 고정한다.**
    # pd.DataFrame 은 모든 티커 날짜의 합집합으로 인덱스를 만든다. 한국 종목
    # (005930.KS 등)을 인자로 넣으면 한국 거래일이 섞여 행 수가 늘어나고,
    # excess() 가 쓰는 iloc[-1-21] 이 세는 21칸이 **실제로는 다른 날짜**가 된다.
    # 실측: 같은 시점에 한국 1개월 초과수익이 종목 없이 -1.6%, 종목을 넣으면 +5.2%.
    # 어떤 종목을 조회하느냐에 따라 지역·섹터 숫자가 바뀌면 안 되므로 ACWI 달력에 맞춘다.
    return pd.DataFrame(out).reindex(out[BENCH].index).ffill(), failed


def excess(s, b, n):
    """n영업일 누적 초과수익(%p). 대회 평가가 상대수익률이므로 이게 본체다."""
    if len(s) <= n or len(b) <= n:
        return None
    a = (float(s.iloc[-1]) / float(s.iloc[-1 - n]) - 1) * 100
    m = (float(b.iloc[-1]) / float(b.iloc[-1 - n]) - 1) * 100
    return a - m


def main():
    extras = [a for a in sys.argv[1:] if not a.startswith("-")]
    df, failed = fetch(extras)
    if BENCH not in df.columns:
        print("벤치마크(ACWI) 를 못 받았다 — 상대값 계산 불가", file=sys.stderr)
        return 1

    b = df[BENCH].dropna()
    br = returns(b).dropna()

    # ── 레짐 ────────────────────────────────────────────────────────────
    print("[레짐]")
    bvol = volatility(b, 30).dropna()
    ma50 = b.rolling(50).mean()
    print(f"벤치마크 {float(b.iloc[-1]):.2f} · 30일변동성 {float(bvol.iloc[-1]):.1f}% · "
          f"50MA {'위' if float(b.iloc[-1]) > float(ma50.iloc[-1]) else '아래'}")
    if "VIX" in df.columns:
        v = df["VIX"].dropna()
        d5 = (float(v.iloc[-1]) / float(v.iloc[-6]) - 1) * 100 if len(v) > 6 else 0
        print(f"VIX {float(v.iloc[-1]):.1f} (5일 {d5:+.0f}%)")

    # ── 그룹별 초과수익 순위 ─────────────────────────────────────────────
    stretched = []
    for gname, members in GROUPS.items():
        rows = []
        for _, name in members.items():
            if name not in df.columns:
                continue
            s = df[name].dropna()
            e1, e3 = excess(s, b, LOOKBACKS[0]), excess(s, b, LOOKBACKS[1])
            if e1 is None or e3 is None:
                continue
            # 벤치마크 대비 상대수익률의 z — 과열/과매도 판정
            idx = s.index.intersection(b.index)
            rel = returns(s[idx]).dropna() - returns(b[idx]).dropna()
            z = zscores(rel.dropna(), 60).dropna()
            zz = float(z.iloc[-1]) if len(z) else 0.0
            try:
                bt = float(beta(s[idx], b[idx], Window(63, 0)).dropna().iloc[-1])
            except Exception:
                bt = float("nan")
            rows.append((e1, e3, zz, bt, name))
            if abs(zz) >= Z_STRETCH:
                stretched.append((zz, name))

        rows.sort(reverse=True)
        print(f"\n[{gname}] 벤치마크 대비 초과수익")
        print(f"  {'':10}{'1개월':>9}{'3개월':>9}{'z':>7}{'베타':>7}   추세")
        for e1, e3, zz, bt, name in rows:
            # 3개월보다 1개월이 좋으면 가속, 나쁘면 둔화
            trend = "가속 ↑" if e1 > e3 / 3 else ("둔화 ↓" if e1 < 0 < e3 else "")
            print(f"  {name:10}{e1:>+8.1f}%{e3:>+8.1f}%{zz:>+7.1f}{bt:>7.2f}   {trend}")

    # ── 뉴스에서 넘어온 개별 종목 ────────────────────────────────────────
    if extras:
        print("\n[종목] 벤치마크 대비 초과수익")
        print(f"  {'':12}{'1개월':>9}{'3개월':>9}{'z':>7}{'베타':>7}")
        srows = []
        for name in extras:
            if name not in df.columns:
                continue
            s = df[name].dropna()
            e1, e3 = excess(s, b, LOOKBACKS[0]), excess(s, b, LOOKBACKS[1])
            if e1 is None or e3 is None:
                continue
            idx = s.index.intersection(b.index)
            rel = (returns(s[idx]).dropna() - returns(b[idx]).dropna()).dropna()
            z = zscores(rel, 60).dropna()
            zz = float(z.iloc[-1]) if len(z) else 0.0
            try:
                bt = float(beta(s[idx], b[idx], Window(63, 0)).dropna().iloc[-1])
            except Exception:
                bt = float("nan")
            srows.append((e1, e3, zz, bt, name))
            if abs(zz) >= Z_STRETCH:
                stretched.append((zz, name))
        for e1, e3, zz, bt, name in sorted(srows, reverse=True):
            print(f"  {name:12}{e1:>+8.1f}%{e3:>+8.1f}%{zz:>+7.1f}{bt:>7.2f}")
        if not srows:
            print("  (조회된 종목 없음)")

    # ── 과열·과매도 ─────────────────────────────────────────────────────
    print("\n[스트레치]")
    if stretched:
        stretched.sort()
        print("  " + " · ".join(f"{n} {z:+.1f}σ" for z, n in stretched))
    else:
        print(f"  없음 (|z|>={Z_STRETCH})")

    # ── 분산: 같이 움직이면 20% 제한을 지켜도 실질 집중이다 ────────────────
    print("\n[상관 60일]")
    pairs = (("기술", "성장"), ("한국", "신흥"), ("에너지", "금융"), ("미국소형", "미국"))
    for a, c in pairs:
        if a in df.columns and c in df.columns:
            x, y = df[a].dropna(), df[c].dropna()
            i = x.index.intersection(y.index)
            if len(i) < 70:
                continue
            # 🔴 correlation 은 **가격**을 받는다 (내부에서 수익률로 변환).
            # 수익률을 넣으면 수익률의 수익률을 계산해 값이 절반 이하로 나온다 —
            # 실측: XLK↔IWF 가 수익률 입력 +0.22, 가격 입력 +0.86 (pandas 정답 +0.861).
            cor = correlation(x[i], y[i], Window(60, 0)).dropna()
            if len(cor):
                cv = float(cor.iloc[-1])
                tag = "높음 — 분산 안 됨" if cv >= 0.8 else ("보통" if cv >= 0.5 else "낮음")
                print(f"  {a}↔{c} {cv:+.2f} ({tag})")

    if failed:
        print(f"\n[조회실패] {', '.join(failed)}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
