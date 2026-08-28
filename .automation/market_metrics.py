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

── 2026-08-24 확장: 단발 스냅샷 → 빌드업 ─────────────────────────────────
초과수익·베타·상관은 "오늘 상태"만 말한다. 매매대회는 하루 만에 끝나지 않으므로
**오늘이 어제·그제와 이어지는 흐름의 어디쯤인지**가 필요하다. 그래서 세 가지를
더한다:
  1. [모멘텀] RSI·MACD — 초과수익이 막 꺾이려는 참인지 스크립트가 미리 감지한다.
  2. [빌드업] 매 실행마다 레짐·브레드스·1등 그룹을 personal/10-market/_buildup/
     에 append 한다. 다음날 실행이 어제 기록을 읽어 "며칠째 유지"를 낸다.
     스냅샷 하나로는 "오늘 그렇다"만 알 수 있고 "언제부터"는 알 수 없다.
  3. [백테스트] strategy_backtest.py(주간, 별도 실행)가 남긴 캐시를 읽어
     "이 로테이션 규칙이 최근 몇 달 실제로 벤치를 이겼나"를 한 줄로 인용한다.
     매일 재계산하기엔 무겁고 결과도 하루 단위로 안 바뀌어서 캐시로 뺐다.

── 2026-08-28 확장: 신호 → 실제 체결 대조 ────────────────────────────────
위 셋은 전부 "신호가 뭐였나"만 말한다. 대회 성적은 신호가 아니라 **실제로
산 것**으로 결정되고, 이 파이프라인은 블룸버그 터미널과 연동돼 있지 않아
(개인 참가자용 API 라이선스가 없다) 실제 체결을 스스로는 알 수 없다.
그래서 .automation/log_trade.py 로 사람이 체결을 남기면, [체결추적]이 그
포지션이 지금 신호대로 가고 있는지(진입가 대비 수익·벤치 대비 초과수익)를
매일 다시 계산한다 — "규칙이 틀렸나 실행이 틀렸나"를 나중에 가를 수 있도록.

── 2026-08-28 확장(2): 위험조정·청산·전략모드 ────────────────────────────
지금까지는 전부 "얼마나 이겼나(raw 초과수익)"로만 줄 세우고, 사면 언제 파는지는
없고, 오늘 뭘 봐야 하는지(로테이션이냐 스크리닝이냐)도 브리핑 읽는 사람이 매번
판단해야 했다. 세 가지를 더한다:
  1. **위험조정 랭킹·사이징** — [지역]/[섹터]/[스타일]/[종목]/[스크리닝] 정렬을
     raw e1 에서 info_score(변동성 대비 초과수익, §info_score)로 바꿨다.
     [포지션 사이징]도 flat 20%가 아니라 역변동성 가중(§build_book)이다.
  2. **청산 규칙** — [체결추적]에 트레일링손절(고점 대비 STOP_FROM_PEAK%)·
     손절(진입가 대비 STOP_FROM_ENTRY%)·익절 후보(수익 중 RSI 과열) 플래그를
     붙인다. 매도 지시가 아니라 후보 통지이고, 최종 판단은 사람이 한다.
  3. **전략모드** — [브레드스]가 이미 계산해 두던 "좁은 장/넓은 장" 서술을
     "그래서 오늘은 로테이션 위주냐 스크리닝 위주냐"는 명시적 행동 권고로
     바꿔 [전략모드] 절로 낸다.

실행:
  .automation/.venv/bin/python .automation/market_metrics.py
  .automation/.venv/bin/python .automation/market_metrics.py META 005930.KS   # 종목 추가
  .automation/.venv/bin/python .automation/log_trade.py AAPL buy 230.50 --shares 100 --note "..."
