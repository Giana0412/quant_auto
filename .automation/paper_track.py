#!/usr/bin/env python3
"""페이퍼 트래킹 — 파이프라인이 **자기가 한 말을 기록하고 스스로 채점**한다.

── 왜 만들었나 ───────────────────────────────────────────────────────────
2026-09-21, 트레이딩 커뮤니티 대화록(26,180건)을 훑다가 이 질문을 봤다:

    "백테스트 차트가 나와서 실전에서 적용해보면 유의미하게 비슷한 성과를 낸 경우가
     있으신가요? 저도 **백테스트 상으로는 너무 퍼포먼스가 좋을 때가 많은데,
     실매매는 항상 대부분 안 나오더라고요.**"

    "가치투자 느낌의 보조 레포트는 되어도 그 자체로 매수매도 판별은 위험하지 않을까요?
     **바이어스 없게 백테스트도 안 될 것 같은데.**"

우리 파이프라인이 정확히 이 구멍을 갖고 있었다. 매일 6종목을 추천하면서
**추천했다는 사실을 아무 데도 남기지 않았다.** 남는 건
  · `_buildup/regime-log.jsonl` — 레짐·브레드스·1등 섹터만
  · `_trades/trade-log.jsonl`  — 사람이 실제로 산 것만 (지금 비어 있다)
즉 **"오늘 뭘 추천했나"가 사라져서 나중에 채점할 수가 없다.**

그래서 브리핑이 내는 표본내(in-sample) 정보비율에 매일 "이건 부풀려진 값"이라고
경고만 붙이고, **정작 편향 없는 숫자는 하나도 못 내고 있었다.**

── 이게 왜 지금 중요한가 ─────────────────────────────────────────────────
교수 B(2026-09-18): "7주 뒤에 성적이 나왔을 때 이 시스템이 실제로 도움이
됐는지 어떻게 판단해야 할까요? **대회 전에 미리 정해둬야 할 판단 기준**이 있을까요?"

대회 시작이 10월 중순이다. **오늘부터 기록하면 시작 시점에 3주치 진짜
아웃오브샘플 기록**이 쌓인다. 백테스트로는 절대 못 얻는 숫자다 —
개별종목 스크리닝은 생존편향 때문에 원리상 백테스트가 불가능하기 때문이다
(§market_metrics screen_universe 주석).

── 어떻게 ────────────────────────────────────────────────────────────────
record: 오늘 모델 북(수비형)과 집중 북(공격형)을 **비중까지 그대로** 스냅샷한다.
score : 과거 스냅샷을 오늘 가격으로 다시 재서 **벤치마크 대비** 성과를 낸다.

🔴 **북을 만든 날의 가격으로 진입했다고 가정한다.** 실제 체결이 아니므로
슬리피지·체결 지연이 없다 — 즉 이 숫자도 낙관 쪽으로 치우쳐 있다. 다만
**종목 선택이 사후에 바뀌지 않는다**는 점에서 표본내 지표와는 질이 다르다.
사람이 실제로 산 것은 log_trade.py 가 따로 추적한다(그쪽이 최종 심판이다).

사용:
  .automation/.venv/bin/python .automation/paper_track.py record   # 오늘 북 저장
  .automation/.venv/bin/python .automation/paper_track.py score    # 누적 성적
  .automation/.venv/bin/python .automation/paper_track.py score --detail
"""
import json
import sys
import warnings
from datetime import date, datetime
from pathlib import Path

warnings.filterwarnings("ignore")

import pandas as pd
import yfinance as yf

from market_metrics import (
    BENCH, BOOK_N, EXTRA, SECTOR_CAPS, build_book, fetch, screen, screen_universe,
)

LOG = Path("personal/10-market/_paper/book-log.jsonl")

# 🔴 market_metrics 의 BENCH 는 **표시용 한글 라벨("벤치마크")** 이지 티커가 아니다.
# fetch() 가 EXTRA 로 ACWI→"벤치마크" 매핑을 하고 그 뒤로는 라벨로만 다룬다.
# 그걸 모르고 yf.download 에 BENCH 를 넘겼다가 존재하지 않는 종목을 받아
# bench_now 가 None 이 되고 TypeError 로 죽었다. 여기서 라벨→티커를 되짚는다.
BENCH_TICKER = next((t for t, name in EXTRA.items() if name == BENCH), "ACWI")


def _read():
    if not LOG.exists():
        return []
    out = []
    for line in LOG.read_text().splitlines():
        try:
            r = json.loads(line)
        except Exception:
            continue
        if isinstance(r, dict) and "date" in r and "book" in r:
            out.append(r)
    return out


def _write(rows):
    LOG.parent.mkdir(parents=True, exist_ok=True)
    tmp = LOG.with_suffix(LOG.suffix + ".tmp")
    with tmp.open("w") as f:
        for r in sorted(rows, key=lambda r: (r["date"], r.get("kind", ""))):
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    tmp.replace(LOG)


