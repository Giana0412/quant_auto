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


def screen_universe():
    """섹터·스타일 ETF 의 상위 보유종목을 모아 스크리닝 유니버스를 만든다.

    대회는 섹터가 아니라 **종목**을 산다. 로테이션 표는 어디가 이기는지까지만
    알려주고 "그래서 뭘 사나"가 비어 있어서, 그 간극을 메우려는 것이다.
    목록을 하드코딩하지 않고 ETF 보유종목에서 끌어오므로 알아서 최신이 된다.
    """
    src = {}
    for etf, label in (("XLK", "기술"), ("XLF", "금융"), ("XLE", "에너지"),
                       ("XLV", "헬스케어"), ("XLI", "산업재"),
                       ("IWF", "성장"), ("IWD", "가치"), ("IWM", "소형")):
        try:
            for sym in yf.Ticker(etf).funds_data.top_holdings.index:
                src.setdefault(sym, []).append(label)
        except Exception:
            continue
    return src


def screen(bench, src, top=5):
    """유니버스를 벤치마크 대비 1개월 초과수익으로 줄 세운다."""
    syms = sorted(src)
    if not syms:
        return [], [], [], pd.DataFrame()
    px = yf.download(syms, period="6mo", interval="1d",
                     progress=False, auto_adjust=True)["Close"]
    # 지역·섹터 표와 같은 이유로 벤치마크 달력에 맞춘다 (§fetch 주석 참조)
    px = px.reindex(bench.index).ffill().dropna(axis=1, how="all")

    rows = []
    for s in px.columns:
        ser = px[s].dropna()
        if len(ser) < 70:
            continue
        e1 = excess(ser, bench, LOOKBACKS[0])
        if e1 is None:
            continue
        idx = ser.index.intersection(bench.index)
        rel = (returns(ser[idx]).dropna() - returns(bench[idx]).dropna()).dropna()
        z = zscores(rel, 60).dropna()
        try:
            bt = float(beta(ser[idx], bench[idx], Window(63, 0)).dropna().iloc[-1])
        except Exception:
            bt = float("nan")
        rows.append((e1, float(z.iloc[-1]) if len(z) else 0.0, bt, s,
                     "/".join(src.get(s, []))))
    rows.sort(reverse=True)
    # 전체 rows 도 돌려준다 — 브레드스(몇 %가 벤치를 이기나)를 세야 하기 때문.
    # px 도 돌려준다 — 포지션 사이징이 같은 가격을 다시 받지 않고 재사용하도록.
    return rows[:top], rows[-top:], rows, px


def build_book(px, bench, ranked, cap=0.20, corr_cap=0.75, n=5):
    """20% 상한 안에서 상관 낮은 n종목 북을 짠다.

    순위 순서대로 훑되, **이미 고른 종목과 상관이 corr_cap 을 넘으면 건너뛴다.**
    실측에서 한국↔신흥 +0.95, 기술↔성장 +0.86 처럼 표면적으로 다른 그룹인데
    상관이 극단적으로 높은 쌍이 나왔다 — 순위만 보고 상위 5개를 그대로 담으면
    "20% 씩 5종목 분산"이라 쓰고도 실제로는 한두 개짜리 베팅이 될 수 있다.
    """
    rets = px.pct_change().dropna()
    chosen, skipped = [], []
    for e1, z, bt, sym, tag in ranked:
        if sym not in rets.columns:
            continue
        if len(chosen) >= n:
            break
        if not chosen:
            chosen.append(sym)
            continue
        c = rets[chosen].corrwith(rets[sym]).abs().max()
        if pd.isna(c) or c <= corr_cap:
            chosen.append(sym)
        else:
            skipped.append((sym, float(c)))
    weights = {s: cap for s in chosen}
    return weights, skipped