"""
import json
import sys
import warnings
from datetime import date, datetime
from pathlib import Path
from zoneinfo import ZoneInfo

warnings.filterwarnings("ignore")

import pandas as pd
import yfinance as yf
from gs_quant.timeseries import (
    Window, beta, correlation, macd, max_drawdown, relative_strength_index,
    returns, volatility, zscores,
)

BENCH = "벤치마크"

GROUPS = {
    "지역": {"SPY": "미국", "EFA": "선진ex미", "EEM": "신흥", "EWY": "한국", "EWJ": "일본"},
    "섹터": {"XLK": "기술", "XLF": "금융", "XLE": "에너지", "XLV": "헬스케어", "XLI": "산업재"},
    "스타일": {"IWF": "성장", "IWD": "가치", "IWM": "미국소형"},
}
EXTRA = {"ACWI": BENCH, "^VIX": "VIX"}

Z_STRETCH = 1.5
RSI_HOT, RSI_COLD = 70, 30
LOOKBACKS = (21, 63)   # 1개월, 3개월 (영업일)
BREADTH_NARROW, BREADTH_WIDE = 40, 60   # 브레드스 %. [브레드스] 서술과 [전략모드] 권고가 같은 임계값을 쓴다

# 청산 규칙(§trade_followup) 기본값 — "공식 최적값"이 아니라 대회 기간(수개월) 스윙 매매
# 기준의 출발점이다. 너무 타이트하면 정상 눌림에도 매번 손절 신호가 뜨고, 너무 느슨하면
# 신호로서 의미가 없다 — 실제 체결 데이터가 쌓이면 이 두 값부터 조정 대상이다.
STOP_FROM_PEAK = -10.0    # 트레일링 손절: 진입 이후 고점 대비 하락률
STOP_FROM_ENTRY = -7.0    # 손절: 진입가 대비 하락률 (트레일링보다 먼저 걸릴 수도 나중에 걸릴 수도 있다)

# personal/ 은 별도 git 저장소(§README "데이터는 어디 있나") — 여기 쓰는 것만 누적된다
BUILDUP_LOG = Path("personal/10-market/_buildup/regime-log.jsonl")
BACKTEST_CACHE = Path("personal/10-market/_backtest/latest.json")
TRADE_LOG = Path("personal/10-market/_trades/trade-log.jsonl")


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


def momentum(s):
    """RSI(14)·MACD(12,26) 방향. 초과수익 표는 "얼마나 이겼나"만 말하고
    "지금 꺾이는 중인가"는 말 안 해준다 — 그 간극을 메운다.
    둘 다 gs_quant.timeseries 순수 계산이라 Marquee 인증 없이 돈다."""
    try:
        rsi = float(relative_strength_index(s, 14).dropna().iloc[-1])
    except Exception:
        rsi = float("nan")
    try:
        m = macd(s, 12, 26).dropna()
        # 데이터가 모자라면(len(m)<=5) None — "하락"으로 단정하면 없는 신호를
        # 지어내는 것과 같다. RSI 쪽은 dropna() 가 이미 NaN 으로 걸러주는데
        # MACD 는 ewm 기반이라 NaN 이 안 나와서 여기서 직접 막아야 한다.
        mdir = None if len(m) <= 5 else ("상승" if float(m.iloc[-1]) > float(m.iloc[-6]) else "하락")
    except Exception:
        mdir = None
    return rsi, mdir


def screen_universe():
    """섹터·스타일 ETF 의 상위 보유종목을 모아 스크리닝 유니버스를 만든다.

    대회는 섹터가 아니라 **종목**을 산다. 로테이션 표는 어디가 이기는지까지만
    알려주고 "그래서 뭘 사나"가 비어 있어서, 그 간극을 메우려는 것이다.
    목록을 하드코딩하지 않고 ETF 보유종목에서 끌어오므로 알아서 최신이 된다.

    ※ 이게 **오늘 시점** 보유종목이라는 점이 중요하다 — 과거로 돌아가 "그때의
    상위 보유종목"을 구할 방법이 없으므로 이 유니버스 자체는 백테스트가 불가능하다
    (strategy_backtest.py 가 그룹 단위로만 검증하는 이유. 그 스크립트 docstring 참고).
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
    """유니버스를 **위험조정** 순위 점수(info_score — 변동성 대비 벤치마크 대비
    1개월 초과수익)로 줄 세운다. raw 초과수익(e1)은 표시용으로 같이 낸다.

    🔴 raw e1 로만 줄 세우던 예전 버전은 변동성이 큰 종목이 한 달 반짝 튀면
    바로 상위권(=매수 후보)에 올라왔다 — 고베타 종목을 보상 없이 담는 것과
    같다. info_score 로 바꾸면 "꾸준히 이긴 종목"이 "크게 흔들리며 이긴 종목"
    보다 앞에 온다."""
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
        rsi, mdir = momentum(ser)
        scr = info_score(e1, rel_vol(rel))
        rows.append((e1, float(z.iloc[-1]) if len(z) else 0.0, bt, s,
                     "/".join(src.get(s, [])), rsi, mdir, scr))
    # key= 로 정렬한다 — rsi 뒤에 mdir(str|None) 이 붙어 있어 튜플 기본비교가
    # None과 str을 비교하려다 TypeError 를 낼 수 있다. scr 이 NaN(변동성 계산
    # 실패 등)이면 맨 뒤로 보낸다 — NaN 은 정렬 비교 자체가 정의되지 않아
    # 그대로 두면 위치가 안정적이지 않다.
    rows.sort(key=lambda r: r[7] if not pd.isna(r[7]) else float("-inf"), reverse=True)
    # 전체 rows 도 돌려준다 — 브레드스(몇 %가 벤치를 이기나)를 세야 하기 때문.
    # px 도 돌려준다 — 포지션 사이징이 같은 가격을 다시 받지 않고 재사용하도록.
    return rows[:top], rows[-top:], rows, px


