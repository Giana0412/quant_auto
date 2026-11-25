#!/usr/bin/env python3
"""운영 스크리너 신호를 다른 고전 신호와 **같은 조건**에서 비교한다.

── 왜 ──────────────────────────────────────────────────────────────────────
overlay.py(KAN-9) 의 부산물: 운영 스크리너 market_metrics.screen() 의 info_score
(21일 상대수익 ÷ √상대변동성) 상위 5분위가 2014 이후 **비용 전에도** SPY 대비 베타조정
초과 연 −2~−4% 였다. 대형주에서 1개월 수익은 되돌아가는 경향(단기 반전, Jegadeesh 1990)이
있으니, 지금 신호는 반전 효과의 반대편에 서 있을 가능성이 크다. 그렇다면 고칠 방향은
① 12-1 모멘텀(Jegadeesh–Titman 1993: 최근 1개월을 뺀 12개월 수익 — 반전 구간을 건너뛴다)
② 1개월 반전(최근 1개월 많이 빠진 종목)
중 하나다. 셋을 같은 유니버스·같은 비용·같은 백테스트로 재서 고를 근거를 만든다.

── 비교하는 신호 (전부 s = t−1 종가까지, 진입 t 종가) ─────────────────────
  A  info_score      운영 스크리너 그대로 (overlay.screen_a: 벤치 SPY, 고저폭·이력 필터)
  A' e1 만           info_score 에서 변동성 나눗셈을 뺀 21일 상대수익 — 변동성 벌점의 몫을 본다
  M  12-1 모멘텀     C[s−21] / C[s−252] − 1
  R  1개월 반전      −(21일 상대수익)  — A' 의 부호를 뒤집은 것
  U  유니버스 동일가중 그날 편입 종목 전부 — 신호 없이 "S&P 500 동일가중"이 내는 몫(기준선)
각 신호의 상위 5분위를 동일가중으로 들고 H 거래일 보유(월간 21 · 주간 5).
수익·비용·편입·베타·상폐 처리는 overlay.run 과 같다(그 docstring 의 🔴 항목 그대로).
증분 = (신호 − A) 의 리밸런스별 순수익 차 → 평균과 Newey–West t. 판정 기준은 A 대비다.

── 결과 (2026-11-26, 2014-01 ~ 2026-11, runs/signals.txt) ────────────────────
🔴 먼저 기준선: **S&P 500 동일가중(U)도 베타조정 초과가 연 −1.5%** 다(비용 0). 2014 이후 시총가중
SPY 가 동일가중을 이긴 몫(메가캡)이 그대로 음수로 잡힌다. 그래서 신호의 몫은 0 이 아니라 U 와 비교해 읽는다.
  비용 0 · U 대비 연수익      월간           주간
    A  info_score (운영)     −1.8%p         −2.1%p
    A' e1 만                 −2.4%p         −2.9%p   (변동성 벌점은 약간 도움)
    M  12-1 모멘텀           −0.7%p         +0.2%p
    R  1개월 반전            +0.7%p         +2.3%p   (2020– 에서만 양수, 2014–19 는 U 이하)
비용 10bp 를 넣으면 **어떤 신호도 U 를 못 넘는다**(회전율 차이: A·R 80%/월, M 35%, U 17%).
A 대비로는 U 가 주간 +5.6%/년 (NW t +3.0) — 운영 스크리너로 사고파는 것보다 그냥 들고 있는 게 낫다.
→ 21일 모멘텀은 대형주에서 반전의 반대편에 선 신호다. 고친다면 방향은 '모멘텀 강화'가 아니라
  회전을 줄이는 것(12-1 모멘텀·보유기간 연장), 혹은 반전 쪽인데 반전도 비용 뒤엔 남지 않는다.

── 한계 ──────────────────────────────────────────────────────────────────
· 유니버스는 S&P 500(편입 이력 반영). 운영 스크리너의 'ETF 상위 보유종목' 유니버스와 다르다.
· 상위 5분위(~100종목)라 운영 북(5~6종목)보다 잡음이 훨씬 적다 — 신호의 **방향**을 보는 실험이다.
· 신호 5개 × 주기 × 기간을 동시에 본다. |t|≈2 하나는 우연으로 읽는다.

실행: ../headline-sentiment/.venv/bin/python signals.py   (runs/*.pkl 캐시만 · runs/signals.txt 저장)
"""
from __future__ import annotations

import sys

import numpy as np
import pandas as pd

from overlay import COSTS, RUNS, SPLITS, beta_excess, load, member_matrix, nw_t, run, screen_a