def cmd_record():
    """오늘 북을 스냅샷. 같은 날 같은 종류는 덮어쓴다(하루 여러 번 돌아도 한 줄)."""
    df, _ = fetch()
    if BENCH not in df.columns:
        print("벤치마크를 못 받았다", file=sys.stderr)
        return 1
    b = df[BENCH].dropna()
    src = screen_universe()
    up, down, allr, px, dropped = screen(b, src)
    if not allr:
        print("스크리닝 결과가 없다", file=sys.stderr)
        return 1

    sector_of = {s: rec["sector"] for s, rec in src.items()}
    weights, _, _ = build_book(px, b, allr, n=BOOK_N,
                               sector_caps=SECTOR_CAPS, sector_of=sector_of)
    if not weights:
        print("북을 못 만들었다", file=sys.stderr)
        return 1

    # 진입가 = 오늘 종가. 실제 체결이 아니라 **가정**이라는 걸 필드 이름에 남긴다.
    entry = {s: float(px[s].dropna().iloc[-1]) for s in weights if s in px.columns}

    # 🔴 스냅샷의 날짜는 **어느 종가를 보고 정했나**이지 며칠에 돌렸나가 아니다.
    # 체인은 06:00 KST 에 도는데 그건 미 동부 전날 17:00 이라, 토·일·월 세 번이
    # 전부 **금요일 종가**를 받는다. date.today() 로 찍으면 같은 베팅이 세 줄로
    # 남아 채점에서 세 번 세어진다 — 실제로 9/26 과 9/28 이 소수점까지 같은 값을
    # 내고 있었다(둘 다 9/25 종가). 표본이 3배로 부풀어 승률이 왜곡된다.
    # 거래일로 찍으면 셋이 한 줄로 합쳐진다(아래 dedupe 가 덮어쓴다).
    price_date = b.index[-1].date().isoformat()
    rec = dict(
        date=price_date,
        run_date=date.today().isoformat(),   # 언제 돌았는지는 따로 남긴다
        kind="defensive",
        book={s: round(w, 4) for s, w in weights.items()},
        assumed_entry=entry,
        bench_price=float(b.iloc[-1]),
        note="종가 진입 가정 · 실제 체결 아님",
    )
    rows = [r for r in _read() if not (r["date"] == rec["date"] and r.get("kind") == "defensive")]
    rows.append(rec)
    _write(rows)
    if rec["date"] != rec["run_date"]:
        print(f"[페이퍼 트래킹] 실행 {rec['run_date']} · 기준 종가 {rec['date']} "
              f"(휴장이라 마지막 거래일로 기록)")
    print(f"[페이퍼 트래킹] {rec['date']} 수비형 북 {len(weights)}종목 기록")
    for s, w in sorted(weights.items(), key=lambda x: -x[1]):
        print(f"  {s:8}{w:>6.1%}  진입가정 {entry.get(s, float('nan')):.2f}")
    print(f"  벤치({BENCH}) {rec['bench_price']:.2f}")
    print(f"\n  → 내일부터 `score` 로 이 북이 벤치를 이겼는지 볼 수 있다.")
    return 0


def _dedupe(rows):
    """같은 종가를 두 번 이상 기록한 스냅샷을 하나로 합친다. (남은 것, 합친 수)

    🔴 날짜가 달라도 **내용이 같으면 같은 베팅이다.** 휴장일에 돌면 직전 거래일
    종가를 그대로 받으므로 토·일·월이 전부 금요일 북이 된다. 그걸 세 건으로 세면
    표본이 3배로 부풀고 승률·평균이 통째로 왜곡된다.

    cmd_record 는 이제 거래일로 찍어 애초에 중복을 안 만들지만, **이미 달력
    날짜로 쌓인 과거 기록**이 있어서 채점 쪽에도 그물을 둔다. 지문은
    (종류, 벤치 종가, 종목별 진입가) — float64 가 소수점까지 같을 확률은 없다.

    로그 원본은 건드리지 않는다. 기록은 기록대로 두고 **셈만 바로잡는다.**
    """
    seen, out, merged = {}, [], 0
    for r in sorted(rows, key=lambda r: r["date"]):
        fp = (r.get("kind", ""), r.get("bench_price"),
              tuple(sorted(r.get("assumed_entry", {}).items())))
        if fp in seen:
            merged += 1
            seen[fp].setdefault("_merged_dates", []).append(r["date"])
            continue
        seen[fp] = r
        out.append(r)
    return out, merged


