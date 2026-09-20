#!/usr/bin/env python3
"""공격형 스크리너 — 7주 안에 크게 움직일 종목을 찾는다.

── 왜 만들었나 ───────────────────────────────────────────────────────────
market_metrics.py 의 [스크리닝]은 **초과수익 ÷ 변동성**으로 줄 세운다. 즉 조용히
꾸준히 이긴 종목을 좋아하고 널뛰는 종목에 벌점을 준다. 고객 돈을 굴리는 관점에선
맞지만, **이 대회의 보상 구조와는 반대 방향**이다.

2026-09-17 교수 A(HKUST Finance) 자문에서 이 점이 정면으로 지적됐다:

    "학생 입장에서는 콜옵션이잖아요. 내 포트폴리오가 망하면 아무 상관없고, 아주
     잘되면 좋고, 적당히 잘되면 딱히 도움되는 게 없고요. 콜옵션 모양의 페이오프이기
     때문에 볼라틸리티를 맥시마이즈하는 게 제일 좋아요."

    "너무 다이버시파이되면 어차피 인덱스 무브랑 비슷해질 것 같아서요."
    "진짜 컨센트레이티드 베팅을 하고 싶으면 20개 이내에서 하는 게 좋고요."

그래서 기존 스크리너를 **바꾸지 않고** 두 번째를 만든다 — 이것도 교수 조언이다:

    김규형: "이 파이프라인은 변동성을 안 좋은 신호로 보고 배제하거든요.
             그러면 이걸 아예 바꾸는 게 나을까요?"
    교수 A: "그걸 버리지 말고 두세 가지를 추가로 구축하면 되지 않을까요?
             아예 밈 스탁을 골라내는 걸 만들어 보기도 하고요. 과거 일주일 새에
             볼륨이 폭발하고 급등해서 사람들이 몰리는 주식을 본다거나."

두 스크리너를 나란히 놓고 "오늘은 어느 쪽 게임을 할지"를 사람이 고른다.

── 🔴 이걸 만든 교수님이 동시에 경고한 것 ────────────────────────────────
    "원래 그런 주식은 절대 사면 안 되는데 (…) 그런 주식은 이미 오버밸류돼 있기
     때문에 그런 주식만 100개 모아놓으면 **평균적으로 하락세를 보여요.** 다 흥분해서
     달려든 주식들이니까요. 그래서 사라고까지는 못 하겠는데."

즉 이 스크리너의 상위 종목은 **기대수익이 플러스라서** 뽑힌 게 아니라 **분산이
커서** 뽑힌 것이다. 토너먼트에서 꼬리를 사는 것이지 좋은 투자가 아니다.
출력에 이 경고를 매번 박아 둔다 — 안 그러면 몇 주 뒤에 이걸 "추천 종목"으로 읽게 된다.

── 점수 구성 ─────────────────────────────────────────────────────────────
네 가지를 **순위 백분위**로 바꿔 가중합한다(단위가 제각각이라 생값을 더할 수 없다):
  · 모멘텀   — 벤치 대비 1개월 초과수익 (변동성으로 **나누지 않는다**)
  · 거래량   — 최근 5일 평균 거래량 ÷ 과거 60일 평균 (사람이 몰리는 중인가)
  · 변동성   — 21일 고저폭 (여기선 **가점**이다)
  · 신고가   — 현재가 ÷ 52주 최고가 (추세의 끝자락에 있나)

⚠️ **가중치는 근거가 없다.** VOL_PENALTY 와 같은 문제다 — 표본이 없어 학습할 수
없고, 백테스트는 생존편향 때문에 애초에 불가능하다(§market_metrics 유니버스 주석).
숫자를 바꿔가며 "좋아 보이는" 걸 고르면 그게 바로 과적합이다. 지금 값은
"넷을 비슷하게 보되 모멘텀과 거래량을 조금 더"라는 판단일 뿐이다.

실행:
  .automation/.venv/bin/python .automation/momentum_screen.py
  .automation/.venv/bin/python .automation/momentum_screen.py --top 15
"""
import sys
import warnings

warnings.filterwarnings("ignore")

import pandas as pd
import yfinance as yf

from market_metrics import (
    BENCH, LOOKBACKS, RSI_HOT, excess, fetch, momentum, screen_universe, span21,
)

# 점수 가중치 — 합 1.0. 위 docstring 의 경고를 읽고 만질 것.
W_MOMENTUM = 0.35     # 이미 오르고 있나
W_VOLUME = 0.30       # 사람이 몰리는 중인가
W_VOLATILITY = 0.20   # 얼마나 크게 움직이나 (가점)
W_HIGH = 0.15         # 신고가에 붙어 있나

