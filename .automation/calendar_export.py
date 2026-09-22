#!/usr/bin/env python3
"""캘린더 내보내기 — macro-calendar.json → .ics (그리고 구글 캘린더).

── 왜 .ics 인가 ──────────────────────────────────────────────────────────
구글 캘린더 MCP 는 **OAuth 토큰이 만료돼 있다**(2026-09-22 확인). 재인증은 브라우저
로그인이 필요해 자동화로는 못 한다. 그런데 캘린더뷰는 지금 필요하다.

.ics 는 그 사이를 메운다 — 구글·애플·아웃룩 아무 데나 가져다 쓸 수 있고, MCP
인증과 무관하며, 파일 하나라 팀원에게 그냥 보내도 된다. 인증이 풀리면 MCP 로
직접 밀어 넣는 쪽도 열리지만, **.ics 는 그때도 여전히 유효한 배포 수단**이다.

── 설계 ──────────────────────────────────────────────────────────────────
· **종일 이벤트**로 만든다. 지표 발표는 대부분 미 동부 08:30 인데, 홍콩에서 보면
  밤 시간이라 시각을 박으면 오히려 헷갈린다. 날짜만 맞추는 게 실용적이다.
· **감시 시작일에도 이벤트를 하나 더 만든다**(`watch_days` 만큼 앞). 캘린더를
  열었을 때 "오늘부터 이걸 봐야 한다"가 보여야 의미가 있다 — 당일만 찍히면
  이미 늦는다.
· UID 를 날짜+이름 해시로 고정한다. 다시 내보내 가져오면 **중복이 아니라 갱신**된다.
· 설명(DESCRIPTION)에 watch/note/source 를 그대로 싣는다. 캘린더에서 눌렀을 때
  "무엇을 볼 것인가"가 바로 보이도록.

실행:
  .automation/.venv/bin/python .automation/calendar_export.py
  .automation/.venv/bin/python .automation/calendar_export.py --out ~/Downloads/lc.ics
  .automation/.venv/bin/python .automation/calendar_export.py --no-watch   # 당일만
"""
import hashlib
import json
import sys
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

CAL = Path(".automation/macro-calendar.json")
DEFAULT_OUT = Path("personal/10-market/_events/lc-ghosts.ics")
ICON = {"정책": "🏛", "지표": "📊", "대회": "🏆", "정치": "🗳", "실적": "📈"}


def esc(s):
    """RFC 5545 이스케이프. 쉼표·세미콜론·백슬래시·개행."""
    return (str(s).replace("\\", "\\\\").replace(";", "\\;")
            .replace(",", "\\,").replace("\n", "\\n"))


def fold(line):
    """75옥텟 넘으면 접는다 — 안 접으면 구글이 조용히 잘라먹는다."""
    b = line.encode("utf-8")
    if len(b) <= 73:
        return line
    out, cur = [], b""
    for ch in line:
        e = ch.encode("utf-8")
        if len(cur) + len(e) > 73:
            out.append(cur.decode("utf-8"))
            cur = b" "
        cur += e
    out.append(cur.decode("utf-8"))
    return "\r\n".join(out)


def uid(d, name, tag):
    h = hashlib.sha1(f"{d}|{name}|{tag}".encode()).hexdigest()[:16]
    return f"{h}@lc-ghosts"


def vevent(d, summary, desc, tag, name):
    end = d + timedelta(days=1)          # 종일 이벤트는 DTEND 가 다음 날
    return [
        "BEGIN:VEVENT",
        f"UID:{uid(d, name, tag)}",
        f"DTSTAMP:{datetime.now(timezone.utc):%Y%m%dT%H%M%SZ}",
        f"DTSTART;VALUE=DATE:{d:%Y%m%d}",
        f"DTEND;VALUE=DATE:{end:%Y%m%d}",
        fold(f"SUMMARY:{esc(summary)}"),
        fold(f"DESCRIPTION:{esc(desc)}"),
        "TRANSP:TRANSPARENT",
        "END:VEVENT",
    ]


def main():
    out = Path(sys.argv[sys.argv.index("--out") + 1]) if "--out" in sys.argv else DEFAULT_OUT
    with_watch = "--no-watch" not in sys.argv

    data = json.loads(CAL.read_text())
    lines = ["BEGIN:VCALENDAR", "VERSION:2.0",
             "PRODID:-//LC Ghosts//Bloomberg Trading Challenge//KO",
             "CALSCALE:GREGORIAN", "METHOD:PUBLISH",
             "X-WR-CALNAME:LC Ghosts — 대회·매크로 일정",
             "X-WR-TIMEZONE:Asia/Hong_Kong"]

    n_ev = n_watch = 0
    for e in data.get("events", []):
        if not e.get("date"):
            continue                      # 날짜 미정은 캘린더에 못 올린다
        try:
            d = date.fromisoformat(e["date"])
        except ValueError:
            continue
        icon = ICON.get(e.get("kind"), "•")
        flag = "" if e.get("confirmed") else " ⚠️"
        desc = []
        if e.get("watch"):
            desc.append(f"볼 것: {e['watch']}")
        if e.get("note"):
            desc.append(e["note"])
        if not e.get("confirmed"):
            desc.append("⚠️ 날짜 미확정 — 확인 필요")
        src = e.get("source") or e.get("auto_source")
        if src:
            desc.append(f"출처: {src}")
        body = "\n".join(desc)

        lines += vevent(d, f"{icon} {e['name']}{flag}", body, "ev", e["name"])
        n_ev += 1

        w = e.get("watch_days")
        if with_watch and w and w > 1:
            wd = d - timedelta(days=w)
            if wd > d - timedelta(days=90):     # 너무 먼 감시 시작은 의미 없다
                lines += vevent(
                    wd, f"👀 감시 시작 D-{w} · {e['name']}",
                    f"{w}일 뒤 이벤트.\n{body}", "watch", e["name"])
                n_watch += 1

    lines.append("END:VCALENDAR")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text("\r\n".join(lines) + "\r\n", encoding="utf-8")

    print(f"[캘린더 내보내기] {out}")
    print(f"  이벤트 {n_ev}건" + (f" + 감시 시작 {n_watch}건" if with_watch else " (감시 표시 없음)"))
    print(f"  크기 {out.stat().st_size:,} bytes")
    print("\n  구글 캘린더: 설정 → 가져오기/내보내기 → 가져오기 → 이 파일 선택")
    print("  애플 캘린더: 파일 → 가져오기")
    print("  ※ 다시 내보내 가져오면 UID 가 같아서 **중복이 아니라 갱신**된다.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