def cmd_score(detail=False):
    rows = _read()
    if not rows:
        print("[페이퍼 트래킹] 기록이 없다 — `record` 를 먼저 돌린다")
        return 0
    raw_n = len(rows)
    rows, merged = _dedupe(rows)

    syms = sorted({s for r in rows for s in r["book"]})
    px = yf.download(syms + [BENCH_TICKER], period="6mo", interval="1d",
                     progress=False, auto_adjust=True)["Close"]
    if BENCH_TICKER not in px.columns:
        print(f"벤치마크({BENCH_TICKER})를 못 받았다", file=sys.stderr)
        return 1

    def last(sym):
        s = px[sym].dropna() if sym in px.columns else pd.Series(dtype=float)
        return float(s.iloc[-1]) if len(s) else None

    bench_now = last(BENCH_TICKER)
    if bench_now is None:
        # 위 체크를 통과해도 전 구간이 NaN 이면 여기로 온다 — 죽지 말고 알린다
        print(f"벤치마크({BENCH_TICKER}) 가격이 비어 있다", file=sys.stderr)
        return 1
    print(f"[페이퍼 트래킹] 스냅샷 {len(rows)}건 · 오늘 기준 재평가")
    if merged:
        # 🔴 조용히 버리지 않는다 — 표본 수가 줄어든 이유는 결과의 일부다.
        print(f"  ⚠️ 기록 {raw_n}건 중 {merged}건은 **같은 종가를 다시 기록한 것**이라 합쳤다.")
        print(f"     (휴장일에 돌면 직전 거래일 종가를 그대로 받는다 — 같은 베팅이다)")
    print(f"  🔴 종가 진입 가정이라 슬리피지가 빠져 있다 — 낙관 쪽으로 치우친 값이다.")
    print(f"  다만 **종목 선택이 사후에 바뀌지 않아** 표본내 지표와는 질이 다르다.\n")
    print(f"  {'기록일':<12}{'보유일':>6}{'북 수익':>10}{'벤치':>9}{'초과':>10}   종목")

    # 🔴 보유일을 달력으로 세면 안 된다. 기준 종가 날짜가 마지막 종가 날짜와 같으면
    # **시장 시간이 하나도 안 지났다** — 수익 0, 초과 0 이 나오고, 그게 "이기지 못한
    # 1건"으로 세어져 승률을 깎는다. 정보가 없는 행은 세지 않는다.
    last_px_date = px.index[-1].date()

    results = []
    for r in sorted(rows, key=lambda r: r["date"]):
        snap = date.fromisoformat(r["date"])
        if snap >= last_px_date:
            continue                      # 아직 장이 한 번도 안 지났다
        held = (date.today() - snap).days
        tot_w = sum(r["book"].values())
        if tot_w <= 0:
            continue
        port = 0.0
        missing = []
        for s, w in r["book"].items():
            e = r.get("assumed_entry", {}).get(s)
            n = last(s)
            if not e or not n:
                missing.append(s)
                continue
            port += w * (n / e - 1)
        # 미배분(현금)은 수익 0 으로 둔다 — 북 전체 대비 수익률로 환산
        port_pct = port * 100
        bench_ret = (bench_now / r["bench_price"] - 1) * 100 if r.get("bench_price") else float("nan")
        excess = port_pct - bench_ret
        results.append(dict(date=r["date"], held=held, port=port_pct,
                            bench=bench_ret, excess=excess))
        names = " ".join(sorted(r["book"]))
        print(f"  {r['date']:<12}{held:>5}일{port_pct:>+9.2f}%{bench_ret:>+8.2f}%"
              f"{excess:>+9.2f}%p   {names[:44]}")
        if missing:
            print(f"               ⚠️ 가격 없음: {' '.join(missing)}")

    if not results:
        print("  아직 하루도 지나지 않았다 — 내일 다시 본다")
        return 0

    d = pd.DataFrame(results)
    wins = int((d.excess > 0).sum())
    print(f"\n  ── 누적 ──")
    print(f"  스냅샷 {len(d)}건 중 **{wins}건**이 벤치마크를 이겼다 ({wins / len(d) * 100:.0f}%)")
    print(f"  평균 초과수익 {d.excess.mean():+.2f}%p · 중앙값 {d.excess.median():+.2f}%p")
    print(f"  최고 {d.excess.max():+.2f}%p · 최악 {d.excess.min():+.2f}%p")
    if len(d) < 10:
        print(f"\n  ⚠️ 표본 {len(d)}건이다. **아무 결론도 내리면 안 된다.**")
        print("     대회 시작(10월 중순)까지 매일 쌓으면 3주치가 된다.")
    return 0


def main():
    if len(sys.argv) < 2 or sys.argv[1] not in ("record", "score"):
        print(__doc__.split("사용:")[-1].strip())
        return 1
    if sys.argv[1] == "record":
        return cmd_record()
    return cmd_score("--detail" in sys.argv)


if __name__ == "__main__":
    sys.exit(main())