VOL_SURGE_DAYS = 5        # 최근 거래량을 보는 창
VOL_BASE_DAYS = 60        # 비교 기준이 되는 평소 거래량 창
MIN_SURGE = 1.5           # 이만큼은 거래량이 터져야 후보로 본다
MIN_SPAN_AGGR = 12.0      # 21일 고저폭 하한 — 수비형(5%)보다 훨씬 높게
MIN_PRICE = 3.0           # 동전주 제외. 슬리피지가 현실에선 수익을 다 먹는다
BOOK_N_AGGR = 4           # 집중 베팅 (교수: "20개 이내", 실제론 더 적게)
CAP_AGGR = 0.20           # 대회 규정 상한은 그대로 지킨다


def volume_surge(vol):
    """최근 거래량이 평소의 몇 배인가. 1.0이면 평소 수준."""
    v = vol.dropna()
    if len(v) < VOL_BASE_DAYS:
        return float("nan")
    recent = float(v.tail(VOL_SURGE_DAYS).mean())
    base = float(v.tail(VOL_BASE_DAYS).mean())
    return recent / base if base > 0 else float("nan")


def high_proximity(close):
    """52주 최고가 대비 현재가 위치. 1.0이면 신고가."""
    c = close.dropna()
    if len(c) < 200:
        return float("nan")
    hi = float(c.tail(252).max())
    return float(c.iloc[-1]) / hi if hi > 0 else float("nan")


def build_rows(bench, src, px, vol):
    """종목별 원자료. 점수는 아직 안 매긴다(백분위는 전체를 봐야 하므로)."""
    rows = []
    for s in px.columns:
        ser = px[s].dropna()
        if len(ser) < 200 or float(ser.iloc[-1]) < MIN_PRICE:
            continue
        e1 = excess(ser, bench, LOOKBACKS[0])
        if e1 is None:
            continue
        sp = span21(ser)
        surge = volume_surge(vol[s]) if s in vol.columns else float("nan")
        prox = high_proximity(ser)
        if pd.isna(sp) or pd.isna(surge) or pd.isna(prox):
            continue
        if sp < MIN_SPAN_AGGR or surge < MIN_SURGE:
            continue
        rsi, mdir = momentum(ser)
        rows.append(dict(sym=s, e1=e1, span=sp, surge=surge, prox=prox,
                         rsi=rsi, mdir=mdir,
                         tag="/".join(src.get(s, {}).get("tags", [])),
                         sector=src.get(s, {}).get("sector")))
    return rows


def score(rows):
    """네 지표를 백분위로 바꿔 가중합. 생값은 단위가 달라 더할 수 없다."""
    if not rows:
        return []
    d = pd.DataFrame(rows)
    for col, w in (("e1", W_MOMENTUM), ("surge", W_VOLUME),
                   ("span", W_VOLATILITY), ("prox", W_HIGH)):
        d[f"p_{col}"] = d[col].rank(pct=True)
    d["score"] = (d.p_e1 * W_MOMENTUM + d.p_surge * W_VOLUME
                  + d.p_span * W_VOLATILITY + d.p_prox * W_HIGH)
    return d.sort_values("score", ascending=False).to_dict("records")


def concentrated_book(px, ranked, n=BOOK_N_AGGR, cap=CAP_AGGR):
    """집중 북. 수비형 build_book 과 **일부러 다르게** 짠다:
      · 상관 필터 없음 — 교수 조언대로 같은 테마에 몰리는 것이 목적이다
      · 섹터 상한 없음 — 같은 이유
      · 역변동성 배분 없음 — 변동성 높은 쪽에 **더** 싣는다(정변동성 가중)
    종목당 20% 상한만 지킨다(대회 규정이라 절대선).
    상위 n 종목 합이 n×cap 이므로 n=4·cap=20% 면 80%, 나머지는 현금이다 —
    이건 의도다. 남은 20%를 억지로 채우려고 확신 없는 5번째를 담지 않는다."""
    picks = [r["sym"] for r in ranked[:n] if r["sym"] in px.columns]
    if not picks:
        return {}
    vol = px[picks].pct_change().std()
    if (vol <= 0).any() or vol.isna().any():
        return {s: cap for s in picks}
    # 🔴 수비형과 정반대: 변동성에 **비례**해 싣는다
    w = vol / vol.sum() * (cap * len(picks))
    return {s: min(cap, float(w[s])) for s in picks}


