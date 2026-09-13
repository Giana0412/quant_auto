#!/usr/bin/env python3
"""블룸버그 터미널에서 실제로 체결한 뒤 손으로 남기는 매매 기록.

이 파이프라인은 터미널과 연동돼 있지 않다 — 개인 참가자용 API 라이선스가
없어서 gs-quant/Marquee 를 못 쓰는 것과 같은 이유다. 그래서 실제 체결은
스크립트가 알 방법이 없고, 사람이 이 스크립트로 남겨야 market_metrics.py 의
[체결추적] 절이 "브리핑 신호를 따랐을 때 실제로 어떻게 됐나"를 다음날부터
계산해 준다.

사용:
  .automation/.venv/bin/python .automation/log_trade.py AAPL buy 230.50 \\
      --shares 100 --sector 기술 --note "RS10일, RSI과열 무시하고 진입"
  .automation/.venv/bin/python .automation/log_trade.py AAPL sell 245.10 \\
      --note "20% 상한 리밸런스로 정리"

--sector 를 남기면 [체결추적] 이 그 섹터의 목표수익·손절선(SECTOR_RULES)을
적용한다 — 1차 미팅에서 정한 "섹터별 목표 수익률에 도달하면 즉시 매도하고
다음 섹터로 순환"을 추적하기 위한 것이다. 안 남기면 기본값을 쓴다.

날짜는 항상 오늘(KST)로 남긴다 — 소급 입력이 필요하면 --date YYYY-MM-DD.
포지션이 열려 있는지는 [체결추적] 쪽에서 **티커별 가장 최근 기록의 side**로
판단한다(정식 체결 장부가 아니라 개인용 추적) — buy 가 마지막이면 보유 중,
sell 이 마지막이면 닫힌 것으로 본다. 분할매수/매도도 그냥 각각 한 줄씩 남기면
된다(마지막 한 줄만 추적에 쓰인다).
"""
import argparse
import json
import sys
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

# 섹터 목록·기본 청산선은 market_metrics 한 곳에서만 정한다 — 여기 따로 적어두면
# SECTOR_RULES 를 고칠 때 조용히 어긋난다(screen_universe 가 GROUPS 와 어긋나
# 섹터 6개가 통째로 빠졌던 것과 같은 사고다). 대가로 이 스크립트도 pandas·
# yfinance 를 끌어와 뜨는 데 몇 초 걸리지만, 손으로 가끔 치는 명령이라 괜찮다.
from market_metrics import SECTOR_RULES, STOP_FROM_ENTRY, TAKE_PROFIT

TRADE_LOG = Path("personal/10-market/_trades/trade-log.jsonl")


def main():
    p = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("ticker", help="야후 파이낸스 티커 (예: AAPL, 005930.KS)")
    p.add_argument("side", choices=["buy", "sell"])
    p.add_argument("price", type=float, help="체결가")
    p.add_argument("--shares", type=float, default=None, help="수량 (기록용, 계산엔 안 쓴다)")
    p.add_argument("--note", default="", help="왜 이 체결인지 — 나중에 신호 대조할 때 쓴다")
    p.add_argument("--date", default=None, help="YYYY-MM-DD (기본: 오늘 KST)")
    p.add_argument("--sector", default=None, choices=sorted(SECTOR_RULES),
                   help="섹터별 목표수익·손절을 적용한다 (안 주면 기본값 "
                        f"목표 {TAKE_PROFIT:+.0f}% / 손절 {STOP_FROM_ENTRY:+.0f}%)")
    args = p.parse_args()

    d = args.date or datetime.now(ZoneInfo("Asia/Seoul")).date().isoformat()
    rec = dict(date=d, ticker=args.ticker.upper(), side=args.side, price=args.price,
               shares=args.shares, note=args.note, sector=args.sector)

    TRADE_LOG.parent.mkdir(parents=True, exist_ok=True)
    # 다른 로그(빌드업)와 달리 이건 하루 여러 건(분할매수 등)이 정상이라
    # 같은 날짜라도 병합하지 않고 그냥 이어붙인다. 원자적 쓰기로 중간에 죽어도
    # 기존 줄은 보존한다.
    lines = TRADE_LOG.read_text().splitlines() if TRADE_LOG.exists() else []
    lines.append(json.dumps(rec, ensure_ascii=False))
    tmp = TRADE_LOG.with_suffix(TRADE_LOG.suffix + ".tmp")
    tmp.write_text("\n".join(lines) + "\n")
    tmp.replace(TRADE_LOG)

    extra = f" x{rec['shares']:g}" if rec["shares"] else ""
    sec_txt = f" [{rec['sector']}]" if rec["sector"] else ""
    note_txt = f" — {rec['note']}" if rec["note"] else ""
    print(f"기록됨: {d} {rec['ticker']} {rec['side']}{sec_txt} {rec['price']:g}{extra}{note_txt}")
    # 어떤 청산선이 걸렸는지 지금 알려준다 — 다음날 브리핑에서 처음 보면
    # "왜 이 수치로 손절 신호가 떴지"를 되짚어야 한다
    if args.side == "buy":
        r = SECTOR_RULES.get(rec["sector"]) if rec["sector"] else None
        take = r["take"] if r else TAKE_PROFIT
        stop = r["stop"] if r else STOP_FROM_ENTRY
        src = f"{rec['sector']} 룰" if r else "기본값(--sector 미지정)"
        print(f"  청산선: 목표 {take:+.0f}% / 손절 {stop:+.0f}%  ({src})"
              f"  → {rec['price'] * (1 + take / 100):.2f} / {rec['price'] * (1 + stop / 100):.2f}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
