#!/usr/bin/env python3
"""블룸버그 터미널에서 실제로 체결한 뒤 손으로 남기는 매매 기록.

이 파이프라인은 터미널과 연동돼 있지 않다 — 개인 참가자용 API 라이선스가
없어서 gs-quant/Marquee 를 못 쓰는 것과 같은 이유다. 그래서 실제 체결은
스크립트가 알 방법이 없고, 사람이 이 스크립트로 남겨야 market_metrics.py 의
[체결추적] 절이 "브리핑 신호를 따랐을 때 실제로 어떻게 됐나"를 다음날부터
계산해 준다.

사용:
  .automation/.venv/bin/python .automation/log_trade.py AAPL buy 230.50 \\
      --shares 100 --note "RS10일, RSI과열 무시하고 진입"
  .automation/.venv/bin/python .automation/log_trade.py AAPL sell 245.10 \\
      --note "20% 상한 리밸런스로 정리"

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
    args = p.parse_args()

    d = args.date or datetime.now(ZoneInfo("Asia/Seoul")).date().isoformat()
    rec = dict(date=d, ticker=args.ticker.upper(), side=args.side, price=args.price,
               shares=args.shares, note=args.note)

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
    note_txt = f" — {rec['note']}" if rec["note"] else ""
    print(f"기록됨: {d} {rec['ticker']} {rec['side']} {rec['price']:g}{extra}{note_txt}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
