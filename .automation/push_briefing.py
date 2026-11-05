#!/usr/bin/env python3
"""아침 브리핑을 팀 대시보드(Streamlit, bloomberg-chart-app)의 **브리핑** 탭에 올린다.

── 왜 ──────────────────────────────────────────────────────────────────────
2026-11-06 요청: 텔레그램 말고 대시보드에서도 매일 브리핑을 보고 싶다.
대시보드는 Streamlit Cloud 에 떠 있어 이 노트북의 파일을 못 읽는다. 대시보드가
이미 쓰는 저장소는 **포트폴리오 구글 시트**뿐이라 거기 `briefings` 탭으로 올린다
(쓰기는 그 앱의 Apps Script 웹 앱 — apps_script/Code.gs 의 upsert_briefing).
같은 날짜·종류면 덮어쓴다 — 07:30 백업 체인이 돌아도 줄이 늘지 않는다.

── 무엇을 ──────────────────────────────────────────────────────────────────
  conclusion  _conclusions/YYMMDD-오늘의결론.md         (텔레그램 그룹과 같은 본문)
  easy        _conclusions/YYMMDD-오늘의결론-쉬운설명.md
  agents      data/YYMMDD-에이전트의견.md               (TradingAgents, §agent_review.py)
없는 파일은 건너뛴다. 하나도 없으면 아무것도 안 보내고 1 로 끝난다.

설정: .automation/.sheet.env (gitignore 의 *.env)
  SHEET_WRITE_URL=https://script.google.com/macros/s/…/exec
  SHEET_WRITE_TOKEN=…   ← Streamlit Secrets 의 같은 이름 값과 같다
없으면 조용히 0 으로 건너뛴다(아직 안 켠 것이지 고장이 아니다).

표준 라이브러리만 쓴다 — 어느 파이썬으로 돌려도 된다.
  python3 .automation/push_briefing.py [YYMMDD] [--dry-run]
"""
from __future__ import annotations

import json
import os
import sys
import urllib.request
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parent.parent
MARKET = ROOT / "personal" / "10-market"
ENV = ROOT / ".automation" / ".sheet.env"
KST = ZoneInfo("Asia/Seoul")


def load_env() -> tuple[str | None, str | None]:
    vals = dict(os.environ)
    if ENV.exists():
        for line in ENV.read_text().splitlines():
            line = line.strip().removeprefix("export ")
            if "=" in line and not line.startswith("#"):
                k, v = line.split("=", 1)
                vals.setdefault(k.strip(), v.strip().strip('"').strip("'"))
    return vals.get("SHEET_WRITE_URL"), vals.get("SHEET_WRITE_TOKEN")


def ops_for(yymmdd: str) -> list[dict]:
    iso = datetime.strptime(yymmdd, "%y%m%d").date().isoformat()
    now = datetime.now(KST).isoformat(timespec="minutes")
    files = {
        "conclusion": MARKET / "_conclusions" / f"{yymmdd}-오늘의결론.md",
        "easy": MARKET / "_conclusions" / f"{yymmdd}-오늘의결론-쉬운설명.md",
        "agents": MARKET / "data" / f"{yymmdd}-에이전트의견.md",
    }
    ops = []
    for kind, f in files.items():
        if f.exists() and f.stat().st_size:
            # 시트 셀 한도는 50,000자. 브리핑은 실측 3~4천 자라 넉넉하지만 넘으면 자른다.
            body = f.read_text()[:49_000]
            ops.append({"op": "upsert_briefing", "date": iso, "kind": kind, "updated": now, "body": body})
    return ops


def main() -> int:
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    dry = "--dry-run" in sys.argv
    yymmdd = args[0] if args else (os.environ.get("CHAIN_DATE") or datetime.now(KST).strftime("%y%m%d"))
    ops = ops_for(yymmdd)
    if not ops:
        print(f"[대시보드] {yymmdd} 브리핑 파일 없음 — 보낼 것 없음")
        return 1
    kinds = ", ".join(o["kind"] for o in ops)
    if dry:
        print(f"[대시보드] (dry-run) {yymmdd}: {kinds} · {sum(len(o['body']) for o in ops)}자")
        return 0
    url, token = load_env()
    if not (url and token):
        print(f"[대시보드] {ENV.name} 없음 — 건너뜀")
        return 0
    data = json.dumps({"token": token, "ops": ops}).encode()
    req = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json"}, method="POST")
    with urllib.request.urlopen(req, timeout=60) as r:   # Apps Script 는 리다이렉트 뒤에 답한다 — urllib 가 따라간다
        res = json.loads(r.read().decode())
    if not res.get("ok"):
        # 'unknown op: upsert_briefing' = 시트의 Apps Script 를 아직 새 Code.gs 로 재배포 안 했다
        print(f"[대시보드] 🔴 시트가 거부: {res.get('error')}")
        return 1
    print(f"[대시보드] {yymmdd} 올림: {kinds}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