def book_stats(px, bench, weights):
    """북 전체의 벤치마크 대비 실질 위험. 개별 베타의 단순합이 아니라
    실제 일별 수익률을 합성해서 계산한다 — 상관을 반영하려면 이래야 한다."""
    names = list(weights)
    rets = px[names].pct_change().dropna()
    bret = bench.pct_change().dropna()
    idx = rets.index.intersection(bret.index)
    rets, bret = rets.loc[idx], bret.loc[idx]
    if len(idx) < 40:
        return None
    w = pd.Series(weights)
    port_ret = (rets * w).sum(axis=1)

    cov = float(pd.Series(port_ret).cov(bret))
    var_b = float(bret.var())
    pbeta = cov / var_b if var_b > 0 else float("nan")

    excess_ret = port_ret - bret
    te = float(excess_ret.std()) * (252 ** 0.5) * 100  # 연율화 추적오차(%)

    # 분산비율(DR): 개별 변동성의 가중평균 / 포트폴리오 변동성.
    # 상관이 없으면 1보다 커지고(분산 효과), 전부 같이 움직이면 1에 가까워진다.
    vols = rets.std()
    weighted_avg_vol = float((vols * w).sum())
    port_vol = float(port_ret.std())
    dr = weighted_avg_vol / port_vol if port_vol > 0 else float("nan")

    cash = 1 - sum(weights.values())
    return dict(beta=pbeta, te=te, dr=dr, cash=cash)


def earnings_soon(syms, within=14):
    """가까운 실적발표일. 며칠 뒤에 이벤트가 있으면 진입 타이밍이 달라진다.

    상대강도가 좋아도 이틀 뒤 실적이면 그건 베팅이지 추세추종이 아니다.
    그래서 후보 종목의 발표일을 같이 낸다.
    """
    from datetime import date
    today, out = date.today(), []
    for t in syms:
        try:
            c = yf.Ticker(t).calendar
            eds = c.get("Earnings Date") if isinstance(c, dict) else None
            if not eds:
                continue
            d = min(eds)
            n = (d - today).days
            if 0 <= n <= within:
                out.append((n, t, d))
        except Exception:
            continue
    return sorted(out)


