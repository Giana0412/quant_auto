#!/usr/bin/env python3
"""Slack 채널의 새 메시지를 vault의 raw 영역에 마크다운으로 수집한다.

slack-sync 옵시디언 플러그인을 대체한다. 플러그인은 Obsidian 앱이 켜져 있어야만
동작해서, 앱을 닫은 2026-08-06 이후 수집이 조용히 멈춰 있었다. 이 스크립트는
launchd가 직접 돌리므로 앱과 무관하게 동작한다.

토큰 취급: 이 스크립트에는 헤드리스 에이전트가 개입하지 않는다(순수 코드다).
그래서 STAGE2가 쓰는 curl -K 설정파일 우회로가 필요 없고, 토큰을 디스크에
임시 파일로 내려쓰지 않는다 — .slack.env에서 읽어 메모리에서만 쓴다.

멱등성: 파일명이 메시지 내용이 아니라 (날짜, 시각, 작성자)에서만 나오므로
같은 메시지는 항상 같은 파일명이 된다. 이미 있으면 건너뛴다. 따라서 last_ts가
어긋나 같은 구간을 다시 훑어도 중복 문서가 생기지 않는다.
"""

import json
import os
import re
import sys
import urllib.parse
import urllib.request
from datetime import datetime, timezone, timedelta

KST = timezone(timedelta(hours=9))
API = "https://slack.com/api/"

VAULT_DIR = os.environ.get(
    "VAULT_DIR", "/Users/gyuhyeongkim/orca/projects/obsidian_test"
)
ENV_FILE = os.path.join(VAULT_DIR, ".automation/.slack.env")
STATE_FILE = os.path.join(VAULT_DIR, ".automation/slack-sync-state.json")
WORKSPACE = "OAO"

# --dry-run: 무엇을 수집할지 출력만 하고 파일도 상태파일도 쓰지 않는다
DRY_RUN = "--dry-run" in sys.argv

# 채널 : 출력 폴더 (VAULT_DIR 기준 상대경로)
# 플러그인은 출력 폴더를 하나만 가져서 채널별 분기가 불가능했다.
CHANNELS = {
    "test_ob": "vault/05-slack",
}

# 사람이 쓴 게 아닌 메시지 subtype — 수집 대상이 아니다
SKIP_SUBTYPES = {
    "channel_join", "channel_leave", "channel_topic", "channel_purpose",
    "channel_name", "channel_archive", "channel_unarchive", "bot_message",
}

# 본문을 그대로 문서에 넣을 첨부 확장자. 나머지(이미지·PDF·덱)는 링크만 남긴다
# — vault에는 md만 들어간다는 260803 정리본 2-9 결정에 따른다.
INLINE_EXT = {".txt", ".md", ".vtt", ".srt"}


def die(msg):
    print(f"🔴 {msg}", file=sys.stderr)
    sys.exit(1)


def read_token():
    if not os.path.exists(ENV_FILE):
        die(f"Slack 토큰 파일이 없다: {ENV_FILE}")
    with open(ENV_FILE) as f:
        for line in f:
            if line.startswith("SLACK_BOT_TOKEN="):
                return line.split("=", 1)[1].strip()
    die(f"{ENV_FILE} 에 SLACK_BOT_TOKEN 항목이 없다")


def api(token, method, **params):
    url = API + method
    if params:
        url += "?" + urllib.parse.urlencode(params)
    req = urllib.request.Request(url, headers={"Authorization": f"Bearer {token}"})
    with urllib.request.urlopen(req, timeout=30) as r:
        data = json.load(r)
    if not data.get("ok"):
        raise RuntimeError(f"{method} 실패: {data.get('error')}")
    return data


def load_state():
    if os.path.exists(STATE_FILE):
        with open(STATE_FILE) as f:
            return json.load(f)
    return {"channels": {}}


def save_state(state):
    with open(STATE_FILE, "w") as f:
        json.dump(state, f, ensure_ascii=False, indent=2)
        f.write("\n")


def resolve_channel_id(token, name):
    cursor = ""
    while True:
        p = {"types": "public_channel,private_channel", "limit": 200}
        if cursor:
            p["cursor"] = cursor
        d = api(token, "conversations.list", **p)
        for c in d["channels"]:
            if c["name"] == name:
                return c["id"]
        cursor = d.get("response_metadata", {}).get("next_cursor", "")
        if not cursor:
            return None


def load_users(token):
    users, cursor = {}, ""
    while True:
        p = {"limit": 200}
        if cursor:
            p["cursor"] = cursor
        d = api(token, "users.list", **p)
        for u in d["members"]:
            prof = u.get("profile", {})
            users[u["id"]] = (
                prof.get("real_name") or prof.get("display_name") or u.get("name") or u["id"]
            )
        cursor = d.get("response_metadata", {}).get("next_cursor", "")
        if not cursor:
            return users


def fetch_history(token, channel_id, oldest):
    """oldest 이후 메시지를 시간순(오래된 것부터)으로 모두 가져온다."""
    msgs, cursor = [], ""
    while True:
        p = {"channel": channel_id, "limit": 200}
        if oldest:
            p["oldest"] = oldest
        if cursor:
            p["cursor"] = cursor
        d = api(token, "conversations.history", **p)
        msgs.extend(d["messages"])
        cursor = d.get("response_metadata", {}).get("next_cursor", "")
        if not cursor or not d.get("has_more"):
            break
    return sorted(msgs, key=lambda m: float(m["ts"]))


def download_text(token, url):
    req = urllib.request.Request(url, headers={"Authorization": f"Bearer {token}"})
    with urllib.request.urlopen(req, timeout=60) as r:
        return r.read().decode("utf-8", errors="replace")