def build_book(px, bench, ranked, cap=0.20, corr_cap=0.75, n=5, vol_scale=True):
    """20% 상한 안에서 상관 낮은 n종목 북을 짠다.

    순위 순서대로 훑되, **이미 고른 종목과 상관이 corr_cap 을 넘으면 건너뛴다.**
    실측에서 한국↔신흥 +0.95, 기술↔성장 +0.86 처럼 표면적으로 다른 그룹인데
    상관이 극단적으로 높은 쌍이 나왔다 — 순위만 보고 상위 5개를 그대로 담으면
    "20% 씩 5종목 분산"이라 쓰고도 실제로는 한두 개짜리 베팅이 될 수 있다.

    ranked 의 각 행은 앞 5개(e1, z, bt, sym, tag)만 쓴다 — 뒤에 momentum()·
    info_score 가 붙은 8튜플(screen() 출력)이 와도, 5튜플(strategy_backtest.py
    가 그룹으로 직접 만든 순위)이 와도 그대로 재사용되도록 슬라이스로 받는다.

    vol_scale=True(기본) 면 **역변동성 가중**을 쓴다 — 변동성 낮은 종목엔
    cap 근처까지, 높은 종목엔 그보다 적게 배분한다(평균이 cap 근처가 되도록
    스케일한 뒤 cap 으로 다시 자른다). 20% 상한은 안전판으로 그대로 유지한다
    — 대회 규정(포지션당 20%)은 변동성과 무관하게 못 넘는 절대선이라서다.
    상한에 걸려 못 배분한 몫은 재분배하지 않고 미배분(현금)으로 남긴다 —
    재분배를 시도하면 역변동성 로직과 상한 로직이 서로 되먹임을 일으켜
    수렴을 보장하기 어렵다. vol_scale=False 면 예전처럼 flat cap 을 쓴다."""
    rets = px.pct_change().dropna()
    chosen, skipped = [], []
    for row in ranked:
        e1, z, bt, sym, tag = row[:5]
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

    if not chosen:
        return {}, skipped
    if not vol_scale or len(chosen) < 2:
        return {s: cap for s in chosen}, skipped

    vol = rets[chosen].std()
    if (vol <= 0).any() or vol.isna().any():
        # 변동성이 0/NaN 인 종목(상장 직후 등)이 섞이면 역수가 발산하거나
        # 정의되지 않는다 — 이럴 땐 안전하게 flat cap 으로 되돌아간다.
        return {s: cap for s in chosen}, skipped
    inv = 1 / vol
    raw_w = inv / inv.sum() * (cap * len(chosen))   # 평균 배분이 cap 근처가 되도록 스케일
    weights = {s: min(cap, float(raw_w[s])) for s in chosen}
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

    # 정보비율(IR) = 연율화 초과수익 / 추적오차. gs_quant.sharpe_ratio 는 무위험
    # 금리 커브를 Marquee 에서 받아와야 해서 오프라인에서 못 쓴다 — 애초에 대회
    # 평가축(벤치 대비 상대수익)엔 무위험금리가 안 들어가므로 IR 이 더 맞는 지표다.
    # 🔴 **표본내(in-sample) 편향**: weights 는 바로 이 excess_ret 을 만든 같은
    # 60~63일 구간에서 "1개월 초과수익 상위"로 뽑은 종목들이다. 즉 이 IR·연환산
    # 초과수익은 "고른 기준으로 다시 잰 성적"이라 구조적으로 부풀려진다 — 새로
    # 고른 북은 거의 항상 IR 이 높게 나온다. strategy_backtest.py 의 [백테스트]가
    # (다음 구간 실현수익으로 평가하므로) 이 편향이 없는 진짜 검증값이다.
    ann_excess = float(excess_ret.mean()) * 252 * 100  # 연율화 초과수익(%p)
    ir = ann_excess / te if te > 0 else float("nan")

    # 최대낙폭(절대, MDD): 북을 지금 비중대로 관측기간 내내 들고 있었다면 겪었을
    # 최악의 고점 대비 하락 — **초과수익이 아니라 북 자체의 절대 수익률 기준**이다.
    # strategy_backtest.py 의 최대낙폭(누적 초과수익 기준, %p)과 계산 대상이 달라
    # 숫자를 나란히 비교하면 안 된다 — 그래서 단위도 %p 가 아니라 %로 낸다.
    book_idx = (1 + port_ret).cumprod()
    try:
        mdd = float(max_drawdown(book_idx, Window(len(book_idx), 0)).dropna().min()) * 100
    except Exception:
        mdd = float("nan")

    cash = 1 - sum(weights.values())
    return dict(beta=pbeta, te=te, dr=dr, cash=cash, ir=ir, mdd=mdd, ann_excess=ann_excess)


def earnings_soon(syms, within=14):
    """가까운 실적발표일. 며칠 뒤에 이벤트가 있으면 진입 타이밍이 달라진다.

    상대강도가 좋아도 이틀 뒤 실적이면 그건 베팅이지 추세추종이 아니다.
    그래서 후보 종목의 발표일을 같이 낸다.
    """
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


def rel_vol(rel, window=60):
    """상대(초과)수익률 시계열의 연율화 변동성(%). book_stats() 의 추적오차(te)와
    같은 식(std × √252 × 100)을 종목 하나 단위로 재사용한다 — 위험조정 순위
    점수(info_score) 계산에 쓴다."""
    r = rel.dropna()
    if len(r) < window:
        return float("nan")
    v = float(r.tail(window).std()) * (252 ** 0.5) * 100
    return v if v > 0 else float("nan")


def info_score(e1, rvol):
    """위험조정 순위 점수 = "변동성 대비 초과수익". e1(21영업일 누적 %, 연율화 안 함)을
    연율화된 rvol 로 나눈다 — 분자·분모 기간이 안 맞아 이 값 자체가 '샤프비율'은
    아니지만, **모든 후보를 같은 잣대로 나누므로 상대비교(랭킹)용으로는 문제 없다.**

    raw e1 만으로 줄 세우면 그냥 변동성이 큰 종목이 한 달 반짝 튀어 상위로 올라온다 —
    베타 큰데 마이너스면 "위험만 지는 조합"이라고 [지는 쪽] 절에서 이미 걸러내던 것과
    같은 문제를, 상위권(사는 쪽) 랭킹 단계에서부터 막는 것이다."""
    if pd.isna(rvol) or rvol <= 0:
        return float("nan")
    return e1 / rvol


