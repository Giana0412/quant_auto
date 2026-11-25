#!/usr/bin/env python3
"""체인 장애를 Jira 인시던트로 남긴다 — chain-watchdog.sh 가 부른다.

── 왜 ────────────────────────────────────────────────────────────────────
워치독 알림은 Slack 에 흘러가고 끝난다. 2026-11-24~26 브리핑이 사흘 끊겼을 때
"언제 시작됐고, 매일 어땠고, 언제 복구됐나"가 어디에도 한 줄로 남지 않았다(KAN-19).
장애는 **상태가 바뀌는 일**이라 Jira 가 맞는 자리다.

── 동작 ──────────────────────────────────────────────────────────────────
  open <메시지파일>   열린 워치독 인시던트가 없으면 새로 만들고(KAN, 에픽 KAN-16 아래),
                      있으면 그날 메시지를 댓글로 붙인다 → 장애 하나 = 티켓 하나.
  resolve <한 줄>     열린 워치독 인시던트가 있으면 복구 댓글을 달고 해결됨으로 옮긴다.
                      없으면 아무것도 안 한다(정상인 날 대부분).

열린 인시던트는 `labels = watchdog AND statusCategory != Done` 으로 찾는다.
손으로 만든 인시던트도 watchdog 라벨을 붙이면 같은 흐름을 탄다.

── 인증 ──────────────────────────────────────────────────────────────────
macOS 키체인 quant-auto-jira (계정 = Atlassian 이메일, 암호 = API 토큰).
  security add-generic-password -a <이메일> -s quant-auto-jira -w
없으면 조용히 건너뛴다 — Jira 가 죽어도 워치독의 Slack 알림은 나가야 한다.
"""
import base64
import json
import re
import subprocess
import sys
import urllib.error
import urllib.parse
import urllib.request

SITE = "https://gyuhyeongkim412.atlassian.net"
PROJECT, EPIC = "KAN", "KAN-16"
INCIDENT_TYPE_ID = "10010"   # 인시던트
RESOLVE_TRANSITION = "41"    # → 해결됨
LABELS = ["ops", "incident", "watchdog"]
SERVICE = "quant-auto-jira"


def creds():
    r = subprocess.run(["security", "find-generic-password", "-s", SERVICE],
                       capture_output=True, text=True)
    m = re.search(r'"acct"<blob>="([^"]+)"', r.stdout)
    pw = subprocess.run(["security", "find-generic-password", "-s", SERVICE, "-w"],
                        capture_output=True, text=True).stdout.strip()
    if r.returncode != 0 or not m or not pw:
        return None
    return base64.b64encode(f"{m.group(1)}:{pw}".encode()).decode()


def api(auth, method, path, body=None):
    req = urllib.request.Request(
        SITE + path, method=method,
        data=json.dumps(body).encode() if body is not None else None,
        headers={"Authorization": f"Basic {auth}", "Accept": "application/json",
                 "Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=20) as r:
        raw = r.read()
    return json.loads(raw) if raw else {}


def open_incident(auth):
    jql = (f"project = {PROJECT} AND labels = watchdog AND statusCategory != Done "
           "ORDER BY created DESC")
    q = urllib.parse.urlencode({"jql": jql, "fields": "summary", "maxResults": 1})
    issues = api(auth, "GET", f"/rest/api/3/search/jql?{q}").get("issues", [])
    return issues[0]["key"] if issues else None


def comment(auth, key, text):
    api(auth, "POST", f"/rest/api/2/issue/{key}/comment", {"body": text})


def main():
    if len(sys.argv) < 3 or sys.argv[1] not in ("open", "resolve"):
        sys.exit("사용법: jira_incident.py open <메시지파일> | resolve <한 줄>")
    auth = creds()
    if not auth:
        print(f"Jira 미설정 — 키체인 {SERVICE} 없음. 건너뜀.", file=sys.stderr)
        return 0
    cmd, arg = sys.argv[1], sys.argv[2]
    try:
        key = open_incident(auth)
        if cmd == "resolve":
            if not key:
                return 0
            comment(auth, key, f"✅ 워치독: 정상 복구\n{arg}")
            api(auth, "POST", f"/rest/api/2/issue/{key}/transitions",
                {"transition": {"id": RESOLVE_TRANSITION}})
            print(f"Jira {key} 해결됨으로 옮김")
            return 0

        text = open(arg, encoding="utf-8").read()
        if key:
            comment(auth, key, text)
            print(f"Jira {key} 에 오늘 상황 댓글")
            return 0
        first = next((l for l in text.splitlines()[1:] if l.startswith("- ")), "체인 장애")
        r = api(auth, "POST", "/rest/api/2/issue", {"fields": {
            "project": {"key": PROJECT}, "issuetype": {"id": INCIDENT_TYPE_ID},
            "parent": {"key": EPIC}, "labels": LABELS, "priority": {"name": "High"},
            "summary": f"[워치독] {first[2:].strip()}"[:200],
            "description": text + "\n\n(chain-watchdog.sh 가 자동으로 만들었다. 복구되면 자동으로 닫힌다.)",
        }})
        print(f"Jira 인시던트 생성 {r.get('key')}")
    except (urllib.error.URLError, OSError, ValueError) as e:
        # Jira 실패가 워치독을 죽이면 안 된다 — 사유만 남긴다.
        detail = e.read().decode(errors="replace")[:200] if isinstance(e, urllib.error.HTTPError) else ""
        print(f"Jira 기록 실패: {e} {detail}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
