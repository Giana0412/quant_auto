#!/usr/bin/env python3
"""이벤트 알림 — 감시 창에 들어온 것만 텔레그램으로 보낸다.

── 🔴 D-N 을 그냥 세지 않는다 ────────────────────────────────────────────
"D-30 중간선거"를 매일 알려봐야 아무도 안 본다. 중요한 건 **언제부터 주시해야
하는가**이고, 그건 이벤트 성격마다 다르다.

그래서 캘린더의 각 이벤트에 `watch_days`(감시 시작 리드타임)를 둔다:

  FOMC 14일   시장이 2주에 걸쳐 금리 기대를 반영한다. 팀 전략도 "실적 1~2주 전 진입"
  CPI 7일     포지셔닝이 대략 한 주 전부터 움직인다
  고용 5일    당일 반응이 대부분이라 짧게
  ECB/BoJ 7일 환율을 경유해 오므로 미국 주식엔 간접적
  선거 30일   예측시장이 몇 주 전부터 움직인다 (두 교수 모두 예측시장을 보라고 했다)
  대회 일정   준비에 실제로 필요한 기간

이 값들은 **판단이지 측정이 아니다.** 근거는 캘린더 `_주석` 과
wiki/competition/timeline.md 에 적어 두었다.

── 언제 보내나 ───────────────────────────────────────────────────────────
매일 떠드는 대신 **상태가 바뀔 때만** 보낸다:
  · 🔔 감시 창에 **처음 들어온 날** (D-watch_days)
  · ⏰ **D-1**, 🚨 **D-0**
이미 알린 것은 상태 파일에 남겨 다시 보내지 않는다. 그래서 조용한 날은 조용하다.

**날짜가 확정 안 된 이벤트(confirmed=false)도 알린다.** 오히려 그게 더 위험하다 —
9/23 행사처럼 "확인하러 가야 하는 일정"은 놓치면 안 된다. 대신 ⚠️ 를 붙인다.

실행:
  .automation/.venv/bin/python .automation/event_alerts.py            # 새 알림만
  .automation/.venv/bin/python .automation/event_alerts.py --all      # 감시 중 전부
  .automation/.venv/bin/python .automation/event_alerts.py --send     # 텔레그램 발송
  .automation/.venv/bin/python .automation/event_alerts.py --dry-run  # 보낼 내용만 출력
"""
import json
import subprocess
import sys
import tempfile
from datetime import date, datetime
from pathlib import Path

CAL = Path(".automation/macro-calendar.json")
STATE = Path("personal/10-market/_events/alerted.json")
SENDER = Path(".automation/send_telegram.sh")

DEFAULT_WATCH = 7          # watch_days 가 없으면
ICON = {"정책": "🏛", "지표": "📊", "대회": "🏆", "정치": "🗳", "실적": "📈"}


def load_events():
    if not CAL.exists():
        return []
    try:
        data = json.loads(CAL.read_text())
    except Exception as e:
        print(f"캘린더를 못 읽었다: {str(e)[:60]}", file=sys.stderr)
        return []
    out = []
    for e in data.get("events", []):
        if not e.get("date"):
            continue          # 날짜 미정은 알림 대상이 아니다 (브리핑엔 뜬다)
        try:
            d = date.fromisoformat(e["date"])
        except Exception:
            continue
        out.append({**e, "_d": d})
    return sorted(out, key=lambda e: e["_d"])


def load_state():
    if not STATE.exists():
        return {}
    try:
        return json.loads(STATE.read_text())
    except Exception:
        return {}


def save_state(st):
    STATE.parent.mkdir(parents=True, exist_ok=True)
    tmp = STATE.with_suffix(".tmp")
    tmp.write_text(json.dumps(st, ensure_ascii=False, indent=2) + "\n")
    tmp.replace(STATE)


def stage(e, today):
    """이 이벤트가 지금 어느 단계인가. (단계키, 표시) — 감시 창 밖이면 None."""
    n = (e["_d"] - today).days
    if n < 0:
        return None, n
    w = e.get("watch_days", DEFAULT_WATCH)
    if n == 0:
        return "d0", n
    if n == 1:
        return "d1", n
    if n <= w:
        return "enter", n
    return None, n


def fmt(e, n, kind):
    """알림 한 건을 텔레그램 Markdown 으로. _italic_ 은 쓰지 않는다(경로 언더스코어 충돌)."""
    head = {"d0": "🚨 *오늘*", "d1": "⏰ *내일*", "enter": "🔔 *감시 시작*"}[kind]
    icon = ICON.get(e.get("kind"), "•")
    warn = "" if e.get("confirmed") else "  ⚠️날짜 미확정"
    lines = [f"{head} · D-{n}{warn}",
             f"{icon} *{e['name']}*  ({e['date']})"]
    if e.get("watch"):
        lines.append(f"  볼 것: {e['watch']}")
    if e.get("note"):
        lines.append(f"  {e['note']}")
    return "\n".join(lines)


def main():
    show_all = "--all" in sys.argv
    do_send = "--send" in sys.argv
    dry = "--dry-run" in sys.argv

    today = date.today()
    events = load_events()
    if not events:
        print("[이벤트 알림] 캘린더가 비었다")
        return 0
    st = load_state()

    fresh, watching = [], []
    for e in events:
        kind, n = stage(e, today)
        if kind is None:
            continue
        watching.append((e, n, kind))
        # 같은 이벤트의 같은 단계는 한 번만 알린다
        key = f"{e['date']}|{e['name']}"
        if st.get(key) == kind:
            continue
        fresh.append((e, n, kind))
        st[key] = kind

    if show_all:
        print(f"[이벤트 알림] 감시 중 {len(watching)}건 (기준일 {today})")
        for e, n, kind in watching:
            w = e.get("watch_days", DEFAULT_WATCH)
            mark = "" if e.get("confirmed") else " ⚠️"
            print(f"  D-{n:<3} {ICON.get(e.get('kind'), '•')} {e['name']}{mark}"
                  f"   (감시 리드 {w}일)")
        return 0

    if not fresh:
        print(f"[이벤트 알림] 새 알림 없음 · 감시 중 {len(watching)}건")
        for e, n, kind in watching[:5]:
            print(f"  D-{n:<3} {e['name']}")
        return 0

    body = "\n\n".join(fmt(e, n, k) for e, n, k in fresh)
    msg = f"📅 *이벤트 알림*  ({today})\n\n{body}"
    print(msg)

    if dry:
        print("\n(--dry-run: 보내지 않았다)")
        return 0
    if do_send:
        if not SENDER.exists():
            print("send_telegram.sh 가 없다", file=sys.stderr)
            return 1
        with tempfile.NamedTemporaryFile("w", suffix=".md", delete=False,
                                         encoding="utf-8") as f:
            f.write(msg)
            path = f.name
        # 팀 그룹으로 보낸다 — 이건 시장 정보라 팀이 봐야 한다(건강검진과 다르다)
        r = subprocess.run(["bash", str(SENDER), path, "--to", "group"],
                           capture_output=True, text=True)
        print(r.stdout.strip() or r.stderr.strip())
        if r.returncode != 0:
            # 🔴 발송에 실패하면 상태를 저장하지 않는다 — 저장해 버리면 이 알림을
            # 영영 다시 못 보낸다. 다음 실행에서 재시도되게 둔다.
            print("발송 실패 — 상태를 저장하지 않는다(다음 실행에서 재시도)",
                  file=sys.stderr)
            return 1
    save_state(st)
    return 0


if __name__ == "__main__":
    sys.exit(main())