def rs_days(s, b, ma=20):
    """상대강도(자산/벤치마크)가 자기 20일선 위/아래로 며칠째인지.

    1개월·3개월 초과수익은 "얼마나 이겼나"만 말하고 **"언제부터"** 를 말해주지 않는다.
    갓 뒤집힌 것과 두 달째 이기는 것은 확신도가 다르므로 지속일을 같이 낸다.
    """
    i = s.index.intersection(b.index)
    if len(i) < ma + 5:
        return None, 0
    ratio = (s[i] / b[i]).dropna()
    a = (ratio > ratio.rolling(ma).mean()).dropna()
    if a.empty:
        return None, 0
    cur, n = bool(a.iloc[-1]), 0
    for v in a.iloc[::-1]:
        if bool(v) != cur:
            break
        n += 1
    return cur, n


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
            rs_up, rs_n = rs_days(s, b)
            rows.append((e1, e3, zz, bt, name, rs_up, rs_n))
            if abs(zz) >= Z_STRETCH:
                stretched.append((zz, name))

        rows.sort(reverse=True)
        print(f"\n[{gname}] 벤치마크 대비 초과수익")
        print(f"  {'':10}{'1개월':>9}{'3개월':>9}{'z':>7}{'베타':>7}{'RS':>8}   추세")
        for e1, e3, zz, bt, name, rs_up, rs_n in rows:
            # 3개월보다 1개월이 좋으면 가속, 나쁘면 둔화
            trend = "가속 ↑" if e1 > e3 / 3 else ("둔화 ↓" if e1 < 0 < e3 else "")
            rs = f"{'승' if rs_up else '패'}{rs_n}일" if rs_up is not None else "-"
            print(f"  {name:10}{e1:>+8.1f}%{e3:>+8.1f}%{zz:>+7.1f}{bt:>7.2f}{rs:>8}   {trend}")

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

    # ── 종목 스크리닝: "그래서 뭘 사나" ─────────────────────────────────
    if "--no-screen" not in sys.argv:
        try:
            src = screen_universe()
            up, down, allr, px = screen(b, src)
            if up:
                print(f"\n[스크리닝] 유니버스 {len(src)}종목 · 벤치마크 대비 1개월")
                print(f"  {'':8}{'1개월':>9}{'z':>7}{'베타':>7}   소속")
                print("  ── 상위 ──")
                for e1, z, bt, s, tag in up:
                    print(f"  {s:8}{e1:>+8.1f}%{z:>+7.1f}{bt:>7.2f}   {tag}")
                print("  ── 하위 ──")
                for e1, z, bt, s, tag in reversed(down):
                    print(f"  {s:8}{e1:>+8.1f}%{z:>+7.1f}{bt:>7.2f}   {tag}")
                # ── 브레드스: 넓은 장인가 좁은 장인가 ──────────────────
                # 벤치를 이기는 종목 비율. 낮으면 소수 종목이 끌고 가는 좁은 장이라
                # 종목선택이 크게 먹히고, 높으면 지수만 사도 비슷해진다.
                win = sum(1 for r in allr if r[0] > 0)
                pct = win / len(allr) * 100 if allr else 0
                shape = "좁은 장 — 종목선택이 크게 먹힘" if pct < 40 else (
                        "넓은 장 — 지수 대비 이기기 어려움" if pct > 60 else "중립")
                print(f"\n[브레드스]")
                print(f"  스크리닝 {len(allr)}종목 중 {win}개가 벤치 상회 ({pct:.0f}%) — {shape}")
                for gname, members in GROUPS.items():
                    names = [n for n in members.values() if n in df.columns]
                    w = sum(1 for n in names
                            if (excess(df[n].dropna(), b, LOOKBACKS[0]) or 0) > 0)
                    print(f"  {gname}: {w}/{len(names)} 이김")

                # ── 실적발표 임박 ─────────────────────────────────────
                cand = [r[3] for r in up] + list(extras)
                ev = earnings_soon(cand)
                print(f"\n[실적발표 14일 내]")
                if ev:
                    for n, t, d in ev:
                        print(f"  {t} — {d} (D-{n})")
                else:
                    print("  없음")

                # ── 포지션 사이징: 20% 상한 안에서 상관 낮은 5종목 북 ────────
                # 순위(초과수익) 그대로 상위 5개를 담으면 상관 높은 쌍이 섞여
                # "5종목 분산"이라 쓰고도 실제로는 한두 개짜리 베팅이 될 수 있다
                # (§build_book 주석 — 한국↔신흥 +0.95 실측 사례).
                weights, skipped = build_book(px, b, up)
                stats = book_stats(px, b, weights) if weights else None
                print(f"\n[포지션 사이징] 20% 상한 · 상관 {0.75:.0%} 미만만 편입")
                if weights:
                    tag_of = {sym: tag for _, _, _, sym, tag in up}
                    for s, w in weights.items():
                        print(f"  {s:8}{w:>6.0%}   {tag_of.get(s, '')}")
                    if skipped:
                        print("  제외(상관 과다): " +
                              " · ".join(f"{s}({c:+.2f})" for s, c in skipped))
                    if stats:
                        print(f"  북 베타 {stats['beta']:+.2f} · 추적오차(연) {stats['te']:.1f}%p"
                              f" · 분산비율 {stats['dr']:.2f} · 미배분 {stats['cash']:.0%}")
                        print("  ※ 베타·추적오차는 과거 60~63일 관측치다. 미래 예측이 아니다.")
                else:
                    print("  구성 불가 (후보 부족)")
        except Exception as e:
            print(f"\n[스크리닝] 실패: {str(e)[:60]}", file=sys.stderr)

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
