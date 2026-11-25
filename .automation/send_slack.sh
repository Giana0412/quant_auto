#!/bin/bash
# 결론 브리핑을 개인 Slack(Giana's Workspace) 채널로 보낸다. 2026-11-26 텔레그램 팀 그룹에서 옮겼다.
#
# 사용법: send_slack.sh <메시지파일경로> [--channel 이름]
#   채널 기본값은 SLACK_BRIEF_CHANNEL(없으면 quant-brief).
#
# 봇은 personal_wiki 의 Talon 앱(dailynews 봇, #daily-news 의 Sombra)을 같이 쓴다.
#   · 토큰은 macOS 키체인 newsbot-slack-bot 에서 읽는다 — 저장소·로그에 남기지 않는다.
#   · 봇에 channels:manage 가 없어서 채널은 사람이 만들고 /invite @dailynews 해야 한다.
#   · chat:write.customize 로 채널마다 이름·아이콘을 바꿔 단다(SLACK_BRIEF_NAME/ICON).
#
# 🔴 성공 문구에 '발송 성공 → 그룹' 을 남긴다. evening-chain.sh 가 이 문구로
#    "오늘 이미 보냈다"를 판단해 07:30 백업 실행의 중복 발송을 막는다.
#
# 채널이 없거나 봇이 초대 안 됐으면 send_telegram.sh 의 미설정과 같이 exit 0 으로
# 건너뛰되, 이유를 stderr 에 남긴다 — 그날 체인 전체를 실패로 만들지 않는다.

set -euo pipefail

MSG_FILE=""
CHANNEL="${SLACK_BRIEF_CHANNEL:-quant-brief}"
while [ $# -gt 0 ]; do
  case "$1" in
    --channel) CHANNEL="${2:?--channel 뒤에 채널 이름}"; shift 2 ;;
    --channel=*) CHANNEL="${1#--channel=}"; shift ;;
    *) MSG_FILE="$1"; shift ;;
  esac
done
CHANNEL="${CHANNEL#\#}"

: "${MSG_FILE:?사용법: send_slack.sh <메시지파일경로> [--channel 이름]}"
if [ ! -f "$MSG_FILE" ]; then
  echo "메시지 파일 없음: $MSG_FILE" >&2
  exit 1
fi

if ! SLACK_TOKEN=$(security find-generic-password -a "$USER" -s newsbot-slack-bot -w 2>/dev/null) \
   || [ -z "$SLACK_TOKEN" ]; then
  echo "슬랙 미설정 — 키체인에 newsbot-slack-bot 없음. 발송 건너뜀." >&2
  exit 0
fi

export SLACK_TOKEN CHANNEL MSG_FILE
export SLACK_BRIEF_NAME="${SLACK_BRIEF_NAME:-Quant}"
export SLACK_BRIEF_ICON="${SLACK_BRIEF_ICON:-:chart_with_upwards_trend:}"

# 토큰은 환경변수로만 넘긴다(argv 에 올리면 ps 에 보인다).
exec /usr/bin/python3 -I - <<'PY'
import json, os, re, sys, urllib.parse, urllib.request

tok, want, path = os.environ["SLACK_TOKEN"], os.environ["CHANNEL"], os.environ["MSG_FILE"]


def api(method, params=None, body=None):
    url = f"https://slack.com/api/{method}"
    if params:
        url += "?" + urllib.parse.urlencode(params)
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(url, data=data, headers={
        "Authorization": f"Bearer {tok}",
        "Content-Type": "application/json; charset=utf-8"})
    with urllib.request.urlopen(req, timeout=20) as r:
        return json.load(r)


ch, cursor = None, ""
while True:
    r = api("conversations.list", {"types": "public_channel", "exclude_archived": "true",
                                   "limit": 200, "cursor": cursor})
    if not r.get("ok"):
        sys.exit(f"슬랙 채널 조회 실패: {r.get('error')}")
    ch = next((c for c in r["channels"] if c["name"] == want), None)
    cursor = r.get("response_metadata", {}).get("next_cursor", "")
    if ch or not cursor:
        break

if not ch:
    print(f"슬랙 미설정 — #{want} 채널 없음(공개 채널로 만들 것). 발송 건너뜀.", file=sys.stderr)
    sys.exit(0)
if not ch.get("is_member"):
    print(f"슬랙 미설정 — 봇이 #{want} 에 없음(/invite @dailynews). 발송 건너뜀.", file=sys.stderr)
    sys.exit(0)

text = open(path, encoding="utf-8").read()
# 텔레그램 Markdown → Slack mrkdwn. *bold*·`code` 는 같고 링크만 다르다.
text = re.sub(r"\[([^\]]+)\]\((https?://[^)\s]+)\)", r"<\2|\1>", text)[:39000]

r = api("chat.postMessage", body={
    "channel": ch["id"], "text": text, "mrkdwn": True,
    "unfurl_links": False, "unfurl_media": False,
    "username": os.environ["SLACK_BRIEF_NAME"], "icon_emoji": os.environ["SLACK_BRIEF_ICON"]})
if r.get("ok"):
    print(f"슬랙 발송 성공 → 그룹(#{want})")
else:
    sys.exit(f"슬랙 발송 실패: {r.get('error')}")
PY