BASE = "A  info_score (운영)"


def signals(C: pd.DataFrame) -> dict[str, pd.DataFrame]:
    b = C["SPY"]
    e1 = (C / C.shift(21) - 1).sub(b / b.shift(21) - 1, axis=0)
    A = screen_a(C)
    ok = A.notna()                         # 같은 이력·고저폭 필터를 모든 신호에 — 후보군을 맞춘다
    mom = (C.shift(21) / C.shift(252) - 1).where(C.rolling(252, min_periods=240).count() >= 240)
    return {
        BASE: A,
        "A' e1 만 (변동성 벌점 없음)": e1.where(ok),
        "M  12-1 모멘텀": mom.where(ok),
        "R  1개월 반전": (-e1).where(ok),
        "U  유니버스 동일가중": pd.DataFrame(np.where(ok, 1.0, np.nan), index=C.index, columns=C.columns),
    }


def main():
    lines = []

    class Tee:
        def write(self, s):
            sys.__stdout__.write(s)
            lines.append(s)

        def flush(self):
            sys.__stdout__.flush()

    sys.stdout = Tee()
    win, sector, E, C, V = load()
    EX = beta_excess(C)
    T, J = C.shape
    M = member_matrix(win, C.columns, C.index)
    M[:, list(C.columns).index("SPY")] = False
    rec, P = np.zeros((T, J), bool), np.full((T, J), np.nan)     # PEAD 조건은 끔 — ① 기준 열만 쓴다
    EXv, Cv = EX.to_numpy(), C.to_numpy()
    print(f"[데이터] S&P 500 (편입 이력 반영) · {C.index[0].date()}~{C.index[-1].date()} · 상위 5분위 동일가중"
          f" · 수익 = SPY 대비 베타조정 초과")
    S = signals(C)
    rows = []
    for H, lab in ((21, "월간"), (5, "주간")):
        res = {}
        for name, sc in S.items():
            rule = "all" if name.startswith("U") else "quintile"
            r = run(sc, EXv, Cv, M, rec, P, H, C.index, rule)
            res[name] = r[["① 기준|g", "① 기준|to"]].rename(columns=lambda c: c.split("|")[1])
        ppy = 252 / H
        print(f"\n[{lab} 리밸런스 · 보유 {H}거래일]  연수익(샤프) · 회전 = 회당 편도 교체율 · 증분은 A 대비 10bp 기준")
        print(f"  {'':<28}{'기간':<9}{'회전':>5}" + "".join(f"{f'{c}bp':>15}" for c in COSTS)
              + f"{'A 대비 증분':>13}{'NW t':>7}")
        base = res[BASE]
        for name, r in res.items():
            r = r.join(base, rsuffix="_A", how="inner")
            for plab, a, b in SPLITS:
                q = r[(r.index >= a) & (r.index < b)]
                if q.empty:
                    continue
                cells, rec_row = "", dict(freq=lab, signal=name, period=plab, turnover=q["to"].mean() / 2)
                for c in COSTS:
                    net = q["g"] - c / 1e4 * q["to"]
                    ann, sh = net.mean() * ppy, net.mean() / net.std() * np.sqrt(ppy)
                    cells += f"{ann * 100:>+8.2f}% ({sh:>+4.2f})"
                    rec_row[f"ann{c}"], rec_row[f"sh{c}"] = ann, sh
                inc = ""
                if name != BASE:
                    d = (q["g"] - 10 / 1e4 * q["to"]) - (q["g_A"] - 10 / 1e4 * q["to_A"])
                    inc = f"{d.mean() * ppy * 100:>+12.2f}%{nw_t(d):>+7.2f}"
                    rec_row["inc10"], rec_row["inc10_t"] = d.mean() * ppy, nw_t(d)
                print(f"  {name if plab == SPLITS[0][0] else '':<28}{plab:<9}{q['to'].mean() / 2:>5.0%}" + cells + inc)
                rows.append(rec_row)

    print("\n  한계: 유니버스 S&P 500 · 상위 5분위(운영 북 5~6종목 아님) · 상폐 수익 0 처리 · 헤지 비용 없음."
          "\n  여러 신호·주기·기간을 동시에 본다 — |t|≈2 하나는 우연으로 읽는다.")
    pd.DataFrame(rows).to_csv(RUNS / "signals.csv", index=False)
    sys.stdout = sys.__stdout__
    (RUNS / "signals.txt").write_text("".join(lines))


if __name__ == "__main__":
    main()
