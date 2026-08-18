#!/usr/bin/env python3
"""
시장봇 데이터 수집 헬퍼. yfinance로 티커별 최근 종가/등락률을 가져와
CSV 한 줄씩 출력한다 (agent가 결과를 그대로 표로 옮겨 적기 쉽게).

사용법:
  python3 market_snapshot.py TICKER [TICKER ...] [--threshold 3.0]

출력 (stdout, CSV):
  ticker,label,last_close,last_date,prev_close,prev_date,pct_change,flag,age_days
  flag는 |pct_change| >= threshold 일 때 'ALERT', 아니면 'normal'
  age_days 는 last_date 가 며칠 전인지 (0=오늘, 1=어제 …)

숫자 계산(등락률)은 전부 이 스크립트가 하고, LLM은 이 출력을 그대로 옮겨적기만
하면 된다 — 숫자를 LLM이 암산/추정하지 않도록 하는 게 목적이다.

**날짜를 반드시 같이 낸다.** 예전에는 종가 두 개만 내보내서, 휴장일에도 직전
거래일 숫자가 "오늘의 전일비"처럼 보고됐다. 실제로 2026-08-17(광복절 대체공휴일)에
한국장이 쉬는데 8/14 대비 8/13 등락률(+2.42%)이 그날 수치처럼 텔레그램에 나갔다.
숫자만으로는 며칠 묵은 건지 알 수 없으므로 날짜와 경과일을 함께 낸다.
"""
import sys
import argparse
from datetime import datetime
from zoneinfo import ZoneInfo

import yfinance as yf

KST = ZoneInfo("Asia/Seoul")

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

    today = datetime.now(KST).date()

    print("ticker,label,last_close,last_date,prev_close,prev_date,pct_change,flag,age_days")
    for t in args.tickers:
        label = LABELS.get(t, t)
        try:
            # 휴장이 길면 5일 창에 거래일 2개가 안 잡힐 수 있어 넉넉히 받는다
            hist = yf.Ticker(t).history(period="1mo", interval="1d")
            close = hist["Close"].dropna()
            if len(close) < 2:
                print(f"{t},{label},NA,NA,NA,insufficient_data", file=sys.stderr)
                continue
            last, prev = close.iloc[-1], close.iloc[-2]
            last_d, prev_d = close.index[-1].date(), close.index[-2].date()
            pct = (last - prev) / prev * 100
            flag = "ALERT" if abs(pct) >= args.threshold else "normal"
            age = (today - last_d).days
            print(f"{t},{label},{last:.2f},{last_d},{prev:.2f},{prev_d},"
                  f"{pct:+.2f},{flag},{age}")
        except Exception as e:
            print(f"{t},{label},ERROR,ERROR,ERROR,ERROR,ERROR,error:{e},NA",
                  file=sys.stderr)


if __name__ == "__main__":
    main()