def _read_buildup_records():
    """로그를 읽어 "date" 키가 있는 레코드만 돌려준다. 깨진 줄(파싱 실패)이나
    "date" 없는 레코드가 섞여 들어오면 뒤에서 r["date"] 로 정렬할 때 KeyError 로
    죽어 [백테스트]·[스트레치]·[상관] 까지 통째로 못 찍는다 — 그래서 여기서 한 번에 거른다."""
    if not BUILDUP_LOG.exists():
        return []
    recs = []
    for line in BUILDUP_LOG.read_text().splitlines():
        try:
            rec = json.loads(line)
        except Exception:
            continue
        if isinstance(rec, dict) and "date" in rec:
            recs.append(rec)
    return recs


def log_buildup(today_kst, snapshot):
    """오늘의 레짐 스냅샷을 append-only 로그에 남긴다. 같은 날 재실행하면
    옛 기록을 덮어쓴다 (하루 여러 번 돌아도 로그가 하루당 한 줄만 남도록) —
    evening-chain 이 저녁에 백업으로 한 번 더 도는 설계와 같은 이유다.

    파일에 바로 쓰지 않고 임시파일에 쓴 뒤 os.replace 로 바꿔치기한다 —
    직접 쓰면 실행이 중간에 죽었을 때(타임아웃 kill 등, evening-chain.sh 의
    각 단계 상한 참고) 파일이 반쯤 잘린 채로 남아 그날 이후 로그 전체를
    잃을 수 있다. os.replace 는 원자적이라 "쓰기 전 상태" 아니면 "쓰기 후
    상태" 둘 중 하나만 존재한다.

    같은 날 재실행분은 **병합**한다(덮어쓰기 아님) — 이번 값 중 None 인 필드는
    이전 기록 값을 유지한다. `--no-screen` 재실행이나 스크리닝 실패로 이번 스냅샷의
    breadth_pct 등이 None 이 되면, 앞서 성공한 실행이 남긴 값을 지우지 않기 위해서다."""
    records = _read_buildup_records()
    prior = next((r for r in records if r["date"] == today_kst), None)
    rows = [r for r in records if r["date"] != today_kst]
    merged = dict(prior or {})
    merged.update({"date": today_kst})
    merged.update({k: v for k, v in snapshot.items() if v is not None})
    rows.append(merged)
    rows.sort(key=lambda r: r["date"])
    BUILDUP_LOG.parent.mkdir(parents=True, exist_ok=True)
    tmp = BUILDUP_LOG.with_suffix(BUILDUP_LOG.suffix + ".tmp")
    with tmp.open("w") as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    tmp.replace(BUILDUP_LOG)


def buildup_trend(days=10, gap_break_days=5):
    """최근 기록에서 지속성을 뽑는다. 스냅샷 하나로는 '오늘 그렇다'만 말할 수 있고
    '며칠째'는 못 준다 — 그 간극을 메운다.

    연속(streak)은 **전체 로그**에서 센다 — days 로 자른 창 안에서만 세면 실제로는
    6주째 같은 레짐인데도 최대 10회로 잘려 보인다. 대신 기록 사이 날짜 간격이
    gap_break_days 를 넘으면(노트북이 며칠 잠들어 있었거나 --skip 로 건너뛴 경우)
    "계속 유지"로 세지 않고 거기서 끊는다 — 안 그러면 80일 떨어진 기록 두 개가
    "3일째 유지"처럼 찍힌다. 그리고 이 숫자는 **영업일이 아니라 기록 횟수**다
    (스크립트를 하루 두 번 돌리면 today_kst 로 병합되니 중복은 안 되지만, 실행을
    건너뛴 날은 기록 자체가 없다) — 그래서 '일째'가 아니라 '회째'로 표시한다."""
    recs = sorted(_read_buildup_records(), key=lambda r: r["date"])
    if len(recs) < 2:
        return None

    def streak(key):
        cur = recs[-1].get(key)
        n, prev_date = 0, None
        for r in reversed(recs):
            if r.get(key) != cur:
                break
            d = r["date"]
            if prev_date is not None:
                gap = (date.fromisoformat(prev_date) - date.fromisoformat(d)).days
                if gap > gap_break_days:
                    break
            n += 1
            prev_date = d
        return cur, n

    regime, regime_n = streak("above_ma50")
    top, top_n = streak("top_group")
    window = recs[-days:]
    return dict(
        n=len(window), regime=regime, regime_n=regime_n, top=top, top_n=top_n,
        breadth_first=window[0].get("breadth_pct"), breadth_last=window[-1].get("breadth_pct"),
    )


def backtest_summary(max_age_days=10):
    """strategy_backtest.py(주간 실행)가 남긴 캐시를 읽는다. 매일 새로 돌리기엔
    무겁고 결과도 하루 단위로 안 바뀌어서 참조만 한다. 캐시가 오래됐으면(기본
    10일 초과) 묵은 숫자를 오늘 것처럼 내지 않고 없는 것으로 취급한다 —
    market_snapshot.py 의 age_days 표시와 같은 원칙.

    ("파일이 아예 없음" / "있는데 오래됨") 을 ("state", ...) 로 구분해 돌려준다 —
    같은 '아직 없음'으로 뭉쳐버리면 주간 잡(strategy-backtest-weekly)이 죽어서
    캐시가 몇 주째 안 갱신되는 상황과 "한 번도 설치 안 함"이 구분이 안 된다."""
    if not BACKTEST_CACHE.exists():
        return dict(state="missing")
    try:
        data = json.loads(BACKTEST_CACHE.read_text())
        age = (date.today() - date.fromisoformat(data["as_of"])).days
    except Exception:
        return dict(state="corrupt")
    if age > max_age_days:
        return dict(state="stale", as_of=data.get("as_of"), age_days=age)
    data["age_days"] = age
    data["state"] = "fresh"
    return data


