#!/usr/bin/env python3
"""
시장봇 데이터 수집 헬퍼. yfinance로 티커별 최근 종가/등락률을 가져와
CSV 한 줄씩 출력한다 (agent가 결과를 그대로 표로 옮겨 적기 쉽게).

사용법:
  python3 market_snapshot.py TICKER [TICKER ...] [--threshold 3.0]

출력 (stdout, CSV):
  ticker,label,last_close,prev_close,pct_change,flag
  flag는 |pct_change| >= threshold 일 때 'ALERT', 아니면 'normal'

숫자 계산(등락률)은 전부 이 스크립트가 하고, LLM은 이 출력을 그대로 옮겨적기만
하면 된다 — 숫자를 LLM이 암산/추정하지 않도록 하는 게 목적이다.
"""
import sys
import argparse
import yfinance as yf

# 자주 쓰는 티커의 친숙한 한글 이름 — 없는 티커는 그대로 심볼을 라벨로 씀
LABELS = {
    "^KS11": "코스피",
    "^KQ11": "코스닥",
    "^GSPC": "S&P 500",
    "^IXIC": "나스닥",
    "^DJI": "다우존스",
    "KRW=X": "원/달러 환율",
    "GC=F": "금 선물",
    "CL=F": "WTI 원유",
    "BTC-USD": "비트코인",
}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("tickers", nargs="+")
    parser.add_argument("--threshold", type=float, default=3.0)
    args = parser.parse_args()

    print("ticker,label,last_close,prev_close,pct_change,flag")
    for t in args.tickers:
        label = LABELS.get(t, t)
        try:
            hist = yf.Ticker(t).history(period="5d", interval="1d")
            close = hist["Close"].dropna()
            if len(close) < 2:
                print(f"{t},{label},NA,NA,NA,insufficient_data", file=sys.stderr)
                continue
            last = close.iloc[-1]
            prev = close.iloc[-2]
            pct = (last - prev) / prev * 100
            flag = "ALERT" if abs(pct) >= args.threshold else "normal"
            print(f"{t},{label},{last:.2f},{prev:.2f},{pct:+.2f},{flag}")
        except Exception as e:
            print(f"{t},{label},ERROR,ERROR,ERROR,error:{e}", file=sys.stderr)


if __name__ == "__main__":
    main()