def main():
    top = 10
    if "--top" in sys.argv:
        try:
            top = int(sys.argv[sys.argv.index("--top") + 1])
        except Exception:
            pass

    df, _ = fetch()
    if BENCH not in df.columns:
        print("벤치마크(ACWI) 를 못 받았다 — 상대값 계산 불가", file=sys.stderr)
        return 1
    b = df[BENCH].dropna()

    src = screen_universe()
    syms = sorted(src)
    if not syms:
        print("유니버스가 비었다", file=sys.stderr)
        return 1

    raw = yf.download(syms, period="1y", interval="1d",
                      progress=False, auto_adjust=True)
    px = raw["Close"].reindex(b.index).ffill().dropna(axis=1, how="all")
    vol = raw["Volume"].reindex(b.index).ffill()

    rows = build_rows(b, src, px, vol)
    ranked = score(rows)

    print(f"\n[공격 스크리닝] 유니버스 {len(syms)}종목 중 조건 통과 {len(ranked)}종목")
    print(f"  조건: 21일 고저폭 ≥{MIN_SPAN_AGGR:.0f}% · 거래량 급증 ≥{MIN_SURGE:.1f}배 · "
          f"주가 ≥${MIN_PRICE:.0f}")
    print(f"  점수 = 모멘텀{W_MOMENTUM:.0%} + 거래량{W_VOLUME:.0%} + "
          f"변동성{W_VOLATILITY:.0%} + 신고가{W_HIGH:.0%} (전부 백분위)")
    if not ranked:
        print("  조건을 통과한 종목이 없다 — 지금은 이 게임을 할 장이 아니다")
        return 0

    print(f"\n  {'':8}{'점수':>6}{'1개월':>9}{'21일폭':>8}{'거래량':>8}{'52주고':>8}{'RSI':>6}   소속")
    for r in ranked[:top]:
        hot = " ⚡" if not pd.isna(r["rsi"]) and r["rsi"] >= RSI_HOT else ""
        print(f"  {r['sym']:8}{r['score']:>6.2f}{r['e1']:>+8.1f}%{r['span']:>7.1f}%"
              f"{r['surge']:>7.1f}x{r['prox']:>7.0%}{r['rsi']:>6.0f}   {r['tag']}{hot}")

    w = concentrated_book(px, ranked)
    if w:
        # 🔴 sector 가 None 이면 DataFrame 왕복에서 NaN(float)이 된다. NaN 은 truthy 라
        # `sec or '섹터미상'` 이 그대로 nan 을 찍는다 — pd.isna 로 걸러야 한다.
        def sector_of(sym):
            v = next((r["sector"] for r in ranked if r["sym"] == sym), None)
            return None if v is None or (isinstance(v, float) and pd.isna(v)) else v

        print(f"\n[집중 북] {len(w)}종목 · 20% 상한 · **정변동성 가중**(변동성 큰 쪽에 더)")
        for s, wt in sorted(w.items(), key=lambda x: -x[1]):
            print(f"  {s:8}{wt:>6.1%}   {sector_of(s) or '섹터미상'}")
        print(f"  합계 {sum(w.values()):.0%} · 미배분 {1 - sum(w.values()):.0%}"
              f" — 확신 없는 종목을 억지로 채우지 않는다")

        secs = [sector_of(s) for s in w]
        known = [x for x in secs if x]
        if known and len(set(known)) == 1 and len(known) == len(secs):
            print(f"  ※ 전 종목이 '{known[0]}' 한 섹터다 — 분산이 아니라 "
                  f"**한 테마 베팅**이다(의도된 것)")

        # 🔴 상관을 **필터로 쓰지는 않지만 보여는 준다.** 수비형과 달리 여기선 같은
        # 테마에 몰리는 게 목적이라 걸러내면 안 되는데, 그렇다고 "4종목 분산"으로
        # 읽히면 곤란하다. 규정상 종목당 20% 는 지켜도 상관 0.99 짜리 두 개를
        # 각각 20%·18% 담으면 **경제적으로는 38% 단일 포지션**이다.
        names = list(w)
        if len(names) >= 2:
            rets = px[names].pct_change().dropna()
            pairs = []
            for i, a in enumerate(names):
                for c in names[i + 1:]:
                    cv = float(rets[a].corr(rets[c]))
                    if not pd.isna(cv) and cv >= 0.80:
                        pairs.append((a, c, cv, w[a] + w[c]))
            for a, c, cv, tot in sorted(pairs, key=lambda x: -x[2]):
                print(f"  🔗 {a}↔{c} 상관 {cv:+.2f} · 합쳐서 {tot:.0%} — "
                      f"규정상 각각 20% 이하지만 **실질적으로 {tot:.0%} 단일 베팅**이다")

    print("\n  🔴 이 목록은 '좋은 종목'이 아니라 '크게 움직일 종목'이다.")
    print("     교수 A(2026-09-17): \"그런 주식만 100개 모아놓으면 평균적으로 하락세를")
    print("     보여요. 다 흥분해서 달려든 주식들이니까요. 그래서 사라고까지는 못 하겠는데.\"")
    print("     기대수익이 플러스라서가 아니라 **분산이 커서** 뽑힌 것이다 —")
    print("     토너먼트에서 꼬리를 사는 것이지 좋은 투자가 아니다.")
    print("  ⚠️ 가중치는 검증된 값이 아니다(표본 없음·생존편향으로 백테스트 불가).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