def safe(s):
    """파일명에 쓸 수 없는 문자를 없앤다."""
    return re.sub(r'[/\\:*?"<>|\s]+', "", s) or "unknown"


def render(msg, users, channel_id, token):
    ts = float(msg["ts"])
    dt = datetime.fromtimestamp(ts, KST)
    author = users.get(msg.get("user", ""), msg.get("username") or "unknown")
    url = f"https://{WORKSPACE}.slack.com/archives/{channel_id}/p{msg['ts'].replace('.', '')}"

    lines = [
        "---",
        f"created: {dt:%Y-%m-%d}",
        f"updated: {datetime.now(KST).isoformat()}",
        f"slack_url: {url}",
        "---",
        "",
        f"## {dt:%H:%M} - {author}",
        "",
        msg.get("text", ""),
        "",
    ]

    for f in msg.get("files", []):
        name = f.get("name", "unnamed")
        ext = os.path.splitext(name)[1].lower()
        lines.append(f"📎 **{name}**")
        lines.append("")
        if ext in INLINE_EXT and f.get("url_private_download"):
            try:
                body = download_text(token, f["url_private_download"])
                lines += ["```", body.rstrip(), "```", ""]
            except Exception as e:  # 첨부 하나가 실패해도 메시지 자체는 남긴다
                lines += [f"> ⚠️ 첨부를 가져오지 못했다: {e}", ""]
        else:
            lines += [
                f"> 바이너리 첨부라 vault에 넣지 않는다. Slack에서 열 것: {f.get('permalink', url)}",
                "",
            ]

    return dt, author, "\n".join(lines)


def target_path(vault, outdir, dt, author, ts):
    """이 메시지를 저장할 경로. 이미 수집된 메시지면 None을 돌려준다.

    파일명은 (날짜, 시각, 작성자)에서만 나온다 — 본문에서 슬러그를 뽑지 않으므로
    같은 메시지는 언제 다시 돌려도 같은 이름이 된다. 같은 사람이 같은 분에 두 번
    말한 경우에만 -2, -3 이 붙는다. 그때도 파일 안의 slack_url로 동일 메시지인지
    구분하므로 중복이 생기지 않는다.
    """
    marker = f"p{ts.replace('.', '')}"
    base = f"{dt:%Y%m%d}_{dt:%H%M}_{safe(author)}"
    for n in range(1, 100):
        fname = f"{base}.md" if n == 1 else f"{base}-{n}.md"
        path = os.path.join(vault, outdir, fname)
        if not os.path.exists(path):
            return path
        with open(path) as f:
            if marker in f.read():
                return None  # 이미 수집됨
    raise RuntimeError(f"파일명 충돌이 100건을 넘었다: {base}")


def collect_channel(token, name, outdir, state, users):
    entry = state["channels"].setdefault(name, {})
    channel_id = entry.get("channel_id") or resolve_channel_id(token, name)
    if not channel_id:
        raise RuntimeError(f"채널을 찾지 못했다: #{name} (봇이 채널에 초대돼 있는가?)")
    entry["channel_id"] = channel_id

    msgs = fetch_history(token, channel_id, entry.get("last_ts"))
    os.makedirs(os.path.join(VAULT_DIR, outdir), exist_ok=True)

    written, skipped, max_ts = 0, 0, entry.get("last_ts")
    for m in msgs:
        max_ts = m["ts"] if max_ts is None else max(max_ts, m["ts"], key=float)

        # 봇이 올린 글은 수집하지 않는다. 이걸 막지 않으면 STAGE2가 게시한
        # "액션 아이템 기한을 정해주세요" 메시지가 다시 원본으로 들어와
        # 자기 출력을 자기 입력으로 먹는 되먹임이 생긴다 (실제로 발생했다).
        if m.get("bot_id") or m.get("subtype") in SKIP_SUBTYPES:
            skipped += 1
            continue
        if not m.get("text", "").strip() and not m.get("files"):
            skipped += 1
            continue

        dt, author, body = render(m, users, channel_id, token)
        path = target_path(VAULT_DIR, outdir, dt, author, m["ts"])
        if path is None:
            skipped += 1  # 이미 수집된 메시지
            continue

        if DRY_RUN:
            preview = " ".join(m.get("text", "").split())[:60]
            print(f"    [dry-run] {os.path.basename(path)}  ({len(body)}자)  {preview}")
        else:
            with open(path, "w") as f:
                f.write(body)
        written += 1

    # 커서는 배치 전체가 끝난 뒤 한 번만 옮긴다. 메시지마다 옮기면 중간에
    # 실패했을 때 일부만 처리된 채로 커서가 전진해 구간이 통째로 누락된다.
    entry["last_ts"] = max_ts
    entry["last_run"] = datetime.now(KST).isoformat()
    entry["last_result"] = "ok"
    return written, skipped, len(msgs)


def main():
    token = read_token()
    state = load_state()
    users = load_users(token)

    total_new = 0
    failed = []
    for name, outdir in CHANNELS.items():
        try:
            w, s, n = collect_channel(token, name, outdir, state, users)
            total_new += w
            print(f"#{name}: 조회 {n}건 → 신규 {w}건, 건너뜀 {s}건 → {outdir}")
        except Exception as e:
            # 한 채널이 실패해도 다른 채널의 커서는 건드리지 않는다
            state["channels"].setdefault(name, {})["last_result"] = f"error: {e}"
            failed.append(f"#{name}: {e}")
            print(f"🔴 #{name} 수집 실패: {e}", file=sys.stderr)

    if not DRY_RUN:
        save_state(state)

    if failed:
        sys.exit(1)
    if total_new == 0:
        print("수집할 새 메시지 없음")


if __name__ == "__main__":
    main()
