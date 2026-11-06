#!/usr/bin/env python3
"""헤드라인 수집 현황을 KEY=VALUE 로 찍는다 — health-check.sh 와 chain-watchdog.sh 가 같이 쓴다.

── 왜 이 데이터만 따로 감시하는가 ────────────────────────────────────────
다른 산출물(시장데이터·결론)은 하루 빠져도 **다음 날 다시 만들면 된다.** 헤드라인은
아니다. yfinance 는 티커당 최근 기사 ~20건만 주므로, 하루 거르면 그날 기사 대부분이
목록에서 밀려나 **영영 못 줍는다.** 실제로 첫 수집(10/22)에서 10/15 치는 26건밖에
안 들어왔다 — 같은 날 10/22 는 896건이었다.

날짜가 사라지는 게 아니라 **얇아진다.** 그래서 "파일이 있나"로는 못 잡고
"오늘 몇 건 늘었나"를 봐야 한다.

── 출력 ──────────────────────────────────────────────────────────────────
  LAST_DATE     쌓인 헤드라인 중 가장 최근 날짜
  DAYS_STALE    오늘과의 차이. 체인은 06:00 KST(=전날 17:00 ET)에 도므로
                **1일 뒤처진 게 정상**이다. 2일을 넘으면 수집이 멈춘 것
  ROWS_TOTAL    전체 행
  ROWS_LAST     LAST_DATE 의 행 수 — 비정상적으로 적으면 반쪽 수집
  DATES_ALL     헤드라인이 있는 고유 날짜 (라벨 전, 얇은 날짜 포함)
  DATES_LABELED 라벨(excess)까지 끝나고 **건수도 충분한** 고유 날짜 — train.py 가 보는 값
  DATES_THIN    건수가 모자라 빠진 날짜 수 (라벨은 됐지만 카운트에 안 들어간 것)
  NEED          학습까지 남은 날짜 수 (MIN_DATES 기준)
  READY         1 이면 지금 학습 가능
  STATUS        ok | empty — 🔴 이 줄이 **아예 없으면** 조회 자체가 실패한 것이다.
                "데이터가 안 쌓인다"와 "상태를 못 읽는다"는 전혀 다른 고장이라
                부르는 쪽이 구분할 수 있어야 한다. 섞으면 오탐이 나고,
                오탐 한 번이면 사람이 다음부터 알림을 안 본다.

파일이 없거나 깨져도 **0 으로 끝난다.** 이 스크립트가 죽으면 그걸 부르는
건강검진까지 같이 죽는데, 그게 바로 이 레포가 두 번 겪은 실패 방식이다.
"""
import json
import sys
from datetime import date, timedelta
from pathlib import Path

DATA = Path("/Users/gyuhyeongkim/orca/projects/quant_auto"
            "/personal/10-market/_headlines/headlines.jsonl")
MIN_DATES = 20          # ml/headline-sentiment/data.py 의 MIN_DATES 와 같은 값
# 🔴 data.py 의 MIN_ROWS_PER_DATE 와 **같은 값이어야 한다.** 갈라지면 텔레그램의
# "학습까지 D-N" 과 train.py 가 실제로 요구하는 날짜 수가 어긋나고, 사람은
# D-0 인 줄 알고 돌렸다가 가드에 막힌다. 거기 주석에 왜 20건인지 적어 뒀다.
MIN_ROWS_PER_DATE = 20


def session(d):
    """달력 날짜 → 진입 거래일(토·일 → 월). 미국 공휴일은 무시한다."""
    x = date.fromisoformat(d)
    return (x + timedelta(days=(7 - x.weekday()) % 7 if x.weekday() >= 5 else 0)).isoformat()


def main():
    out = dict(LAST_DATE="-", DAYS_STALE=-1, ROWS_TOTAL=0, ROWS_LAST=0,
               DATES_ALL=0, DATES_LABELED=0, DATES_THIN=0,
               NEED=MIN_DATES, READY=0, STATUS="empty")
    try:
        dates, labeled_n, total = {}, {}, 0
        with DATA.open() as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    r = json.loads(line)
                except Exception:
                    continue          # 한 줄 깨져도 나머지는 센다
                d = r.get("date")
                if not d:
                    continue
                total += 1
                dates[d] = dates.get(d, 0) + 1
                if r.get("excess") is not None:
                    s_ = session(d)
                    labeled_n[s_] = labeled_n.get(s_, 0) + 1
        if dates:
            last = max(dates)
            # 라벨까지 끝난 날짜 중 **건수가 충분한 것만** 센다. 3건짜리 일요일을
            # 896건짜리 목요일과 똑같이 1일로 세면 가드가 무력해진다 (§data.py).
            # 🔴 **거래일**로 센다(§data.py load) — 주말 기사는 월요일 종가로 진입해
            # 같은 가격창을 쓰므로 독립 날짜가 아니다. 2026-11-06 까지 달력으로 세서
            # '19일'이라 했지만 실제로는 13거래일이었다.
            usable = {d for d, n in labeled_n.items() if n >= MIN_ROWS_PER_DATE}
            out["LAST_DATE"] = last
            out["ROWS_LAST"] = dates[last]
            out["DAYS_STALE"] = (date.today() - date.fromisoformat(last)).days
            out["ROWS_TOTAL"] = total
            out["DATES_ALL"] = len(dates)
            out["DATES_LABELED"] = len(usable)
            out["DATES_THIN"] = len(labeled_n) - len(usable)
            out["NEED"] = max(0, MIN_DATES - len(usable))
            out["READY"] = 1 if len(usable) >= MIN_DATES else 0
            out["STATUS"] = "ok"
    except FileNotFoundError:
        pass                          # 아직 한 번도 안 돌았다 — 에러가 아니다
    except Exception as e:
        print(f"# 읽기 실패: {e}", file=sys.stderr)

    for k, v in out.items():
        print(f"{k}={v}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