def trade_followup(b):
    """실제 체결(사람이 손으로 남긴 기록)이 신호대로 가고 있는지 매일 추적한다.

    이 파이프라인은 블룸버그 터미널과 연동돼 있지 않다 — 개인 참가자용 API
    라이선스가 없어서 Marquee 를 못 쓰는 것과 같은 이유다. 그래서 실제 체결은
    스크립트가 알 방법이 없고, .automation/log_trade.py 로 사람이 남겨야 한다.
    이 함수는 그 로그를 읽어 "브리핑 신호를 따라 실제로 샀을 때 지금 어떻게
    됐나"를 계산한다 — 대회가 끝난 뒤 신호 자체가 맞았는지 vs 체결/타이밍이
    틀렸는지를 구분하려면 이 기록이 있어야 한다.

    포지션 상태는 티커별 **가장 최근 기록의 side** 로만 판단한다(정식 FIFO
    체결 장부가 아니라 개인용 추적이다) — 마지막이 buy 면 보유 중으로 보고
    현재가를 붙이고, 마지막이 sell 이면 이미 닫힌 포지션이라 뺀다.

    청산 신호(exit)도 여기서 같이 낸다 — 지금까지는 진입 신호([스크리닝]·
    [모멘텀])만 있고 "그래서 언제 파나"가 없었다. 진입 후 고점 대비
    STOP_FROM_PEAK% 하락(트레일링 손절), 진입가 대비 STOP_FROM_ENTRY% 하락
    (손절), 또는 수익 중인데 RSI 가 과열로 돌아선 경우(익절 후보) 셋 중 하나면
    플래그를 붙인다. **매도 지시가 아니라 후보 통지다** — 최종 판단은 사람이 한다."""
    if not TRADE_LOG.exists():
        return []
    recs = []
    for line in TRADE_LOG.read_text().splitlines():
        try:
            r = json.loads(line)
        except Exception:
            continue
        if isinstance(r, dict) and {"date", "ticker", "side", "price"} <= r.keys():
            recs.append(r)
    if not recs:
        return []

    by_ticker = {}
    for r in sorted(recs, key=lambda r: r["date"]):
        by_ticker.setdefault(r["ticker"], []).append(r)

    out = []
    for ticker, events in by_ticker.items():
        last = events[-1]
        if last.get("side") != "buy":
            continue
        try:
            entry_date = date.fromisoformat(last["date"])
            entry_price = float(last["price"])
            h = yf.Ticker(ticker).history(period="6mo", interval="1d")["Close"].dropna()
            h.index = h.index.tz_localize(None)
            h = h[h.index.date >= entry_date]
            if len(h) < 1:
                continue
            cur_price = float(h.iloc[-1])
            peak_price = float(h.max())
            ret = (cur_price / entry_price - 1) * 100
            dd_from_peak = (cur_price / peak_price - 1) * 100
            bidx = b[b.index.date >= entry_date]
            bench_ret = ((float(bidx.iloc[-1]) / float(bidx.iloc[0]) - 1) * 100
                         if len(bidx) >= 1 else float("nan"))
            excess_ret = ret - bench_ret if not pd.isna(bench_ret) else float("nan")

            rsi, _ = momentum(h)
            exit_flag = None
            if dd_from_peak <= STOP_FROM_PEAK:
                exit_flag = f"🔴 트레일링손절 후보(고점 {peak_price:.2f} 대비 {dd_from_peak:+.1f}%)"
            elif ret <= STOP_FROM_ENTRY:
                exit_flag = f"🔴 손절 후보(진입가 대비 {ret:+.1f}%)"
            elif ret > 0 and not pd.isna(rsi) and rsi >= RSI_HOT:
                exit_flag = f"🟡 익절 후보(RSI{rsi:.0f} 과열, 진입가 대비 {ret:+.1f}%)"

            out.append(dict(
                ticker=ticker, entry_date=last["date"], entry_price=entry_price,
                cur_price=cur_price, ret=ret, bench_ret=bench_ret, excess=excess_ret,
                days=(date.today() - entry_date).days, note=last.get("note") or "",
                exit_flag=exit_flag,
            ))
        except Exception:
            continue
    return out


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
    above_ma50 = float(b.iloc[-1]) > float(ma50.iloc[-1])
    print(f"벤치마크 {float(b.iloc[-1]):.2f} · 30일변동성 {float(bvol.iloc[-1]):.1f}% · "
          f"50MA {'위' if above_ma50 else '아래'}")
    vix_val = None
    if "VIX" in df.columns:
        v = df["VIX"].dropna()
        vix_val = float(v.iloc[-1])
        d5 = (vix_val / float(v.iloc[-6]) - 1) * 100 if len(v) > 6 else 0
        print(f"VIX {vix_val:.1f} (5일 {d5:+.0f}%)")
    rsi_b, mdir_b = momentum(b)
    if pd.isna(rsi_b):
        # NaN 을 그대로 비교식에 넣으면 전부 False 라 "중립"으로 떨어진다 —
        # "계산 못 했다"와 "중립이다"는 다른 말이므로 갈라서 찍는다.
        print(f"모멘텀 RSI 계산 불가 · MACD {mdir_b or '-'}")
    else:
        print(f"모멘텀 RSI {rsi_b:.0f} · MACD {mdir_b or '-'} "
              f"({'과열' if rsi_b >= RSI_HOT else '과매도' if rsi_b <= RSI_COLD else '중립'})")

    # ── 그룹별 초과수익 순위 ─────────────────────────────────────────────
    # 🔴 2026-08-28: 정렬 기준을 raw 1개월 초과수익(e1)에서 위험조정 점수(scr =
    # info_score, 변동성 대비 초과수익)로 바꿨다. '1등 그룹'의 뜻이 바뀌므로
    # buildup_trend() 의 top_group 연속기록은 이 시점 전후로 끊겨 보일 수 있다
    # (같은 레짐이 계속돼도 랭킹 기준이 바뀐 것뿐인데 "방금 1등이 바뀜"으로
    # 찍힌다는 뜻) — 방법론이 바뀐 것이지 시장이 바뀐 게 아니다.
    stretched, hot_cold, group_bests = [], [], []
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
            rsi, mdir = momentum(s)
            scr = info_score(e1, rel_vol(rel))
            rows.append((e1, e3, zz, bt, name, rs_up, rs_n, rsi, mdir, scr))
            if abs(zz) >= Z_STRETCH:
                stretched.append((zz, name))
            if not pd.isna(rsi) and (rsi >= RSI_HOT or rsi <= RSI_COLD):
                hot_cold.append((rsi, mdir, name))

        # scr 이 NaN 이면 맨 뒤로 — screen() 과 같은 이유(NaN 비교는 정의되지 않는다)
        rows.sort(key=lambda r: r[9] if not pd.isna(r[9]) else float("-inf"), reverse=True)
        if rows:
            group_bests.append((rows[0][9], rows[0][4]))
        print(f"\n[{gname}] 벤치마크 대비 (위험조정순 · scr=변동성대비초과수익)")
        print(f"  {'':10}{'scr':>7}{'1개월':>9}{'3개월':>9}{'z':>7}{'베타':>7}{'RS':>8}   추세")
        for e1, e3, zz, bt, name, rs_up, rs_n, rsi, mdir, scr in rows:
            # 3개월보다 1개월이 좋으면 가속, 나쁘면 둔화
            trend = "가속 ↑" if e1 > e3 / 3 else ("둔화 ↓" if e1 < 0 < e3 else "")
            rs = f"{'승' if rs_up else '패'}{rs_n}일" if rs_up is not None else "-"
            scr_txt = f"{scr:>+6.2f}" if not pd.isna(scr) else "   -  "
            print(f"  {name:10}{scr_txt}{e1:>+8.1f}%{e3:>+8.1f}%{zz:>+7.1f}{bt:>7.2f}{rs:>8}   {trend}")

    # scr 이 전부 NaN(60일치 데이터가 모자란 조합 등)인 그룹은 max() 비교에서
    # NaN 이 항상 False 를 내는 파이썬 특성 때문에 엉뚱한 그룹이 뽑힐 수 있어
    # 여기서 걸러낸다 — 정상 운영(1년치 fetch)에선 거의 발생하지 않는 경로다.
    valid_bests = [g for g in group_bests if not pd.isna(g[0])]
    top_group_name = max(valid_bests, key=lambda g: g[0])[1] if valid_bests else None

    # ── 뉴스에서 넘어온 개별 종목 ────────────────────────────────────────
    if extras:
        print("\n[종목] 벤치마크 대비 (위험조정순 · scr=변동성대비초과수익)")
        print(f"  {'':12}{'scr':>7}{'1개월':>9}{'3개월':>9}{'z':>7}{'베타':>7}")
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
            rsi, mdir = momentum(s)
            scr = info_score(e1, rel_vol(rel))
            srows.append((e1, e3, zz, bt, name, rsi, mdir, scr))
            if abs(zz) >= Z_STRETCH:
                stretched.append((zz, name))
            if not pd.isna(rsi) and (rsi >= RSI_HOT or rsi <= RSI_COLD):
                hot_cold.append((rsi, mdir, name))
        srows.sort(key=lambda r: r[7] if not pd.isna(r[7]) else float("-inf"), reverse=True)
        for e1, e3, zz, bt, name, rsi, mdir, scr in srows:
            scr_txt = f"{scr:>+6.2f}" if not pd.isna(scr) else "   -  "
            print(f"  {name:12}{scr_txt}{e1:>+8.1f}%{e3:>+8.1f}%{zz:>+7.1f}{bt:>7.2f}")
        if not srows:
            print("  (조회된 종목 없음)")

    # ── 종목 스크리닝: "그래서 뭘 사나" ─────────────────────────────────
    pct = None
    if "--no-screen" not in sys.argv:
        try:
            src = screen_universe()
            up, down, allr, px = screen(b, src)
            if up:
                print(f"\n[스크리닝] 유니버스 {len(src)}종목 · 위험조정순(scr=변동성대비 1개월초과수익)")
                print(f"  {'':8}{'scr':>7}{'1개월':>9}{'z':>7}{'베타':>7}   소속")
                print("  ── 상위 ──")
                for e1, z, bt, s, tag, rsi, mdir, scr in up:
                    extreme = not pd.isna(rsi) and (rsi >= RSI_HOT or rsi <= RSI_COLD)
                    flag = f" ⚡RSI{rsi:.0f}" if extreme else ""
                    scr_txt = f"{scr:>+6.2f}" if not pd.isna(scr) else "   -  "
                    print(f"  {s:8}{scr_txt}{e1:>+8.1f}%{z:>+7.1f}{bt:>7.2f}   {tag}{flag}")
                    if extreme:
                        hot_cold.append((rsi, mdir, s))
                print("  ── 하위 ──")
                for e1, z, bt, s, tag, rsi, mdir, scr in reversed(down):
                    extreme = not pd.isna(rsi) and (rsi >= RSI_HOT or rsi <= RSI_COLD)
                    flag = f" ⚡RSI{rsi:.0f}" if extreme else ""
                    scr_txt = f"{scr:>+6.2f}" if not pd.isna(scr) else "   -  "
                    print(f"  {s:8}{scr_txt}{e1:>+8.1f}%{z:>+7.1f}{bt:>7.2f}   {tag}{flag}")
                    if extreme:
                        hot_cold.append((rsi, mdir, s))
                # ── 브레드스: 넓은 장인가 좁은 장인가 ──────────────────
                # 벤치를 이기는 종목 비율. 낮으면 소수 종목이 끌고 가는 좁은 장이라
                # 종목선택이 크게 먹히고, 높으면 지수만 사도 비슷해진다.
                win = sum(1 for r in allr if r[0] > 0)
                pct = win / len(allr) * 100 if allr else 0
                shape = "좁은 장 — 종목선택이 크게 먹힘" if pct < BREADTH_NARROW else (
                        "넓은 장 — 지수 대비 이기기 어려움" if pct > BREADTH_WIDE else "중립")
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

                # ── 포지션 사이징: 20% 상한 안에서 상관 낮은 5종목 북, 역변동성 배분 ──
                # 순위(위험조정 점수) 그대로 상위 5개를 담으면 상관 높은 쌍이 섞여
                # "5종목 분산"이라 쓰고도 실제로는 한두 개짜리 베팅이 될 수 있다
                # (§build_book 주석 — 한국↔신흥 +0.95 실측 사례). 비중도 더 이상
                # flat 20%가 아니라 역변동성 가중이다(§build_book 주석) — 변동성
                # 낮은 종목엔 상한 근처까지, 높은 종목엔 그보다 적게 담아 "20%씩
                # 5종목"이 아니라 "20% 상한 안에서 위험을 맞춘 5종목"이 된다.
                weights, skipped = build_book(px, b, up)
                stats = book_stats(px, b, weights) if weights else None
                print(f"\n[포지션 사이징] 20% 상한 · 상관 {0.75:.0%} 미만만 편입 · 역변동성 배분")
                if weights:
                    tag_of = {r[3]: r[4] for r in up}
                    for s, w in weights.items():
                        print(f"  {s:8}{w:>6.0%}   {tag_of.get(s, '')}")
                    if skipped:
                        print("  제외(상관 과다): " +
                              " · ".join(f"{s}({c:+.2f})" for s, c in skipped))
                    if stats:
                        print(f"  북 베타 {stats['beta']:+.2f} · 추적오차(연) {stats['te']:.1f}%p"
                              f" · 분산비율 {stats['dr']:.2f} · 미배분 {stats['cash']:.0%}")
                        print(f"  연환산 초과수익(표본내) {stats['ann_excess']:+.1f}%p"
                              f" · 정보비율(표본내) {stats['ir']:+.2f} · 최대낙폭(절대) {stats['mdd']:+.1f}%")
                        print("  ※ 베타·추적오차는 과거 60~63일 관측치다. 미래 예측이 아니다.")
                        print("  ※ 연환산 초과수익·정보비율은 방금 그 종목을 고른 기준(1개월 초과수익 상위)과"
                              " 같은 구간에서 잰 값이라 구조적으로 부풀려진다 — 새로 고른 북은 거의 항상"
                              " 좋게 나온다. 편향 없는 검증은 [백테스트] 절(다음 구간 실현수익)을 본다.")
                else:
                    print("  구성 불가 (후보 부족)")
        except Exception as e:
            print(f"\n[스크리닝] 실패: {str(e)[:60]}", file=sys.stderr)

    # ── 전략모드: [브레드스] 서술을 "그래서 오늘은 뭘 위주로 볼까"로 바꾼다 ───
    # 브레드스 자체는 이미 위에서 계산돼 있었지만("좁은 장 — 종목선택이 크게
    # 먹힘") 그건 장의 성격 **서술**이었지 **행동 권고**가 아니었다 — 브리핑을
    # 읽는 사람이 매번 "그래서 로테이션을 볼까 스크리닝을 볼까"를 직접 판단해야
    # 했다. 같은 pct·같은 임계값(BREADTH_NARROW/WIDE)을 재사용해 그 판단을
    # 스크립트가 대신 명시한다.
    print("\n[전략모드]")
    if pct is None:
        print("  브레드스 계산 불가(스크리닝 실패) — 로테이션([지역]/[섹터]/[스타일])만 참고")
    elif pct < BREADTH_NARROW:
        print(f"  좁은 장(브레드스 {pct:.0f}%) → 스크리닝(개별종목) 위주 — 로테이션 표는 참고만")
    elif pct > BREADTH_WIDE:
        print(f"  넓은 장(브레드스 {pct:.0f}%) → 로테이션(그룹) 위주 — 지수만 사도 비슷해 종목선택 효과가 작다")
    else:
        print(f"  중립 장(브레드스 {pct:.0f}%) → 로테이션·스크리닝 비중 5:5, 두 랭킹 상위가 겹치는 종목 우선")

    # ── 모멘텀: 과열·과매도가 며칠 뒤가 아니라 지금 꺾이는 중인지 ───────────
    print("\n[모멘텀]")
    if hot_cold:
        hot_cold.sort(key=lambda x: -x[0])
        print("  " + " · ".join(
            f"{n} RSI{r:.0f}({'과열' if r >= RSI_HOT else '과매도'}/MACD{d or '-'})"
            for r, d, n in hot_cold))
    else:
        print(f"  과열·과매도 없음 (RSI {RSI_COLD}~{RSI_HOT})")

    # ── 빌드업: 오늘 기록 남기고, 최근 며칠과 이어보기 ──────────────────────
    today_kst = datetime.now(ZoneInfo("Asia/Seoul")).date().isoformat()
    try:
        log_buildup(today_kst, dict(
            above_ma50=above_ma50,
            breadth_pct=round(pct, 1) if pct is not None else None,
            top_group=top_group_name,
            vix=vix_val,
            stretched_n=len(stretched),
        ))
    except Exception as e:
        print(f"[빌드업] 기록 실패: {str(e)[:60]}", file=sys.stderr)
    print("\n[빌드업]")
    try:
        trend = buildup_trend()
    except Exception as e:
        # 여기서 죽으면 [백테스트]·[스트레치]·[상관] 까지 통째로 못 찍는다 —
        # 로그 하나 못 읽는다고 오늘 브리핑 전체가 날아가면 안 된다.
        print(f"  집계 실패: {str(e)[:60]}", file=sys.stderr)
        trend = None
    if trend:
        reg_txt = ("위" if trend["regime"] else "아래") if trend["regime"] is not None else "?"
        bf, bl = trend["breadth_first"], trend["breadth_last"]
        breadth_txt = f"{bf:.0f}%→{bl:.0f}%" if bf is not None and bl is not None else "기록 없음"
        # '일째'가 아니라 '회째' — 실행을 건너뛴 날은 로그에 구멍이 나므로
        # 이 숫자는 영업일수가 아니라 연속으로 남은 기록 횟수다 (buildup_trend 주석 참고)
        print(f"  최근 {trend['n']}회 기록 · 레짐 {reg_txt} {trend['regime_n']}회째 유지"
              f" · '{trend['top'] or '?'}' {trend['top_n']}회째 1등 · 브레드스 {breadth_txt}")
    else:
        print("  기록 1회째 — 다음 실행부터 누적 추세가 보인다")

    # ── 백테스트: 이 로테이션 규칙이 최근 실제로 벤치를 이겼나 ───────────────
    print("\n[백테스트]")
    bt = backtest_summary()
    if bt["state"] == "fresh":
        print(f"  {bt['as_of']} 기준(-{bt['age_days']}일) · 지역·섹터·스타일 로테이션 {bt['periods']}회 리밸런스"
              f" · 적중 {bt['hits']}/{bt['periods']}({bt['hit_rate']:.0f}%)"
              f" · 회당평균초과 {bt['avg_excess']:+.2f}%p · 정보비율(회당) {bt['ir']:+.2f}"
              f" · 최대낙폭(누적초과수익) {bt['mdd']:+.1f}%p")
        print("  ※ 개별종목 스크리닝은 생존편향 때문에 과거 재현 불가 — 그룹 로테이션 규칙만 검증한 값")
    elif bt["state"] == "stale":
        # 10일 넘게 안 갱신됐다는 건 주간 잡(strategy-backtest-weekly)이 죽었을 수
        # 있다는 뜻이다 — "한 번도 설치 안 함"과 다른 문제이므로 다르게 알린다
        print(f"  🔴 캐시가 {bt['age_days']}일째 안 갱신됨({bt['as_of']} 이후) — "
              f"주간 잡(strategy-backtest-weekly)이 죽었을 수 있다. 숫자는 안 낸다")
    elif bt["state"] == "corrupt":
        print("  🔴 캐시 파일이 깨져 있다 — .automation/strategy_backtest.py 를 다시 돌릴 것")
    else:
        print("  아직 없음 — .automation/strategy_backtest.py 를 한 번 돌리면 채워진다 (주간 갱신)")

    # ── 체결 추적: 신호가 아니라 실제 매매가 어떻게 됐나 ─────────────────
    print("\n[체결추적]")
    try:
        followup = trade_followup(b)
    except Exception as e:
        print(f"  집계 실패: {str(e)[:60]}", file=sys.stderr)
        followup = []
    if followup:
        # 청산 후보(exit_flag 있는 것)를 먼저 보여준다 — 매일 훑을 때 가장 급한
        # 줄이 맨 아래 묻히면 놓치기 쉽다.
        for f in sorted(followup, key=lambda x: (
                x["exit_flag"] is None, x["excess"] if not pd.isna(x["excess"]) else 0)):
            note = f" — {f['note']}" if f["note"] else ""
            bench_txt = f"{f['bench_ret']:+.1f}%" if not pd.isna(f["bench_ret"]) else "?"
            excess_txt = f"{f['excess']:+.1f}%p" if not pd.isna(f["excess"]) else "?"
            print(f"  {f['ticker']:8}{f['entry_date']} 진입 {f['entry_price']:.2f}→{f['cur_price']:.2f}"
                  f"({f['ret']:+.1f}%) · 벤치 {bench_txt} · 초과 {excess_txt} · {f['days']}일째{note}")
            if f["exit_flag"]:
                print(f"           {f['exit_flag']}")
    else:
        print("  기록된 체결 없음 — .automation/log_trade.py 로 남기면 다음날부터 추적된다")

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
