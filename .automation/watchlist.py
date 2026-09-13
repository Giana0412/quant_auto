#!/usr/bin/env python3
"""팀 워치리스트 — 팀원이 조사한 종목을 파이프라인에 넣는 창구.

── 왜 필요한가 ───────────────────────────────────────────────────────────
1차 미팅(260911) 공통 액션 아이템에 이렇게 적혀 있다:

    종목 조사 결과는 수시로 김규형 파이프라인/텔레그램으로 공유

그런데 **받을 창구가 없었다.** 티커가 파이프라인에 들어오는 경로는
market-snapshot.sh 가 뉴스레터 다이제스트에서 LLM 으로 뽑는 것 하나뿐이라
(§market-snapshot.sh 1단계), 이정민이 파이낸셜 종목을 이유찬이 D램/HBM 종목을
조사해 와도 넣을 데가 없었다. 받는 쪽이 이 파이프라인이라 여기서 만들어야 한다.

── 설계 ──────────────────────────────────────────────────────────────────
· **담당자와 사유를 필수로 남긴다.** 티커만 모으면 한 달 뒤에 "이거 왜 넣었지"가
  된다. 대회가 끝나고 "규칙이 틀렸나 실행이 틀렸나"를 가리려면 누가 왜 넣었는지가
  있어야 한다 — log_trade.py 가 --note 를 받는 것과 같은 이유다.
· **지울 때도 기록을 남긴다(drop).** 줄을 지우는 게 아니라 status 를 바꾼다.
  빼는 판단도 판단이라 남아야 한다.
· **append-only JSONL + 원자적 쓰기.** 다른 로그(빌드업·체결)와 같은 방식이다 —
  실행이 중간에 죽어도 파일이 반쯤 잘리지 않는다.
· market_metrics.py 가 active 티커를 자동으로 읽어 [워치리스트] 절에 벤치 대비
  성과를 매일 다시 계산한다. **팀원 각자의 픽이 실제로 벤치를 이기고 있는지**가
  매일 아침 브리핑에 뜬다는 뜻이다.

사용:
  .automation/.venv/bin/python .automation/watchlist.py add JPM \\
      --owner 이정민 --sector 금융 --reason "캐피털마켓 강세, 3주차 실적"
  .automation/.venv/bin/python .automation/watchlist.py drop JPM --reason "금리 발표 후 논리 깨짐"
  .automation/.venv/bin/python .automation/watchlist.py list
  .automation/.venv/bin/python .automation/watchlist.py list --all   # 뺀 것까지
"""
import argparse
import json
import sys
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

WATCHLIST = Path("personal/10-market/_watchlist/watchlist.jsonl")

# 담당자는 자유 문자열이 아니라 목록으로 받는다 — "이정민"/"정민"/"LJM" 이
# 섞이면 나중에 사람별로 묶어 보질 못한다.
OWNERS = ["김규형", "이정민", "이유찬", "공통"]


def _read():
    if not WATCHLIST.exists():
        return []
    out = []
    for line in WATCHLIST.read_text().splitlines():
        try:
            r = json.loads(line)
        except Exception:
            continue
        if isinstance(r, dict) and "ticker" in r:
            out.append(r)
    return out


def _write(rows):
    WATCHLIST.parent.mkdir(parents=True, exist_ok=True)
    tmp = WATCHLIST.with_suffix(WATCHLIST.suffix + ".tmp")
    with tmp.open("w") as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    tmp.replace(WATCHLIST)


def load_active():
    """market_metrics.py 가 쓰는 진입점. status=active 인 것만, 티커별로
    **가장 최근 레코드**를 돌려준다 — 뺐다가 다시 넣는 경우가 있어서다."""
    latest = {}
    for r in sorted(_read(), key=lambda r: r.get("date", "")):
        latest[r["ticker"]] = r
    return [r for r in latest.values() if r.get("status") == "active"]


def cmd_add(args):
    t = args.ticker.upper()
    rec = dict(date=args.date or datetime.now(ZoneInfo("Asia/Seoul")).date().isoformat(),
               ticker=t, status="active", owner=args.owner,
               sector=args.sector, reason=args.reason)
    rows = _read()
    rows.append(rec)
    _write(rows)
    dup = [r for r in rows[:-1] if r["ticker"] == t and r.get("status") == "active"]
    print(f"추가됨: {t} [{args.owner}]"
          f"{' · ' + args.sector if args.sector else ''} — {args.reason}")
    if dup:
        print(f"  ⚠️ 이미 active 로 들어 있던 종목이다 ({dup[-1]['date']}, "
              f"{dup[-1].get('owner')}) — 사유가 갱신된 것으로 본다")
    return 0


def cmd_drop(args):
    t = args.ticker.upper()
    active = {r["ticker"] for r in load_active()}
    if t not in active:
        print(f"🔴 {t} 는 지금 워치리스트에 없다 (list 로 확인할 것)", file=sys.stderr)
        return 1
    rows = _read()
    rows.append(dict(date=args.date or datetime.now(ZoneInfo("Asia/Seoul")).date().isoformat(),
                     ticker=t, status="dropped", owner=args.owner, reason=args.reason))
    _write(rows)
    print(f"제외됨: {t} — {args.reason}")
    return 0


def cmd_list(args):
    rows = _read()
    if not rows:
        print("워치리스트가 비어 있다. add 로 넣는다.")
        return 0
    active = load_active()
    print(f"[워치리스트] active {len(active)}종목")
    by_owner = {}
    for r in active:
        by_owner.setdefault(r.get("owner") or "?", []).append(r)
    for owner in sorted(by_owner):
        print(f"\n  {owner}")
        for r in sorted(by_owner[owner], key=lambda r: r["date"]):
            sec = f" [{r['sector']}]" if r.get("sector") else ""
            print(f"    {r['ticker']:<8}{r['date']}{sec}  {r.get('reason', '')}")
    if args.all:
        dropped = [r for r in rows if r.get("status") == "dropped"]
        if dropped:
            print(f"\n  제외 기록 {len(dropped)}건")
            for r in sorted(dropped, key=lambda r: r["date"]):
                print(f"    {r['ticker']:<8}{r['date']}  {r.get('reason', '')}")
    return 0


def main():
    p = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="cmd", required=True)

    a = sub.add_parser("add", help="종목을 워치리스트에 넣는다")
    a.add_argument("ticker", help="야후 파이낸스 티커 (예: JPM)")
    a.add_argument("--owner", required=True, choices=OWNERS, help="누가 조사했나")
    a.add_argument("--reason", required=True, help="왜 넣나 — 한 달 뒤에 읽어도 알 수 있게")
    a.add_argument("--sector", default=None, help="섹터 (선택)")
    a.add_argument("--date", default=None, help="YYYY-MM-DD (기본: 오늘 KST)")
    a.set_defaults(func=cmd_add)

    d = sub.add_parser("drop", help="워치리스트에서 뺀다 (기록은 남는다)")
    d.add_argument("ticker")
    d.add_argument("--reason", required=True, help="왜 빼나 — 빼는 판단도 판단이다")
    d.add_argument("--owner", default=None, choices=OWNERS)
    d.add_argument("--date", default=None)
    d.set_defaults(func=cmd_drop)

    l = sub.add_parser("list", help="현재 워치리스트")
    l.add_argument("--all", action="store_true", help="제외 기록까지 본다")
    l.set_defaults(func=cmd_list)

    args = p.parse_args()
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
